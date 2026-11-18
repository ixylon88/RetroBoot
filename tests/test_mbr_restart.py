"""Independent byte-level checks on the published cold-start test media."""
import struct
import unittest
import zlib

from tools.mbr_restart_fixtures import carrier_images, sector_body, witness_floppy


class RestartMediaTests(unittest.TestCase):
    def header(self, img, lba, tag, expected):
        p = img[512*lba:512*(lba+1)]
        self.assertEqual(p[:8], tag)
        self.assertEqual(p[8:24], bytes(15) + b'\x11')
        self.assertEqual(struct.unpack_from('<II', p, 24), (262144, 1))
        self.assertEqual(p[32:48], bytes(15) + b'\x22')
        self.assertEqual(struct.unpack_from('<4I', p, 48), expected)
        self.assertEqual(p[72:508], bytes(436))
        self.assertEqual(int.from_bytes(p[508:], 'little'), zlib.crc32(p[:508]))

    def test_rollback_keeps_the_same_approved_bytes_and_a_valid_older_header(self):
        images = carrier_images()
        latest, older = images['current'], images['older']
        self.assertEqual(len(older), 1474560)
        self.assertEqual(older[:3*512], latest[:3*512])
        self.assertEqual(older[6*512:7*512], latest[6*512:7*512])
        self.header(older, 5, b'RBCMT001', (4, 3, 3, 0))
        self.header(latest, 5, b'RBCMT001', (6, 5, 3, 0))
        self.header(latest, 1, b'RBORG001', (1, 1, 0, 0))
        self.assertNotEqual(latest[510:512], b'\x55\xaa')
        self.assertEqual(latest[2*512+510:3*512], b'\x55\xaa')

    def test_staging_preserves_original_and_selected_slot(self):
        images = carrier_images()
        active, staged = images['current'], images['staged']
        self.assertEqual(active[:3*512], staged[:3*512])
        self.assertEqual(active[5*512:], staged[5*512:])
        self.header(staged, 3, b'RBCMT001', (7, 5, 5, 3))
        self.assertNotEqual(staged[4*512:5*512], active[6*512:7*512])
        self.assertEqual(zlib.crc32(staged[4*512:5*512]), zlib.crc32(active[6*512:7*512]))

    def test_witness_is_a_separate_complete_file_on_the_boot_floppy(self):
        disk = bytearray(1474560)
        disk[19*512+32:19*512+43] = b'RBRESCUEBIN'
        out = witness_floppy(disk)
        self.assertEqual(out[512:10*512], out[10*512:19*512])
        entry = out[19*512+64:19*512+96]
        self.assertEqual(entry[:12], b'RBWITNESBIN\x20')
        self.assertEqual(struct.unpack_from('<HI', entry, 26), (2845, 2048))
        for cluster, link in ((2845,2846), (2846,2847), (2847,2848), (2848,0xfff)):
            word = struct.unpack_from('<H', out, 512 + cluster + cluster // 2)[0]
            self.assertEqual((word >> 4 if cluster & 1 else word) & 0xfff, link)
        self.assertEqual(out[2876*512:2876*512+24], b'RBMEDIA1'+bytes(15)+b'\x33')
        self.header(out, 2877, b'RBWIT001', (6, 5, 3, 0))
        self.assertNotEqual(out[2878*512:2879*512], out[2879*512:])
        self.assertEqual(out[2878*512:2879*512], sector_body(0))
        self.assertEqual(out[2879*512:], sector_body(3))
        disk[19*512+64:19*512+75] = b'FOREIGN DAT'
        with self.assertRaises(ValueError):
            witness_floppy(disk)
