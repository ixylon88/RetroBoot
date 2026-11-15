"""Independent fixture and trace boundaries for the native capture planner."""
import struct
import unittest
import zlib

from tools.backup_plan_vectors import cases, check_reads, expected_reads, patches, sectors
from tools.config_records import FIXTURE_MEDIA_ID, layout_crc


class BackupPlanTests(unittest.TestCase):
    def test_link_vectors_select_independent_generations_and_last_profile(self):
        base=sectors();vectors={c['name']:c for c in cases()}
        def record(case,lba):
            data=bytearray(base[lba])
            for sector,at,value in case['patches']:
                if sector==lba:struct.pack_into('<I',data,at,value)
            self.assertEqual(zlib.crc32(data[:508]),struct.unpack_from('<I',data,508)[0])
            return data
        for family,lbas,offset in (('config',(6257,6457),108),('state',(6657,6857),64)):
            for copy,lba in enumerate(lbas):
                older=vectors[f'older-{family}-{copy}-unlinked']
                self.assertEqual(older['status'],0)
                bad,new=(record(older,n) for n in (lba,lbas[1-copy]))
                self.assertEqual(struct.unpack_from('<I',bad,16)[0],1)
                self.assertEqual(struct.unpack_from('<I',new,16)[0],2)
                self.assertNotEqual(bad[offset:offset+8],new[offset:offset+8])
                selected=vectors[f'selected-{family}-{copy}-unlinked']
                self.assertEqual((selected['status'],selected['detail'],selected['reads']),(2,11,528))
                self.assertEqual(struct.unpack_from('<I',record(selected,lba),16)[0],2)
        last=vectors['last-profile-unlinked'];config=record(last,6257)
        self.assertEqual((last['status'],last['detail'],last['nested'],last['lba']),(2,11,7,131072))
        self.assertEqual(struct.unpack_from('<H',config,36)[0],8)
        self.assertEqual([struct.unpack_from('<I',config,64+i*52)[0] for i in range(8)],list(range(1,9)))
        self.assertTrue(all(config[108+i*52:116+i*52]==base[6257][108:116] for i in range(7)))
        self.assertNotEqual(config[472:480],base[6257][108:116])

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
            self.assertTrue(all(131072+i in data for i in range(reserved)))
            if bits==32:
                self.assertEqual(data[131078],data[131072])
                self.assertEqual(data[131080],data[131074])

    def test_two_planning_passes_cover_metadata_and_complete_reserved_areas(self):
        reads=expected_reads()
        self.assertEqual(len(reads),2188)
        self.assertEqual(reads[:1094],reads[1094:])
        self.assertEqual(reads[:529],reads[529:1058])
        self.assertEqual(reads[1058:1094],[131072,126,*range(131072,131104),126,0])
        self.assertEqual(set(reads),{0,63,126,*range(127,631),6257,6457,6657,6857,*range(131072,131104)})
        self.assertTrue(set(reads).isdisjoint({661,697,7057,7257,131104}))

    def test_oracle_rejects_truncation_reordering_and_extra_payload_reads(self):
        reads=expected_reads();check_reads(reads)
        for invalid in (reads[:1094],reads[:-1],reads+[131073],
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
            for lba,block in alternate.items():self.assertEqual(restored.get(lba,bytes(512)),block)

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
        self.assertEqual(sum(bool(c['io']) for c in vectors.values()),42)
        self.assertEqual(maximum['reads'],6194)
        self.assertEqual(vectors['container-one-sector-too-large']['reads'],1060)
        self.assertEqual(vectors['reserved-count-changes-after-sizing']['reads'],1061)


if __name__ == '__main__':
    unittest.main()
