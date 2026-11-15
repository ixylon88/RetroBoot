import struct
import unittest
import zlib

from tools.backup_container import InvalidBackup, inspect
from tools.backup_encode_vectors import cases, sources
from tools.backup_vectors import materialize


class BackupEncodeTests(unittest.TestCase):
    def test_native_oracles_and_table_boundaries(self):
        images = sources()
        for case in cases():
            with self.subTest(case=case['name']):
                data = materialize(images[case['source']], case)
                try:
                    inspect(data)
                    status = 0
                except InvalidBackup as error:
                    status = error.status
                self.assertEqual(status, case['decoded'])
        self.assertEqual([len(inspect(data)[1]) for data in images[4:11]],
                         [7, 15, 16, 17, 31, 32, 33])
        self.assertEqual(len(inspect(images[3])[1]), 42)
        self.assertEqual(len(images[2]), 1024 * 1024)
        self.assertGreater(inspect(images[1])[1][3]['sectors'] * 512, 65536)

    def test_wide_fields_have_literal_little_endian_bytes(self):
        data = sources()[11]
        self.assertEqual(data[:12], b'RBBAK\0\0\0\x01\0\0\x02')
        self.assertEqual(data[16:32], bytes.fromhex('40 30 20 10 80 70 60 50 C0 B0 A0 90 40 30 20 10'))
        self.assertEqual(data[48:56], bytes.fromhex('05 04 03 02 01 00 00 00'))
        self.assertEqual(data[56:72], bytes.fromhex('A6 21 6F 34 5C D2 46 77 90 AB C0 13 7D 84 52 E9'))
        self.assertEqual(data[608:612], b'\x04\0\0\0')
        self.assertEqual(data[612:616], bytes.fromhex('40 30 20 10'))
        self.assertEqual(data[628:632], bytes.fromhex('40 30 20 10'))
        self.assertEqual(data[72:76], struct.pack('<I', zlib.crc32(data[512:2560])))
        self.assertEqual(data[508:512], struct.pack('<I', zlib.crc32(data[:508])))
        self.assertEqual(data[76:508], bytes(432))
        self.assertEqual(data[512 + 8 * 32:2560], bytes(2048 - 8 * 32))

    def test_framing_does_not_verify_payload_crc_claims(self):
        base = sources()[0]
        claims = [c for c in cases() if c['name'].startswith('payload-crc-')]
        self.assertEqual(len(claims), 2)
        for case in claims:
            data = materialize(base, case)
            self.assertEqual(case['expected'], 0)  # The framing encoder accepts the claim.
            self.assertEqual(data[2560:], base[2560:])
            self.assertEqual(struct.unpack_from('<I', data, 72)[0], zlib.crc32(data[512:2560]))
            self.assertEqual(struct.unpack_from('<I', data, 508)[0], zlib.crc32(data[:508]))
            with self.assertRaises(InvalidBackup) as error:
                inspect(data)
            self.assertEqual(error.exception.status, 3)
