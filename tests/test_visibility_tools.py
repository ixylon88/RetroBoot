"""Independent fixture bindings and rejection of stale F7 screen content."""
import struct
import unittest
import zlib

from tools.build_hdd import fixture
from tools.config_fixtures import FILE_LBAS as CFG_LBAS
from tools.state_fixtures import FILE_LBAS as STATE_LBAS
from tools.visibility_fixtures import VISIBILITY_CASES, mutate_visibility_fixture, blocked
from tools.test_visibility import check_visibility_screen
from tools.test_state import PROOF_KEYS
from tools.ui_text import load_catalog
from test_hdd_tools import samples


class VisibilityToolsTests(unittest.TestCase):
    def test_fixture_allocation_and_loader_are_preserved(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        vbr = bytes(510) + b'\x55\xaa'
        for name in VISIBILITY_CASES:
            with self.subTest(name=name):
                new_size, changed = mutate_visibility_fixture(size, original, name, vbr, 'de')
                self.assertEqual(new_size, 128 * 1024 * 1024)
                self.assertEqual(changed[0][:446], original[0][:446])
                self.assertEqual(changed[0][494:], original[0][494:])
                for lba in (126, 127, 253, 379, 411, 483, 1603, 563):
                    self.assertEqual(changed[lba * 512], original[lba * 512])

    def test_distinct_installations_bind_to_each_current_vbr(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        vbr = bytes(510) + b'\x55\xaa'
        for name, kind, masks in (('visibility-dos', 1, [1, 2]), ('visibility-nt-group', 2, [3, 6])):
            _, changed = mutate_visibility_fixture(size, original, name, vbr, 'en')
            cfg = changed[CFG_LBAS[0] * 512]; state = changed[STATE_LBAS[0] * 512]
            self.assertEqual(cfg, changed[CFG_LBAS[1] * 512])
            self.assertEqual(state, changed[STATE_LBAS[1] * 512])
            self.assertEqual(cfg[84:91], bytes.fromhex('8e999a849481e1'))
            self.assertEqual(struct.unpack_from('<H', cfg, 36)[0], 2)
            self.assertEqual(struct.unpack_from('<H', state, 36)[0], 2)
            for i, lba in enumerate((131072, 140000)):
                target = changed[lba * 512]
                self.assertEqual(struct.unpack_from('<Q', cfg, 108 + 52 * i)[0], 0x100000001 + i)
                self.assertEqual(struct.unpack_from('<Q', state, 64 + 64 * i)[0], 0x100000001 + i)
                self.assertEqual(cfg[78 + 52 * i], kind); self.assertEqual(cfg[81 + 52 * i], masks[i])
                self.assertEqual(struct.unpack_from('<I', state, 84 + 64 * i)[0], zlib.crc32(target))
            self.assertEqual(struct.unpack_from('<I', changed[140000 * 512], 28)[0], 140000)
            self.assertEqual(changed[140000 * 512][:28], vbr[:28])
            self.assertEqual(changed[140000 * 512][32:], vbr[32:])

    def test_target_faults_leave_an_independent_second_profile(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        vbr = bytes(510) + b'\x55\xaa'
        _, good = mutate_visibility_fixture(size, original, 'visibility-dos', vbr, 'en')
        _, bad = mutate_visibility_fixture(size, original, 'visibility-vbr-code', vbr, 'en')
        self.assertNotEqual(bad[131072 * 512], good[131072 * 512])
        self.assertEqual(bad[140000 * 512], good[140000 * 512])
        for lba in CFG_LBAS + STATE_LBAS: self.assertEqual(good[lba * 512], bad[lba * 512])
        self.assertEqual(VISIBILITY_CASES['visibility-vbr-code']['plans'][0]['proof'], 15)
        self.assertEqual(VISIBILITY_CASES['visibility-vbr-code']['plans'][1]['types'], [0x16, 6, 0x17, 5])

    def test_failed_preview_rejects_stale_masks_table_profile_and_border(self):
        for language in ('en', 'de'):
            strings = load_catalog(language); data = bytearray(b' \x17' * 2000)
            def text(row, column, value):
                for i, byte in enumerate(value.encode('cp437')): data[(row * 80 + column + i) * 2] = byte
            for row in range(2, 23): data[(row * 80 + 1) * 2] = data[(row * 80 + 78) * 2] = 0xB3
            for row, col, key in ((2,65,'READ_ONLY'), (5,4,'VIS_TITLE'), (6,4,'VIS_SCOPE'),
                                  (8,4,'VIS_BLOCKED'), (9,4,'VIS_CODES'), (13,4,'LBA_HEX'),
                                  (19,4,'VIS_HELP'), (21,4,'KEY_HELP'), (22,4,'FUNCTION_HELP')):
                text(row, col, strings[key])
            text(9,30,'0002 / 0006 / 0000'); text(11,4,strings[PROOF_KEYS[6]]); text(13,23,'00000000')
            data[(8 * 80 + 4) * 2 + 1] = 0x1E
            args = (strings, {}, blocked(6), bytes(512), bytes(512), 0, 0)
            check_visibility_screen(data, *args)
            for row, col, value in ((7,4,'old profile'), (12,17,'06'), (15,30,'03'),
                                     (17,30,'01'), (18,10,'1'), (13,45,'80'), (2,78,'X')):
                good = data[:]; text(row, col, value)
                with self.subTest(language=language, row=row), self.assertRaises(ValueError):
                    check_visibility_screen(data, *args)
                data[:] = good


if __name__ == '__main__': unittest.main()
