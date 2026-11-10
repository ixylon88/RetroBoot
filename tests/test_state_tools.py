"""Independent state/v2 field offsets, identity separation and allocation checks."""
import struct
import unittest
import zlib

from tools.build_hdd import fixture
from tools.config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, encode as config
from tools.state_records import encode, PHASES
from tools.state_fixtures import STATE_CASES, FILE_LBAS, mutate_state_fixture
from test_hdd_tools import samples


class StateToolsTests(unittest.TestCase):
    binding = dict(disk_id=0x52425431, layout=0x420CE91C, admin_start=126, admin_sectors=128457)
    entry = dict(install_id=TEST_INSTALL_ID, slot=1, type=6, start=131072, sectors=5073, phase=6, vbr_crc=0x12345678)

    def test_state_binary_offsets_and_independent_crc(self):
        data = encode(**self.binding, installations=[self.entry])
        self.assertEqual(len(data), 512)
        self.assertEqual(data[:16].hex(), '52425354415445000100400000020000')
        self.assertEqual(struct.unpack_from('<IIIIIIH', data, 16), (1, 0x52425431, 0x420CE91C, 126, 128457, 1, 0))
        self.assertEqual(data[38:48], bytes(10))
        self.assertEqual(data[48:64], FIXTURE_MEDIA_ID)
        self.assertEqual(struct.unpack_from('<QIIBBBBI', data, 64), (TEST_INSTALL_ID, 131072, 5073, 1, 6, 1, 6, 0x12345678))
        self.assertEqual(data[88:508], bytes(420))
        self.assertEqual(struct.unpack_from('<I', data, 508)[0], zlib.crc32(data[:508]))

    def test_all_seven_phases_and_duplicate_rejection(self):
        self.assertEqual(len(PHASES), 7)
        for phase in range(1, 8):
            data = encode(**self.binding, installations=[self.entry | dict(phase=phase, vbr_crc=0)])
            self.assertEqual(data[83], phase)
        for patch in ({'phase': 0}, {'phase': 8}, {'phase': 5}, {'install_id': 0},
                      {'install_id': 1 << 64}, {'slot': 5}, {'type': 0x16}, {'kind': 3}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                encode(**self.binding, installations=[self.entry | patch])
        for second in (self.entry, self.entry | dict(install_id=2), self.entry | dict(slot=2)):
            with self.assertRaises(ValueError): encode(**self.binding, installations=[self.entry, second])
        for patch in ({'media_id': bytes(16)}, {'media_id': b'x'}, {'generation': 0}, {'generation': 1 << 32}):
            with self.assertRaises(ValueError): encode(**(self.binding | patch))

    def test_v2_eight_profiles_and_legacy_preserved(self):
        p = dict(self.entry, id=1, name='ÄÖÜäöüß', installed=2, approved=1)
        profiles = [p | dict(id=i + 1) for i in range(8)]
        data = config(**self.binding, profiles=profiles, media_id=FIXTURE_MEDIA_ID)
        self.assertEqual(data[8:10], b'\x02\x00'); self.assertEqual(data[48:64], FIXTURE_MEDIA_ID)
        for i in range(8):
            self.assertEqual(data[84 + i * 52:91 + i * 52], bytes.fromhex('8e999a849481e1'))
            self.assertEqual(struct.unpack_from('<Q', data, 108 + i * 52)[0], TEST_INSTALL_ID)
        self.assertEqual(data[480:508], bytes(28))
        self.assertEqual(struct.unpack_from('<I', data, 508)[0], zlib.crc32(data[:508]))
        self.assertEqual(config(**self.binding, profiles=[p])[8:10], b'\x01\x00')
        with self.assertRaises(ValueError): config(**self.binding, profiles=[p | dict(install_id=0)], media_id=FIXTURE_MEDIA_ID)

    def test_newer_record_does_not_reuse_old_installation_or_media_identity(self):
        size, original = fixture(samples(), 'retroboot-hdd'); vbr = bytes(510) + b'\x55\xaa'
        for name, offset, length in (('state-install-newer', 64, 8), ('state-media-newer', 48, 16)):
            _, changed = mutate_state_fixture(size, original, name, vbr, 'en')
            a, b = (changed[lba * 512] for lba in FILE_LBAS)
            self.assertEqual(struct.unpack_from('<I', b, 16)[0], 2)
            self.assertNotEqual(a[offset:offset + length], b[offset:offset + length])
            self.assertEqual(struct.unpack_from('<I', b, 508)[0], zlib.crc32(b[:508]))

    def test_state_fault_fixtures_preserve_loader_and_configuration_allocation(self):
        size, original = fixture(samples(), 'retroboot-hdd'); vbr = bytes(510) + b'\x55\xaa'
        for name in STATE_CASES:
            with self.subTest(name=name):
                _, changed = mutate_state_fixture(size, original, name, vbr, 'de')
                self.assertEqual(changed[0][:446], original[0][:446])
                self.assertEqual(changed[379 * 512][:736], original[379 * 512][:736])
                for lba in (126, 411, 483, 1603, 563): self.assertEqual(changed[lba * 512], original[lba * 512])
                for fat in (127, 253):
                    self.assertEqual(changed[fat * 512][:6000], original[fat * 512][:6000])


if __name__ == '__main__': unittest.main()
