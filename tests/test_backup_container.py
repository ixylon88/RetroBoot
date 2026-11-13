"""Container corruption, canonical extents, bounds and read-only inspection."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from tools.backup_container import Chunk, InvalidBackup, encode, inspect, inspect_file
from tools.backup_vectors import cases, fixture, materialize, model_header, sources


class BackupContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = sources()

    def test_independent_wire_offsets_and_round_trip(self):
        data = self.sources[0]
        self.assertEqual(len(data), 44 * 512)
        self.assertEqual(data[:16], b'RBBAK\0\0\0\x01\0\0\x02\0\x58\0\0')
        self.assertEqual(data[36:48], bytes.fromhex('08 00 20 00 01 00 00 00 00 00 00 00'))
        self.assertEqual(data[56:72].hex(), 'a6216f345cd2467790abc0137d8452e9')
        self.assertEqual(struct.unpack_from('<HH7I', data, 512), (1, 0, 0, 1, 5, zlib.crc32(data[2560:3072]), 0, 0, 0))
        self.assertEqual(struct.unpack_from('<HH3I', data, 608), (4, 0, 126, 32, 8))
        self.assertEqual(data[768:2560], bytes(1792))
        self.assertEqual(zlib.crc32(data[:508]), struct.unpack_from('<I', data, 508)[0])
        self.assertEqual(zlib.crc32(data[512:2560]), struct.unpack_from('<I', data, 72)[0])
        identity, entries = inspect(data)
        chunks = [Chunk(e['kind'], e['index'], e['lba'], data[e['file_sector']*512:(e['file_sector']+e['sectors'])*512],
                        e['owner_start'], e['owner_sectors']) for e in entries]
        self.assertEqual(encode(identity, chunks), data)
        self.assertEqual(identity.capacity, 300000)

    def test_resealed_malformed_vectors_and_payload_corruption(self):
        for case in cases():
            if case['fail_sector'] != 0xFFFF:
                continue  # Reader failures are exercised by the native model.
            with self.subTest(case=case['name']):
                data = materialize(self.sources[case['source']], case)
                if case['expected']:
                    with self.assertRaises(InvalidBackup) as caught:
                        inspect(data)
                    self.assertEqual(caught.exception.status, case['expected'])
                else:
                    inspect(data)

    def test_every_header_table_and_payload_byte_is_protected(self):
        # All byte positions, including padding and both complete MBR copies.
        data = self.sources[0]
        for offset in range(len(data)):
            bad = bytearray(data)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(InvalidBackup):
                inspect(bad)

    def test_truncation_extension_and_non_sector_file_are_rejected(self):
        data = self.sources[0]
        for length in (0, 511, 512, 2559, 2560, len(data)-512, len(data)-1):
            with self.subTest(length=length), self.assertRaises(InvalidBackup):
                inspect(data[:length])
        for extra in (b'\0', bytes(512), bytes(2048*512)):
            with self.assertRaises(InvalidBackup):
                inspect(data + extra)

    def test_large_boot_regions_and_maximum_descriptor_count(self):
        for data, expected_count in zip(self.sources, (8, 8, 8, 42)):
            _, entries = inspect(data)
            self.assertEqual(len(entries), expected_count)
        self.assertEqual(inspect(self.sources[1])[1][3]['sectors'], 130)
        self.assertEqual(len(self.sources[2]), 1024*1024)
        self.assertEqual(inspect(self.sources[3])[1][37]['index'], 19)
        with self.assertRaises(InvalidBackup):
            fixture(2037)

    def test_each_required_role_is_required(self):
        data = self.sources[0]
        identity, entries = inspect(data)
        chunks = [Chunk(e['kind'], e['index'], e['lba'], data[e['file_sector']*512:(e['file_sector']+e['sectors'])*512],
                        e['owner_start'], e['owner_sectors']) for e in entries]
        for kind in (1, 2, 4, 5, 6, 7, 8):
            with self.subTest(kind=kind), self.assertRaises(InvalidBackup) as caught:
                encode(identity, [chunk for chunk in chunks if chunk.kind != kind])
            self.assertEqual(caught.exception.status, 7)
        # A primary-only layout has no EBR; absence is structurally permitted.
        inspect(encode(identity, [chunk for chunk in chunks if chunk.kind != 3]))
        for media in (b'', bytes(15), bytes(17), bytes(16)):
            with self.subTest(media=media), self.assertRaises(InvalidBackup):
                encode(replace(identity, media_id=media), chunks)

    def test_encoder_rejects_unaligned_empty_and_out_of_range_inputs(self):
        identity = inspect(self.sources[0])[0]
        for chunk in (Chunk(1, 0, 0, b'x'), Chunk(1, 0, 0, b''), Chunk(1, 0, -1, bytes(512)),
                      Chunk(65536, 0, 0, bytes(512)), Chunk(1, 0, 1 << 32, bytes(512))):
            with self.subTest(chunk=chunk), self.assertRaises(InvalidBackup):
                encode(identity, [chunk])
        for chunks in ([], [Chunk(1, 0, 0, bytes(512))] * 43):
            with self.assertRaises(InvalidBackup):
                encode(identity, chunks)

    def test_inspector_only_reads_regular_bounded_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.rbb'
            path.write_bytes(self.sources[0])
            inspect_file(path)
            run = subprocess.run([sys.executable, '-m', 'tools.backup_container', str(path)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(run.stdout)
            self.assertEqual(report['validation'], 'container-integrity-only')
            self.assertFalse(report['live_media_match'])
            self.assertFalse(report['restore_authorized'])
            self.assertEqual(path.read_bytes(), self.sources[0])
            with self.assertRaises(ValueError):
                inspect_file(Path(tmp))
            path.write_bytes(bytes(2048*512 + 1))
            with self.assertRaises(InvalidBackup):
                inspect_file(path)

    def test_native_seeds_are_reproducible_and_small(self):
        header = model_header()
        self.assertEqual(header, model_header())
        self.assertTrue(header.isascii())
        self.assertEqual(header.count('[2560]'), 4)


if __name__ == '__main__':
    unittest.main()
