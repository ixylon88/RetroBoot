import struct
import unittest
import zlib

from tools.backup_container import inspect
from tools.backup_stream_vectors import cases, sources
from tools.backup_vectors import pattern


class BackupStreamTests(unittest.TestCase):
    def test_complete_wire_oracles_and_distinct_mbr_sources(self):
        images = sources()
        for number, image in enumerate(images):
            identity, entries = inspect(image)
            for entry in entries:
                for pos in range(entry['file_sector'], entry['file_sector'] + entry['sectors']):
                    expected = bytearray(pattern(pos))
                    if number == 4 and pos == 43:
                        struct.pack_into('<I', expected, 508, zlib.crc32(expected[:508]))
                    self.assertEqual(image[pos*512:(pos+1)*512], expected)
            self.assertNotEqual(image[5*512:6*512], image[6*512:7*512])
        self.assertGreater(len(images[1]), 65536)
        self.assertEqual(len(images[2]), 1024*1024)
        self.assertEqual(len(inspect(images[3])[1]), 42)
        self.assertEqual(inspect(images[5])[0].capacity, 0x0102030405)
        self.assertEqual(inspect(images[6])[0].route, 2)

    def test_every_read_and_output_boundary_can_fail(self):
        vectors = cases()
        for phase in (0, 1):
            errors = [c for c in vectors if c['name'].startswith(f'read-{phase}-')]
            self.assertEqual([c['pos'] for c in errors], list(range(5, 44)))
            self.assertEqual([c['reads'] for c in errors], list(range(phase*39+1, (phase+1)*39+1)))
            self.assertEqual([c['sinks'] for c in errors], list(range(5, 44)) if phase else [0]*39)
        errors = [c for c in vectors if c['name'].startswith('sink-')]
        self.assertEqual([c['pos'] for c in errors], list(range(44)))
        self.assertEqual([c['sinks'] for c in errors], list(range(1, 45)))
        self.assertTrue(all(c['reads'] == c['sinks'] == 0 for c in vectors
                            if c['name'].startswith(('framing-', 'null-'))))

    def test_resealed_last_sector_requires_body_tail_comparison(self):
        block = sources()[4][-512:]
        changed = bytearray(block)
        changed[400] ^= 1
        struct.pack_into('<I', changed, 508, zlib.crc32(changed[:508]))
        self.assertNotEqual(changed, block)
        self.assertEqual(zlib.crc32(changed), zlib.crc32(block))
        self.assertNotEqual(zlib.crc32(changed[:508]), zlib.crc32(block[:508]))
        failures = [c for c in cases() if c['name'].startswith('resealed-last-')]
        self.assertEqual([c['at'] for c in failures], [39, 78])
        self.assertTrue(all(c['status'] == 5 and c['sinks'] == 44 for c in failures))
