"""Independent payload byte, read-order and mutation oracles."""
import struct
import unittest
import zlib

from tools.backup_payload_vectors import (
    PAYLOAD_PASS, case_data, cases, check_reads, expected_reads, payload_crcs,
    payload_reads,
)


class BackupPayloadTests(unittest.TestCase):
    def test_exact_extent_crc_oracle_and_large_ranges(self):
        vectors = {c['name']: c for c in cases()}
        self.assertEqual(payload_crcs(vectors['fat32-edd']), [
            0x4878B9CD, 0x18AAED8C, 0xD49A4683, 0x013A13BA,
            0x2144DF1C, 0x2144DF1C, 0x2144DF1C, 0x2144DF1C,
        ])
        for name in ('over-64k-reserved-area', 'exact-container-limit'):
            case = vectors[name]
            data = case_data(case)
            area = b''.join(data.get(131072+i, bytes(512)) for i in range(case['reserved']))
            self.assertGreater(len(area), 65536)
            self.assertEqual(payload_crcs(case)[2], zlib.crc32(area))
            self.assertNotEqual(payload_crcs(case)[2], zlib.crc32(area[:65536]))
        self.assertEqual(vectors['exact-container-limit']['reserved']+7+6, 2048)
        self.assertEqual(vectors['exact-container-limit']['reads'], 10278)
        self.assertEqual(vectors['container-one-sector-too-large']['reads'], 1060)

    def test_reads_follow_validations_twice_and_cover_only_planned_payload(self):
        reads = expected_reads()
        self.assertEqual((PAYLOAD_PASS, len(reads)), (1133, 2266))
        self.assertEqual(reads[:1133], reads[1133:])
        payload = [0, 63, *range(131072,131104), 126, 6257, 6457, 6657, 6857]
        self.assertEqual(payload_reads(), payload)
        self.assertEqual(reads[1093:1132], payload)
        self.assertEqual(reads[1132], 0)
        self.assertTrue(set(payload).isdisjoint({629, 661, 697, 7057, 7257, 131104}))
        check_reads(reads)
        for bad in (reads[:-1], reads[:1133], reads+[0],
                    reads[:1093]+list(reversed(payload))+reads[1132:]):
            with self.assertRaises(ValueError):
                check_reads(bad)

    def test_every_payload_sector_has_first_and_second_pass_io_faults(self):
        vectors = cases()
        self.assertEqual(len({c['name'] for c in vectors}), len(vectors))
        faults = [c for c in vectors if c['name'].startswith('payload-io-')]
        self.assertEqual(len(faults), 78)
        reads = expected_reads()
        for c in faults:
            self.assertEqual(c['status'], 10)
            self.assertEqual(c['reads'], c['io'])
            self.assertEqual(reads[c['io']-1], c['lba'])
        self.assertEqual({c['lba'] for c in faults}, set(payload_reads()))

    def test_transient_resealed_records_have_equal_whole_crc_but_changed_bodies(self):
        vectors = {c['name']: c for c in cases()}
        for outer in (0, 1):
            c = vectors[f'transient-{outer}-resealed-tail-outer']
            before, after = case_data(c, changed=False), case_data(c)
            self.assertEqual((c['status'], c['reads']), (6, 2266))
            self.assertEqual((c['start'], c['stop']), (outer*1133+1094, (outer+1)*1133))
            for lba in (6257, 6457):
                self.assertNotEqual(before[lba], after[lba])
                self.assertEqual(zlib.crc32(before[lba]), zlib.crc32(after[lba]))
                self.assertNotEqual(zlib.crc32(before[lba][:508]), zlib.crc32(after[lba][:508]))
                for record in (before[lba], after[lba]):
                    self.assertEqual(zlib.crc32(record[:508]), struct.unpack_from('<I', record,508)[0])


if __name__ == '__main__':
    unittest.main()
