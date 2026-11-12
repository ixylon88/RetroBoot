"""Independent mutation boundaries and fail-closed audit evidence checks."""
import struct
import unittest

from tools.audit_fixtures import AUDIT_CASES, mutate_audit_fixture
from tools.build_hdd import fixture
from tools.test_audit import check_audit_screen, check_reads, expected_reads
from tools.ui_text import load_catalog
from test_hdd_tools import samples


class AuditToolsTests(unittest.TestCase):
    def test_released_root_is_closed_but_loader_skip_challenges_remain(self):
        for name in ('retroboot-hdd', 'retroboot-handoff', 'retroboot-reference'):
            _, extents = fixture(samples(), name)
            vbr = next(data for data in extents.values() if len(data) == 512 and data[62:66] == b'RBV1')
            start = struct.unpack_from('<I', vbr, 28)[0]
            spf = struct.unpack_from('<H', vbr, 22)[0]
            root = extents[(start + 1 + 2 * spf) * 512]
            entries = [root[i:i+32] for i in range(0, 25*32, 32) if root[i] != 0xE5]
            self.assertEqual([e[:11] for e in entries],
                [b'RBBOOT  SYS', b'RBSTG2  BIN', b'RBCFG   A  ', b'RBCFG   B  ', b'RBSTATE A  ', b'RBSTATE B  '])
            self.assertEqual(root[25*32], 0)
        _, extents = fixture(samples(), 'hdd-fragmented')
        self.assertEqual((extents[379*512][43], extents[379*512][75]), (0x10, 0x0F))

    def test_audit_mutations_preserve_loader_code_and_stage_chain(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        for name in AUDIT_CASES:
            with self.subTest(name=name):
                new_size, changed = mutate_audit_fixture(size, original, name)
                self.assertEqual(new_size, size)
                self.assertEqual(set(original), set(changed))
                for offset in original:
                    if offset not in (127*512, 253*512, 379*512):
                        self.assertEqual(changed[offset], original[offset])
                for lba in (127, 253):
                    for cluster in (20, 300, 40):
                        self.assertEqual(changed[lba*512][cluster*2:cluster*2+2],
                                         original[lba*512][cluster*2:cluster*2+2])
                self.assertEqual(changed[379*512][20*32:21*32], original[379*512][20*32:21*32])

    def test_orphan_crosslink_and_full_padding_mutations_are_distinct(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        _, orphan = mutate_audit_fixture(size, original, 'audit-orphan')
        for lba in (127, 253): self.assertEqual(orphan[lba*512][8000:8002], b'\xff\xff')
        self.assertEqual(orphan[379*512], original[379*512])
        _, shared = mutate_audit_fixture(size, original, 'audit-cross-copy')
        self.assertEqual(struct.unpack_from('<H', shared[379*512], 24*32+26)[0], 2800)
        self.assertEqual(shared[127*512], original[127*512])
        _, padding = mutate_audit_fixture(size, original, 'audit-padding')
        self.assertEqual(padding[127*512], original[127*512])
        self.assertEqual(padding[253*512][:-1], original[253*512][:-1])
        self.assertNotEqual(padding[253*512][-1], original[253*512][-1])

    def test_read_evidence_requires_order_full_mirrors_and_no_payload(self):
        good = expected_reads({}, 5000, 0)
        self.assertEqual(good[:13], [0,63,126,379,380,127,253,128,254,127,253,137,263])
        self.assertEqual(good[-252:], [v for i in range(126) for v in (127+i,253+i)])
        check_reads(good, good)
        for bad in (good[:-1], good+[411], [63,0]+good[2:], good+[131072]):
            with self.assertRaises(ValueError): check_reads(bad, good)
        retry = AUDIT_CASES['audit-retry']; failure = AUDIT_CASES['audit-io']
        self.assertEqual(expected_reads(retry,5000,0), good+[378])
        self.assertEqual(expected_reads(retry,5000,1), good)
        self.assertEqual(expected_reads(failure,5000,0), good+[378,378])

    def test_rejection_screen_cannot_retain_a_success_table(self):
        for language in ('en', 'de'):
            strings = load_catalog(language); data = bytearray(b' \x17'*2000)
            def text(row,col,value):
                for i,b in enumerate(value.encode('cp437')): data[(row*80+col+i)*2] = b
            for row in range(2,23): data[(row*80+1)*2] = data[(row*80+78)*2] = 0xB3
            for row,col,key in ((2,65,'READ_ONLY'),(5,4,'AUDIT_TITLE'),(6,4,'AUDIT_SCOPE'),
                    (8,4,'AUDIT_COPIES'),(9,4,'AUDIT_CODES'),(11,4,'LBA_HEX'),
                    (13,4,'AUDIT_ERROR_FILE'),(19,4,'AUDIT_REVIEW'),(20,4,'AUDIT_LIMIT'),
                    (21,4,'KEY_HELP'),(22,4,'FUNCTION_HELP')): text(row,col,strings[key])
            text(9,32,'0007 / 0000'); text(11,32,'0000017A'); text(13,32,'0000 / 0000')
            data[(8*80+4)*2+1] = 0x1E
            spec = AUDIT_CASES['audit-padding']; check_audit_screen(data,strings,spec,[])
            for row,col,value in ((12,4,'RBBOOT.SYS'),(17,41,'00003203'),(18,38,'7D2B'),(2,78,'X')):
                good = data[:]; text(row,col,value)
                with self.subTest(language=language,row=row), self.assertRaises(ValueError):
                    check_audit_screen(data,strings,spec,[])
                data[:] = good


if __name__ == '__main__': unittest.main()
