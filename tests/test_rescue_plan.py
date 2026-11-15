"""Independent live fixture, read boundary and failed-result display checks."""
import unittest

from tools.backup_boot_vectors import fixture
from tools.backup_container import inspect
from tools.rescue_match_fixtures import disk as old_disk, acquisition
from tools.rescue_plan_fixtures import disk, specs, hdd_reads, ranges, SYSTEM
from tools.rescue_text import load_catalog
from tools.test_rescue_plan import check_discovery, check_plan_screen


class RescuePlanTests(unittest.TestCase):
    def test_published_target_adds_only_the_saved_synthetic_reserved_area(self):
        size,base=old_disk();length,data=disk()
        self.assertEqual(size,length)
        self.assertEqual({k:data[k] for k in base},base)
        self.assertEqual(set(data)-set(base),{SYSTEM*512})
        raw=fixture();_,entries=inspect(raw)
        e=next(e for e in entries if e['kind']==4 and e['lba']==SYSTEM)
        self.assertEqual(data[SYSTEM*512],raw[e['file_sector']*512:(e['file_sector']+e['sectors'])*512])
        self.assertEqual(len(data[SYSTEM*512]),32*512)
        self.assertEqual(data[0][:432],bytes(432))
        self.assertEqual(sum(count for _,_,count in ranges()),39)
        self.assertEqual((39+6)*512,23040)

    def test_plan_reads_only_first_vbr_and_discovers_twice(self):
        cases=specs();reads=hdd_reads(cases['plan'])
        self.assertEqual(len(reads),2122)
        self.assertEqual(reads,(acquisition()*2+[SYSTEM,126,0])*2)
        self.assertTrue(set(range(SYSTEM+1,SYSTEM+32)).isdisjoint(reads))
        calls=['41','48']+['42']*len(reads)+['41','48']
        text=lambda c:''.join('@'+n+'\n' for n in c)
        check_discovery(text(calls),cases['plan'])
        for wrong in (calls[2:],calls[:-2],['41','08']+calls[2:]):
            with self.assertRaises(ValueError):check_discovery(text(wrong),cases['plan'])
        self.assertEqual(hdd_reads(cases['no-hdd']),[])
        self.assertEqual(hdd_reads(cases['mbr-io']),[0,0,0])
        self.assertEqual(hdd_reads(cases['vbr-io']),acquisition()*2+[SYSTEM]*3)
        self.assertEqual(hdd_reads(cases['failed-reprobe']),reads)

    def test_unread_reserved_sector_cannot_be_certified_by_this_plan(self):
        size,good=disk();length,bad=disk('reserved-unread')
        self.assertEqual(size,length)
        self.assertNotEqual(good[SYSTEM*512],bad[SYSTEM*512])
        def sector(extents,lba):
            for at,block in extents.items():
                offset=lba*512-at
                if 0<=offset<len(block):return block[offset:offset+512]
            return bytes(512)
        for lba in set(hdd_reads(specs()['plan'])):
            self.assertEqual(sector(good,lba),sector(bad,lba))

    def test_failed_page_rejects_any_retained_size_or_range(self):
        for language in ('en','de'):
            s=load_catalog(language);spec=specs()['failed-reprobe'];data=bytearray(b' \x17'*2000)
            def put(row,col,value):
                for i,c in enumerate(value.encode('cp437')):data[2*(row*80+col+i)]=c
            for row in range(2,23):
                if row!=4:data[2*(row*80+1)]=data[2*(row*80+78)]=0xB3
            for row,col,value in ((2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['P_SCOPE']),
                (6,4,s['P_LIMIT']),(8,4,s['PARAMS']),(9,4,s['P_CODES']),
                (9,32,'0x0002 / 0x0000 / 0x0000 / 0x0000'),(10,4,s['P_ERROR']),
                (10,32,'0x00000000 / 0x0000'),(21,4,s['P_HELP']),(22,4,s['P_BOUNDARY'])):put(row,col,value)
            data[2*(8*80+4)+1]=0x1E;check_plan_screen(data,s,spec,0)
            for row in range(11,20):
                bad=bytearray(data);bad[2*(row*80+32)]=ord('1')
                with self.assertRaises(ValueError):check_plan_screen(bad,s,spec,0)


if __name__=='__main__':unittest.main()
