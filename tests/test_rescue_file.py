"""Independent FAT12 packing, read bounds and file-page evidence checks."""
import struct
import unittest

from tools.backup_boot_vectors import fixture
from tools.backup_container import InvalidBackup, inspect
from tools.rescue_file_fixtures import ROOT, put_backup, make_fixture, file_chain, specifications, expected_file_reads
from tools.rescue_text import load_catalog
from tools.test_rescue import check_file_screen, floppy_reads
from tools.build_rescue import make_image
from tests.test_rescue_tools import boot, payload


def original():
    return make_image(boot(),payload(23001))


class RescueFileTests(unittest.TestCase):
    def test_fragmented_file_round_trip_and_loader_isolation(self):
        base=original();data=fixture();image,clusters=put_backup(base,data)
        mapping=file_chain(image)
        self.assertEqual(mapping,[c+31 for c in clusters])
        self.assertEqual(clusters[:4],[341,700,340,2848])
        self.assertEqual(b''.join(image[lba*512:(lba+1)*512] for lba in mapping),data)
        self.assertEqual(image[512:5120],image[5120:9728])
        self.assertEqual(image[:512],base[:512])
        self.assertEqual(image[33*512:33*512+23001],base[33*512:33*512+23001])
        self.assertEqual(image[ROOT+64:ROOT+76],b'RBBACKUPRBB\x20')
        self.assertEqual(struct.unpack_from('<HI',image,ROOT+90),(341,len(data)))

    def test_maximum_file_mapping_and_invalid_sizes(self):
        image,clusters=put_backup(original(),bytes(1048576))
        mapping=file_chain(image)
        self.assertEqual(len(mapping),2048)
        self.assertEqual(len(set(mapping)),2048)
        self.assertTrue(all(33<=n<2880 for n in mapping))
        self.assertEqual(mapping[-1],clusters[-1]+31)
        for data in (bytes(2048),bytes(2561),bytes(1049088)):
            with self.assertRaises(ValueError):put_backup(original(),data)
        with self.assertRaises(ValueError):put_backup(bytes(512),fixture())

    def test_directory_terminators_duplicates_and_lfn_fixtures(self):
        base=original()
        for name,slot in (('file-late-root',17),('file-last-root',223),('file-lfn',4)):
            image=make_fixture(base,name)
            self.assertEqual(image[ROOT+slot*32:ROOT+slot*32+11],b'RBBACKUPRBB')
            self.assertNotIn(0,[image[ROOT+n*32] for n in range(slot)])
            self.assertEqual(len(file_chain(image)),45)
        image=make_fixture(base,'file-duplicate')
        self.assertEqual(image[ROOT+64:ROOT+96],image[ROOT+96:ROOT+128])
        self.assertEqual(make_fixture(base,'file-missing'),base)

    def test_corruptions_preserve_executable_payload_and_expected_boundaries(self):
        base=original()
        for name in specifications():
            image=make_fixture(base,name)
            self.assertEqual(len(image),1474560)
            self.assertEqual(image[33*512:33*512+23001],base[33*512:33*512+23001])
        for name in ('file-loop','file-short','file-long','file-free','file-bad-cluster'):
            with self.subTest(name=name),self.assertRaises(ValueError):file_chain(make_fixture(base,name))
        for name in ('file-container-crc','file-fsinfo'):
            image=make_fixture(base,name)
            data=b''.join(image[lba*512:(lba+1)*512] for lba in file_chain(image))
            if name=='file-container-crc':
                with self.assertRaises(InvalidBackup):inspect(data)
            else:inspect(data)

    def test_physical_read_oracles_include_recheck_and_bounded_retries(self):
        base=original()
        for name in specifications():
            reads=expected_file_reads(make_fixture(base,name),name)
            self.assertTrue(all(0<=lba<2880 for lba in reads),name)
        image=make_fixture(base,'file-demo')
        reads=expected_file_reads(image,'file-demo')
        self.assertEqual(reads[:33],list(range(33)))
        self.assertEqual(reads[-33:],list(range(33)))
        self.assertEqual(reads[33:78],file_chain(image))
        self.assertIn(2879,reads)
        self.assertEqual(expected_file_reads(image,'file-root-io'),list(range(19))+[19]*3)
        self.assertEqual(expected_file_reads(image,'file-retry',1),reads)
        self.assertEqual(len(expected_file_reads(image,'file-retry',0)),len(reads)+1)
        self.assertEqual(floppy_reads('%0000\n%0B3F\n@02\n'),[0,2879])

    def test_failed_file_page_rejects_stale_success_counters(self):
        s=load_catalog('en');spec=specifications()['file-missing'];data=bytearray(b' \x17'*2000)
        def put(row,col,value):
            for i,c in enumerate(value.encode('cp437')):data[2*(row*80+col+i)]=c
        for row in range(2,23):
            if row!=4:data[2*(row*80+1)]=data[2*(row*80+78)]=0xB3
        for row,col,value in ((2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['B_SCOPE']),
                (6,4,s['B_LIMIT']),(8,4,s['B_MISSING']),(9,4,s['B_CODES']),(9,32,'0x0005 / 0x0000 / 0x0000'),
                (10,4,s['B_NESTED']),(10,32,'0x0000'),(16,4,s['B_FILE_LBA']),(16,32,'0x00000000'),
                (17,4,s['B_DISK_LBA']),(17,32,'0x00000000'),(18,4,s['B_EXTENT']),(18,32,'0x0000 / 0x0000'),
                (21,4,s['B_HELP']),(22,4,s['B_BOUNDARY'])):put(row,col,value)
        data[2*(8*80+4)+1]=0x1E
        check_file_screen(data,s,spec)
        for row in (12,13,14):
            bad=bytearray(data);bad[2*(row*80+32)]=ord('2')
            with self.assertRaises(ValueError):check_file_screen(bad,s,spec)


if __name__=='__main__':unittest.main()
