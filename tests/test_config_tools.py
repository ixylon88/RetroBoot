"""Independent binary offsets, allocation preservation and VGA rejection checks."""
import hashlib
import struct
import unittest
import zlib

from tools.build_hdd import fixture, layout
from tools.config_records import CLUSTERS, encode, install_records, layout_crc, model_record
from tools.config_fixtures import CONFIG_CASES, FILE_LBAS, mutate_config_fixture
from tools.ui_text import load_catalog
from tools.test_config import check_config_screen
from test_hdd_tools import samples


class ConfigurationToolsTests(unittest.TestCase):
    def test_exact_host_to_native_vector_and_cp437(self):
        data = model_record()
        self.assertEqual(len(data), 512)
        self.assertEqual(data[:16].hex(), '52424346470000000100400000020000')
        self.assertEqual(struct.unpack_from('<IIIIIII', data, 16)[:5],
                         (100, 0x52425431, 0x420CE91C, 126, 128457))
        self.assertEqual(data[84:91], bytes.fromhex('8e999a849481e1'))
        self.assertEqual(data[96:108], bytes(12))
        self.assertEqual(data[112:508], bytes(396))
        self.assertEqual(zlib.crc32(data[:508]), 0x21BBF2B8)
        self.assertEqual(struct.unpack_from('<I', data, 508)[0], 0x21BBF2B8)
        self.assertEqual(hashlib.sha256(data).hexdigest(), '44df4d3acc8a0ead2864fe7ecae11a5bd0ae825019554c8be8e4dc2dff214643')

    def test_fingerprint_changes_with_structure_but_not_hidden_active_or_chs(self):
        _, _, extents = layout(True)
        fingerprint = layout_crc(extents)
        changed = dict(extents); mbr = bytearray(changed[0])
        mbr[446] ^= 0x80; mbr[450] ^= 0x10; mbr[447] ^= 1
        changed[0] = bytes(mbr)
        self.assertEqual(layout_crc(changed), fingerprint)
        for offset in (454, 458, 502):
            changed = dict(extents); mbr = bytearray(changed[0]); mbr[offset] ^= 1; changed[0] = bytes(mbr)
            if offset == 502:
                with self.assertRaises(KeyError): layout_crc(changed)
            else: self.assertNotEqual(layout_crc(changed), fingerprint)
        changed = dict(extents); ebr = bytearray(changed[11518605 * 512]); ebr[454] ^= 1
        changed[11518605 * 512] = bytes(ebr)
        self.assertNotEqual(layout_crc(changed), fingerprint)

    def test_single_cluster_records_have_two_fats_and_fixed_directory_sizes(self):
        _, extents = fixture(samples(), 'retroboot-hdd')
        root = extents[379 * 512]
        for i, (cluster, lba) in enumerate(zip(CLUSTERS, FILE_LBAS)):
            entry = root[672 + i * 32:704 + i * 32]
            self.assertEqual(entry[:11], b'RBCFG   ' + bytes([65 + i]) + b'  ')
            self.assertEqual(struct.unpack_from('<HI', entry, 26), (cluster, 512))
            for fat in (127, 253):
                self.assertEqual(struct.unpack_from('<H', extents[fat * 512], cluster * 2)[0], 0xFFFF)
            self.assertEqual(len(extents[lba * 512]), 512)
            self.assertEqual(struct.unpack_from('<I', extents[lba * 512], 24)[0], layout_crc(extents))
        self.assertEqual(extents[FILE_LBAS[0] * 512], extents[FILE_LBAS[1] * 512])

    def test_fixture_failures_preserve_loader_files_and_other_allocations(self):
        size, original = fixture(samples(), 'retroboot-hdd')
        vbr = bytes(510) + b'\x55\xaa'
        for name in CONFIG_CASES:
            with self.subTest(name=name):
                new_size, changed = mutate_config_fixture(size, original, name, vbr, 'de')
                self.assertEqual(new_size, 128 * 1024 * 1024)
                self.assertEqual(changed[0][:446], original[0][:446])
                self.assertEqual(changed[126 * 512], original[126 * 512])
                self.assertEqual(changed[379 * 512][:672], original[379 * 512][:672])
                for fat in (127, 253):
                    for cluster in (2, 20, 300, 40):
                        at = cluster * 2
                        self.assertEqual(changed[fat * 512][at:at + 2], original[fat * 512][at:at + 2])
                for lba in (411, 483, 1603, 563): self.assertEqual(changed[lba * 512], original[lba * 512])

    def test_producer_rejects_ambiguous_names_invalid_fields_and_overlapping_allocation(self):
        args = dict(disk_id=1, layout=0, admin_start=126, admin_sectors=128457)
        profile = dict(id=1, name='test', slot=1, type=6, start=131072, sectors=5073)
        for changes in ({'generation': 0}, {'generation': 1 << 32}, {'disk_id': 0}, {'countdown': 61},
                        {'language': 'fr'}, {'default_id': 1}, {'profiles': [profile] * 9}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): encode(**(args | changes))
        for changes in ({'name': 'x\n'}, {'name': 'x\x7f'}, {'name': '€'}, {'name': 'x' * 25},
                        {'slot': 0}, {'slot': 5}, {'approved': 1}, {'visible_mask': 3}, {'type': 7},
                        {'start': 0}, {'sectors': 0xFFFFFFFF}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): encode(**args, profiles=[profile | changes])
        _, admin, _ = layout(False); _, extents = fixture(samples(), 'retroboot-hdd')
        with self.assertRaises(ValueError): install_records(extents, admin)

    def test_failure_page_cannot_contain_stale_entry_or_overwrite_border(self):
        strings = load_catalog('en'); data = bytearray(b' \x17' * 2000)
        def text(row, column, value):
            for i, byte in enumerate(value.encode('cp437')): data[(row * 80 + column + i) * 2] = byte
        for row in range(2, 23):
            data[(row * 80 + 1) * 2] = data[(row * 80 + 78) * 2] = 0xB3
        for row, col, key in ((2,65,'READ_ONLY'), (5,4,'CONFIG_TITLE'), (6,4,'CONFIG_SCOPE'),
                              (8,4,'CONFIG_COPIES'), (9,4,'CONFIG_CRC'), (11,4,'LBA_HEX'),
                              (12,4,'CONFIG_DETAIL'), (19,4,'CONFIG_HELP'),
                              (21,4,'KEY_HELP'), (22,4,'FUNCTION_HELP')): text(row,col,strings[key])
        text(8,29,'0004 / 0004'); text(11,23,'00000000'); text(12,29,'0000')
        spec = {'status':4,'copies':[4,4]}
        check_config_screen(data, strings, spec, bytes(512), 0)
        text(13,4,'old profile')
        with self.assertRaises(ValueError): check_config_screen(data, strings, spec, bytes(512), 0)


if __name__ == '__main__': unittest.main()
