"""Verify new header fixtures do not corrupt the bootable management volume."""

import struct
import unittest

from test_hdd_tools import samples
from tools.build_hdd import fixture
from tools.volume_fixtures import FIRST_LBA, SECOND_LBA, VOLUME_BYTES, VOLUME_CASES, mutate_volume_fixture


class VolumeFixtureTests(unittest.TestCase):
    def test_all_fixtures_preserve_loader_and_mbr_identity(self):
        size, original = fixture(samples(), "retroboot-hdd")
        snapshot = dict(original)
        for name in VOLUME_CASES:
            with self.subTest(name=name):
                length, changed = mutate_volume_fixture(size, original, name)
                self.assertEqual(length, VOLUME_BYTES)
                self.assertEqual(changed[0][:446], original[0][:446])
                self.assertEqual(changed[0][510:], original[0][510:])
                for offset, data in original.items():
                    if offset:
                        self.assertEqual(changed[offset], data)
                self.assertEqual(original, snapshot)

    def test_new_volumes_do_not_overlap_original_container_or_each_other(self):
        size, original = fixture(samples(), "retroboot-hdd")
        length, changed = mutate_volume_fixture(size, original, "volume-headers")
        entries = [struct.unpack_from("<II", changed[0], 454 + i * 16) for i in range(4)]
        for i, (start, count) in enumerate(entries):
            self.assertGreater(count, 0)
            self.assertLessEqual(start + count, 261072)  # default 128 MiB QEMU CHS reach
            self.assertLessEqual((start + count) * 512, length)
            for other_start, other_count in entries[:i]:
                self.assertTrue(start + count <= other_start or other_start + other_count <= start)

    def test_header_reference_values_and_no_fake_filesystem(self):
        size, original = fixture(samples(), "retroboot-hdd")
        _, changed = mutate_volume_fixture(size, original, "volume-headers")
        for start, total, fat, roots, reserved, clusters in ((FIRST_LBA, 5073, 20, 32, 1, 5000),
                                                           (SECOND_LBA, 71126, 547, 0, 32, 70000)):
            b = changed[start * 512]
            self.assertEqual(struct.unpack_from("<II", b, 28), (start, total))
            self.assertEqual(total - reserved - 2 * fat - roots, clusters)
            self.assertEqual(b[510:], b"\x55\xaa")
        additions = set(changed) - set(original)
        self.assertEqual(additions, {FIRST_LBA * 512, SECOND_LBA * 512})
        self.assertEqual(changed[SECOND_LBA * 512][90:510], bytes(420))

    def test_invalid_fixture_or_base_size_is_rejected(self):
        size, original = fixture(samples(), "retroboot-hdd")
        with self.assertRaises(ValueError):
            mutate_volume_fixture(size, original, "unknown")
        with self.assertRaises(ValueError):
            mutate_volume_fixture(1, original, "volume-headers")


if __name__ == "__main__":
    unittest.main()
