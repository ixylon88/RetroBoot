"""Independent F9 fixture/receipt prerequisites and failure-page hygiene."""
import struct
import unittest
import zlib

from tools.build_hdd import fixture
from tools.profile_fixtures import PROFILE_CASES, FILE_LBAS, mutate_profile_fixture, expected_preview
from tools.config_fixtures import FILE_LBAS as CFG_LBAS
from tools.ui_text import load_catalog
from tools.test_profile import check_rejection
from test_hdd_tools import samples


class ProfileTestToolsTests(unittest.TestCase):
    def test_fixtures_preserve_loader_and_management_allocation(self):
        size, original=fixture(samples(),'retroboot-hdd');vbr=bytes(510)+b'\x55\xaa'
        for name in PROFILE_CASES:
            with self.subTest(name=name):
                new_size, changed=mutate_profile_fixture(size,original,name,vbr,'en')
                self.assertEqual(new_size,64*1024*1024 if name=='profile-empty' else 128*1024*1024)
                self.assertEqual(changed[0][:446],original[0][:446])
                self.assertEqual(changed[0][494:],original[0][494:])
                for lba in (126,127,253,379,411,483,1603,563):
                    self.assertEqual(changed[lba*512],original[lba*512])

    def test_substituted_sector_has_matching_state_crc_but_different_test_bytes(self):
        size, original=fixture(samples(),'retroboot-hdd');vbr=bytes(510)+b'\x55\xaa'
        _, changed=mutate_profile_fixture(size,original,'profile-vbr-substituted',vbr,'en')
        current=changed[131072*512]
        self.assertEqual(current[:509],vbr[:509]);self.assertEqual(current[510:],vbr[510:])
        self.assertNotEqual(current[509],vbr[509])
        for lba in FILE_LBAS:
            record=changed[lba*512]
            self.assertEqual(struct.unpack_from('<I',record,84)[0],zlib.crc32(current))
            self.assertNotEqual(struct.unpack_from('<I',record,84)[0],zlib.crc32(vbr))
            self.assertEqual(struct.unpack_from('<I',record,508)[0],zlib.crc32(record[:508]))
        self.assertEqual(expected_preview(PROFILE_CASES['profile-vbr-substituted'])['plans'][0]['status'],0)
        self.assertEqual(PROFILE_CASES['profile-vbr-substituted']['status'],5)

    def test_selected_alias_is_not_the_first_entry(self):
        size, original=fixture(samples(),'retroboot-hdd');vbr=bytes(510)+b'\x55\xaa'
        _, changed=mutate_profile_fixture(size,original,'profile-ready',vbr,'de')
        cfg=changed[CFG_LBAS[0]*512]
        self.assertEqual(struct.unpack_from('<H',cfg,36)[0],2)
        self.assertEqual(struct.unpack_from('<I',cfg,64)[0],1)
        self.assertEqual(struct.unpack_from('<I',cfg,116)[0],2)
        self.assertEqual(cfg[84:91],bytes.fromhex('8e999a849481e1'))
        self.assertNotEqual(cfg[84:108],cfg[136:160])
        self.assertEqual(cfg[108:116],cfg[160:168])
        self.assertEqual(PROFILE_CASES['profile-ready']['selected'],1)

    def test_rejection_page_contains_no_stale_plan_or_launch_hint(self):
        for language in ('en','de'):
            strings=load_catalog(language);data=bytearray(b' \x17'*2000)
            def text(row,col,value):
                for i,b in enumerate(value.encode('cp437')):data[(row*80+col+i)*2]=b
            for row in range(2,23):data[(row*80+1)*2]=data[(row*80+78)*2]=0xB3
            for row,col,key in ((2,65,'READ_ONLY'),(5,4,'PROFILE_TEST_FAILED'),(6,4,'PROFILE_TEST_SELECTION'),
                               (8,4,'PROFILE_TEST_REASON'),(14,4,'LBA_HEX'),(17,4,'NO_CHANGES'),
                               (19,4,'PROFILE_TEST_REVIEW'),(21,4,'KEY_HELP'),(22,4,'FUNCTION_HELP')):
                text(row,col,strings[key])
            text(10,4,'0001 / 0000 / 0000');text(14,23,'00000000');data[(6*80+4)*2+1]=0x1E
            check_rejection(data,strings,1,{})
            for row,col,value in ((7,4,'old profile'),(11,17,'06'),(15,30,'01'),
                                  (20,4,strings['PROFILE_TEST_HELP']),(2,78,'X')):
                good=data[:];text(row,col,value)
                with self.subTest(language=language,row=row), self.assertRaises(ValueError):
                    check_rejection(data,strings,1,{})
                data[:]=good


if __name__=='__main__':unittest.main()
