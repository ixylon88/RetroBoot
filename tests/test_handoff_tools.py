"""Independent checks of handoff fixture identity and target-state evidence."""
import struct
import unittest
from test_hdd_tools import samples
from tools.build_hdd import fixture
from tools.handoff_fixtures import (DISK_ID, HANDOFF_CASES, IMAGE_BYTES, LBA,
                                    assembler_header, c_header, entry_bytes, mutate_handoff_fixture)
from tools.test_handoff import check_receipt


class HandoffToolsTests(unittest.TestCase):
    def test_fixed_primary_entry_and_header_binding(self):
        self.assertEqual(entry_bytes().hex(), '802821080679020800000200d1130000')
        self.assertEqual(struct.unpack_from('<II', entry_bytes(), 8), (131072, 5073))
        self.assertIn('%define RB_TEST_LBA 131072', assembler_header())
        header = c_header(bytes(510) + b'\x55\xaa')
        self.assertIn('0x52425431UL', header)
        self.assertIn('rb_test_vbr[512]', header)

    def test_fixtures_preserve_loader_and_partition_boundaries(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        saved = dict(original)
        vbr = bytes(510) + b'\x55\xaa'
        for name in HANDOFF_CASES:
            with self.subTest(name=name):
                length, extents = mutate_handoff_fixture(size, original, name, vbr)
                self.assertEqual(length, IMAGE_BYTES)
                self.assertEqual(extents[0][:440], original[0][:440])
                self.assertEqual(extents[0][462:], original[0][462:])
                if name != 'handoff-identity': self.assertEqual(extents[0][440:446], original[0][440:446])
                for offset, data in original.items():
                    if offset and not (name == 'handoff-ebr' and offset == 63 * 512):
                        self.assertEqual(extents[offset], data)
                self.assertEqual(set(extents) - set(original), {131072 * 512})
                self.assertEqual(original, saved)
        _, extents = mutate_handoff_fixture(size, original, 'retroboot-handoff', vbr)
        extended_start, extended_count = struct.unpack_from('<II', extents[0], 502)
        self.assertLessEqual(extended_start + extended_count, LBA)
        self.assertLessEqual(LBA + 5073, 261072)  # default BIOS CHS reach for 128 MiB

    def test_reject_unknown_fixture_size_and_malformed_sector(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        for name, length, vbr in (('unknown', size, bytes(510) + b'\x55\xaa'),
                                 ('retroboot-handoff', 1, bytes(510) + b'\x55\xaa'),
                                 ('retroboot-handoff', size, bytes(512)),
                                 ('retroboot-handoff', size, bytes(511))):
            with self.assertRaises(ValueError): mutate_handoff_fixture(length, original, name, vbr)

    def receipt(self):
        before, low = bytearray(0x8000), bytearray(0x8000)
        vbr = bytes(range(256)) * 2
        low[0x7C00:0x7E00] = vbr
        low[0x800:0x810] = entry_bytes()
        low[0x820:0x824] = b'RBH1'
        struct.pack_into('<12H', low, 0x824, 0x202, 0, 0, 0, 0, 0x7C00, 0x800, 0x80, 0, 0, 0x7CC0, 0)
        return before, low, vbr

    def test_receipt_verifies_complete_sector_and_stable_low_memory(self):
        before, low, vbr = self.receipt()
        self.assertEqual(check_receipt(low, before, vbr)['sp'], 0x7C00)
        for offset in (0x4C, 0x600, 0x7FF, 0x800, 0x80F, 0x810, 0x81F, 0x820,
                       0x7C00, 0x7DFF):
            changed = bytearray(low); changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError): check_receipt(changed, before, vbr)

    def test_receipt_rejects_each_wrong_entry_state_and_false_pass(self):
        before, low, vbr = self.receipt()
        for offset in range(0x826, 0x83C, 2):
            changed = bytearray(low); struct.pack_into('<H', changed, offset, 0xFFFF)
            with self.subTest(offset=offset), self.assertRaises(ValueError): check_receipt(changed, before, vbr)
        for flags in (0, 0x600):
            changed = bytearray(low); struct.pack_into('<H', changed, 0x824, flags)
            with self.assertRaises(ValueError): check_receipt(changed, before, vbr)
        with self.assertRaises(ValueError): check_receipt(low, before, vbr, 'ds')
        changed = bytearray(low); struct.pack_into('<H', changed, 0x828, 0x80)
        struct.pack_into('<H', changed, 0x83A, 1)
        self.assertEqual(check_receipt(changed, before, vbr, 'ds')['status'], 1)


if __name__ == '__main__': unittest.main()
