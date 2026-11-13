"""Journal fixture boundaries and independent I/O/VGA evidence checks."""
import struct
import unittest
import zlib

from tools.build_hdd import fixture
from tools.journal_fixtures import JOURNAL_CASES, mutate
from tools.journal_records import baseline
from tools.test_journal import check_journal_screen, check_reads, expected_reads
from tools.ui_text import load_catalog
from test_hdd_tools import samples


class JournalIOToolsTests(unittest.TestCase):
    def test_released_seed_is_bound_to_complete_mbr_and_exact_three_sectors(self):
        size,extents=fixture(samples(),'retroboot-hdd');seeded=baseline(extents,size,126)
        for lba in (13203,13603):
            data=seeded[lba*512]
            self.assertEqual(len(data),1536)
            self.assertEqual(data[512:1024],seeded[0]);self.assertEqual(data[1024:],seeded[0])
            self.assertEqual(struct.unpack_from('<I',data,16)[0],1)
            self.assertEqual(struct.unpack_from('<HH',data,36),(0,1))
            self.assertEqual(struct.unpack_from('<I',data,40)[0],131072)
            self.assertEqual(struct.unpack_from('<I',data,508)[0],zlib.crc32(data[:508]))
        self.assertEqual(set(seeded),set(extents))
        self.assertTrue(all(seeded[k]==v for k,v in extents.items() if k not in (13203*512,13603*512)))

    def test_campaign_has_matching_routes_and_preserves_loader_payload(self):
        size,original=fixture(samples(),'retroboot-hdd')
        for name,spec in JOURNAL_CASES.items():
            with self.subTest(name=name):
                final,changed=mutate(size,original,name);self.assertEqual(final,128*1024*1024)
                self.assertEqual(changed[0][:444],original[0][:444])
                if spec['kind']!='diverged':self.assertEqual(changed[0][444:446],original[0][444:446])
                for offset,data in original.items():
                    if offset not in (0,379*512,11603*512,12003*512,12403*512,12803*512,13203*512,13603*512):self.assertEqual(changed[offset],data)
                self.assertEqual(len(changed[13203*512]),1536);self.assertEqual(len(changed[13603*512]),1536)
                record=changed[13203*512]
                self.assertEqual(struct.unpack_from('<H',record,38)[0],1 if spec['mode']=='EDD' else 2)
                self.assertEqual(struct.unpack_from('<HH',record,72),(0,0) if spec['mode']=='EDD' else (16,63))
        self.assertEqual({s['mode'] for s in JOURNAL_CASES.values()},{'EDD','CHS'})

    def test_read_oracle_rejects_target_payload_padding_stale_maps_and_missing_recheck(self):
        good=expected_reads({},38000,0)
        self.assertEqual(good[-11:],[11603,12003,12403,12803,13203,13204,13205,13603,13604,13605,0])
        check_reads(good,good)
        for bad in (good[:-1],good+[13206],good+[131072],good+[13606],good[:-2]+[0,13605]):
            with self.assertRaises(ValueError):check_reads(bad,good)
        failure=JOURNAL_CASES['journal-io-edd']
        self.assertEqual(expected_reads(failure,38000,0).count(13204),3)
        retry=JOURNAL_CASES['journal-retry-edd']
        self.assertEqual(expected_reads(retry,38000,0).count(13204),2)
        self.assertEqual(expected_reads(retry,38000,1).count(13204),1)
        for kind,reads in (('config',2),('state',4),('media',4)):
            spec=JOURNAL_CASES['journal-'+kind+'-edd'];self.assertEqual(expected_reads(spec,38000,0)[-reads:],[11603,12003,12403,12803][:reads])

    def test_failed_screen_rejects_stale_sequence_crc_and_frame_damage(self):
        spec=JOURNAL_CASES['journal-bad-a-edd']
        for language in ('en','de'):
            strings=load_catalog(language);data=bytearray(b' \x17'*2000)
            def text(row,col,value):
                for i,b in enumerate(value.encode('cp437')):data[(row*80+col+i)*2]=b
            for row in range(2,23):data[(row*80+1)*2]=data[(row*80+78)*2]=0xB3
            for row,col,key in ((2,65,'READ_ONLY'),(5,4,'JOURNAL_TITLE'),(6,4,'JOURNAL_SCOPE'),(8,4,'JOURNAL_INVALID'),
                (9,4,'JOURNAL_LOAD_CODES'),(10,4,'JOURNAL_COPY_CODES'),(17,4,'LBA_HEX'),(19,4,'JOURNAL_HELP'),(20,4,'NO_CHANGES'),(21,4,'KEY_HELP'),(22,4,'FUNCTION_HELP')):text(row,col,strings[key])
            text(9,32,'0000 / 0000');text(10,32,'0009 / 0003 / 0000');text(17,32,'00000000');data[(8*80+4)*2+1]=0x1E
            check_journal_screen(data,strings,spec,(0,0))
            for row,col,value in ((12,32,'00000002'),(14,32,'12345678'),(15,32,'01'),(2,78,'X')):
                good=data[:];text(row,col,value)
                with self.assertRaises(ValueError):check_journal_screen(data,strings,spec,(0,0))
                data[:]=good


if __name__=='__main__':unittest.main()
