"""Independent fixture and trace boundaries for the native capture planner."""
import struct
import unittest
import zlib

from tools.backup_plan_vectors import cases, check_reads, expected_reads, patches, sectors
from tools.config_records import FIXTURE_MEDIA_ID, layout_crc


class BackupPlanTests(unittest.TestCase):
    def test_live_fixture_records_and_vbr_bindings(self):
        for bits, reserved, kind in ((32,32,None),(16,1,None),(16,4,None),
                                     (32,130,None),(32,2035,None),(32,32,0x1B)):
            data=sectors(bits,reserved,kind=kind)
            crc=layout_crc({lba*512:block for lba,block in data.items()})
            for lba in (6257,6457,6657,6857):
                record=data[lba]
                self.assertEqual(record[48:64],FIXTURE_MEDIA_ID)
                self.assertEqual(struct.unpack_from('<IIII',record,20),(0x52425431,crc,126,128457))
                self.assertEqual(zlib.crc32(record[:508]),struct.unpack_from('<I',record,508)[0])
            for lba in (6657,6857):
                self.assertEqual(struct.unpack_from('<I',data[lba],84)[0],zlib.crc32(data[131072]))
            self.assertEqual(struct.unpack_from('<H',data[131072],14)[0],reserved)
            self.assertEqual(data[0][450],kind or (6 if bits==16 else 11))

    def test_two_planning_passes_cover_metadata_and_first_headers_only(self):
        reads=expected_reads()
        self.assertEqual(len(reads),2122)
        self.assertEqual(reads[:1061],reads[1061:])
        self.assertEqual(reads[:529],reads[529:1058])
        self.assertEqual(reads[1058:1061],[131072,126,0])
        self.assertEqual(set(reads),{0,63,126,*range(127,631),6257,6457,6657,6857,131072})
        self.assertTrue(set(reads).isdisjoint({661,697,7057,7257,131073,131078,131103}))

    def test_oracle_rejects_truncation_reordering_and_extra_payload_reads(self):
        reads=expected_reads();check_reads(reads)
        for invalid in (reads[:1061],reads[:-1],reads+[131073],
                        reads[:1058]+[126,131072]+reads[1060:],
                        reads[:529]+reads[530:],reads+[7057]):
            with self.assertRaises(ValueError):check_reads(invalid)

    def test_sparse_seed_and_zero_replacements_are_lossless(self):
        base=sectors()
        def apply(data, edits):
            result={lba:bytearray(block) for lba,block in data.items()}
            for lba,at,value in edits:
                self.assertLessEqual(at,508);self.assertEqual(at%4,0)
                block=result.setdefault(lba,bytearray(512));struct.pack_into('<I',block,at,value)
            return {lba:bytes(block) for lba,block in result.items()}
        restored=apply({},patches({},base))
        self.assertEqual(restored,{lba:block for lba,block in base.items() if any(block)})
        for alternate in (sectors(16,1),sectors(reserved=2036),{0:bytes(512)}):
            restored=apply(base,patches(base,alternate))
            for lba,block in alternate.items():self.assertEqual(restored[lba],block)

    def test_budget_boundaries_and_io_oracles(self):
        vectors={c['name']:c for c in cases()}
        self.assertEqual(len(vectors),len(cases()))
        maximum=vectors['exact-container-limit']
        self.assertEqual((maximum['status'],maximum['reserved']+7+6),(0,2048))
        self.assertEqual(vectors['container-one-sector-too-large']['status'],5)
        self.assertGreater(vectors['over-64k-reserved-area']['reserved']*512,65536)
        reads=expected_reads()
        for c in vectors.values():
            if c['io']:
                self.assertEqual(c['reads'],c['io'])
                self.assertEqual(c['lba'],reads[c['io']-1])
        self.assertEqual(sum(bool(c['io']) for c in vectors.values()),26)


if __name__ == '__main__':
    unittest.main()
