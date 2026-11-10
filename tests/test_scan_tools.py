"""Keep scanner fixtures separate from loader corruption and real media."""

import struct
import unittest

from tools.build_hdd import fixture
from tools.scan_fixtures import LONG_EBRS, SCAN_CASES, TAIL_LIMIT, mutate_scan_fixture
from test_hdd_tools import samples


class ScanFixtureTests(unittest.TestCase):
    def test_mutations_preserve_loader_payloads_and_mbr_identity(self):
        size, original = fixture(samples(), "retroboot-hdd")
        snapshot = dict(original)
        for name in SCAN_CASES:
            with self.subTest(case=name):
                changed = mutate_scan_fixture(size, original, name)
                self.assertEqual(changed[0][:446], original[0][:446])
                self.assertEqual(changed[0][510:], b"\x55\xaa")
                for offset, data in original.items():
                    if offset not in (0, 63 * 512):
                        self.assertEqual(changed[offset], data)
                self.assertEqual(original, snapshot)

    def test_long_chain_uses_unused_tail_and_both_relative_address_bases(self):
        size, original = fixture(samples(), "retroboot-hdd")
        changed = mutate_scan_fixture(size, original, "scan-many")
        self.assertEqual(len(LONG_EBRS), 16)
        self.assertEqual(struct.unpack_from("<II", changed[0], 502), (63, TAIL_LIMIT - 63))
        for index, lba in enumerate(LONG_EBRS):
            block = changed[lba * 512]
            if index:
                self.assertGreater(lba, 126 + 128457 - 1)
                self.assertEqual(struct.unpack_from("<II", block, 454), (1, 10))
            if index + 1 < len(LONG_EBRS):
                self.assertEqual(struct.unpack_from("<I", block, 470)[0] + 63, LONG_EBRS[index + 1])
            else:
                self.assertEqual(block[462:478], bytes(16))

    def test_unknown_fixture_is_rejected(self):
        size, original = fixture(samples(), "retroboot-hdd")
        with self.assertRaises(ValueError):
            mutate_scan_fixture(size, original, "not-a-scan-case")


if __name__ == "__main__":
    unittest.main()
