"""Independent boundaries for the native live-target acquisition model."""
import re
import struct
import unittest
import zlib

from tools.backup_target_vectors import check_reads, expected_reads
from tools.journal_records import io_model_header


class BackupTargetTests(unittest.TestCase):
    def test_fixture_records_bind_same_media_and_layout(self):
        arrays = {name: bytes(map(int, re.findall(r'\d+', data))) for name, data in
                  re.findall(r'static const rb_u8 (\w+)\[\d+\] = \{(.*?)\};', io_model_header(), re.S)}
        journal, config, state = (arrays[name] for name in ('rb_io_journal', 'rb_io_config', 'rb_io_state'))
        self.assertEqual(config[48:64], state[48:64])
        self.assertEqual(config[48:64], journal[48:64])
        self.assertEqual(struct.unpack_from('<III', config, 24),
                         struct.unpack_from('<III', state, 24))
        self.assertEqual(struct.unpack_from('<II', config, 28), (126, 5285))
        self.assertEqual(struct.unpack_from('<II', journal, 40), (262144, 0))
        for record in (config, state):
            self.assertEqual(zlib.crc32(record[:508]), struct.unpack_from('<I', record, 508)[0])
        self.assertEqual(journal[512 + 432:512 + 436], b'RBM1')
        self.assertEqual(struct.unpack_from('<II', journal, 512 + 436), (126, 0x52425431))

    def test_two_complete_acquisitions_have_bounded_read_sets(self):
        reads = expected_reads()
        self.assertEqual(len(reads), 542)
        self.assertEqual(reads[:271], reads[271:])
        self.assertEqual(reads[:6], [0, 0, 63, 126, 379, 380])
        self.assertEqual(reads[266:271], [3209, 3309, 3409, 3509, 0])
        self.assertTrue(set(range(127, 379)) <= set(reads))
        self.assertEqual(set(reads), {0, 63, 126, *range(127, 381), 3209, 3309, 3409, 3509})
        # No program contents, journal payloads or system-volume VBRs are read.
        self.assertTrue(set(reads).isdisjoint({411, 429, 3609, 3709, 131072, 140000}))

    def test_oracle_rejects_omitted_rechecks_and_unowned_reads(self):
        reads = expected_reads()
        check_reads(reads)
        for malformed in (reads[:271], reads[:-1], reads + [131072],
                          reads[:266] + [3609] + reads[267:],
                          reads[:7] + reads[8:], reads[1:] + [0]):
            with self.assertRaises(ValueError):
                check_reads(malformed)


if __name__ == '__main__':
    unittest.main()
