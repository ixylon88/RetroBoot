"""Wire oracles for reopening the actual C/16 destination."""
import unittest
import zlib

from tools.backup_container import inspect
from tools.backup_verify_vectors import alternatives, wire
from tools.rescue_plan_fixtures import disk


class CompletedBackupTests(unittest.TestCase):
    def test_ordinary_and_segment_crossing_outputs(self):
        _, extents = disk()
        small = wire()
        self.assertEqual(len(small), 45 * 512)
        self.assertEqual(len(wire(130)), 143 * 512)
        identity, entries = inspect(small)
        self.assertEqual(identity.capacity, 262144)
        for entry in entries:
            start = entry['file_sector'] * 512
            data = small[start:start + entry['sectors']*512]
            self.assertEqual(zlib.crc32(data), entry['crc32'])
            if entry['kind'] > 2:
                self.assertEqual(data, extents[entry['lba']*512][:len(data)])
        original, approved = small[5*512:6*512], small[6*512:7*512]
        self.assertNotEqual(original, approved)
        self.assertNotIn(extents[0], (original, approved))
        self.assertEqual(approved[432:436], b'RBM1')
        _, large = inspect(wire(130))
        self.assertEqual(large[-1]['file_sector'], 142)
        self.assertEqual(next(x['sectors'] for x in large if x['lba'] == 131072), 130)

    def test_resealed_files_reach_the_intended_readers(self):
        data = wire()
        altered = alternatives(data)
        with self.assertRaises(ValueError):
            inspect(altered['overlap'])
        for name in ('boot_area', 'saved_state', 'changed_config', 'sub_original', 'sub_approved'):
            with self.subTest(name=name):
                self.assertNotEqual(data, altered[name])
                self.assertEqual(inspect(data)[0], inspect(altered[name])[0])
        for name, pos in (('sub_original', 5), ('sub_approved', 6), ('changed_config', 41)):
            at = slice(pos * 512, (pos + 1)*512)
            self.assertNotEqual(data[at], altered[name][at])
            self.assertEqual(zlib.crc32(data[at]), zlib.crc32(altered[name][at]))
            self.assertEqual(data[:pos*512], altered[name][:pos*512])
            self.assertEqual(data[(pos+1)*512:], altered[name][(pos+1)*512:])

    def test_incomplete_extended_or_damaged_outputs(self):
        data = wire()
        for damaged in (data[:-512], data[:-1], data + b'x', data + bytes(512),
                        data[:-1] + bytes([data[-1] ^ 1])):
            with self.assertRaises(ValueError):
                inspect(damaged)


if __name__ == '__main__':
    unittest.main()
