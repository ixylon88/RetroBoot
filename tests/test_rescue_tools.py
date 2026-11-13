"""Independent FAT12 vectors, rescue limits and diagnostic evidence checks."""
import json
import struct
import unittest
import zlib

from tools.build_rescue import fat12_set, hdd_fixture, inspect_payload, make_image, seal_payload
from tools.rescue_text import load_catalog, output_name, render_header, unique_keys, validate
from tools.test_rescue import check_screen, expected_reads, trace_reads


def payload(size=847):
    data=bytearray((i*7)&255 for i in range(size));data[:6]=b'\xeb\x1eRBRS'
    struct.pack_into('<HII8H',data,6,32,size,0,0x1000,32,1,size,size+32,0xE000,0xFFFE,0)
    return seal_payload(data)


def boot():
    data=bytearray(512)
    # Literal BPB for 1440 KiB FAT12, independent of the production packer.
    data[11:36]=bytes.fromhex('00 02 01 01 00 02 e0 00 40 0b f0 09 00 12 00 02 00 00 00 00 00 00 00 00 00')
    data[510:]=b'\x55\xaa';return data


class RescueToolsTests(unittest.TestCase):
    def test_fat12_image_has_two_equal_fats_and_a_readable_contiguous_file(self):
        p=payload(9501);image=make_image(boot(),p)
        self.assertEqual(len(image),1474560)
        self.assertEqual(image[:512],boot())
        self.assertEqual(image[512:5120],image[5120:9728])
        fat=image[512:5120];self.assertEqual(fat[:3],b'\xf0\xff\xff')
        root=image[9728:16896]
        self.assertEqual(root[:12],b'RB RESCUE  \x08')
        self.assertEqual(root[32:44],b'RBRESCUEBIN\x20')
        self.assertEqual(struct.unpack_from('<HI',root,58),(2,len(p)))
        self.assertEqual(struct.unpack_from('<H',root,56)[0],0x21)
        self.assertEqual(root[64:],bytes(len(root)-64))
        cluster=2;chain=[];file=bytearray()
        while cluster<0xFF8:
            self.assertNotIn(cluster,chain);chain.append(cluster)
            file+=image[(cluster+31)*512:(cluster+32)*512]
            pair=int.from_bytes(fat[cluster*3//2:cluster*3//2+2],'little')
            cluster=(pair>>4 if cluster&1 else pair)&0xFFF
        self.assertEqual(chain,list(range(2,21)))
        self.assertEqual(file[:len(p)],p);self.assertEqual(file[len(p):],b'\xa5'*(-len(p)%512))
        self.assertEqual(image[(33+len(chain))*512:],bytes(1474560-(33+len(chain))*512))
        bad=boot();bad[13]=2
        with self.assertRaises(ValueError):make_image(bad,p)

    def test_fat12_packed_entries_preserve_neighbours_and_cross_sector_boundary(self):
        fat=bytearray(4608);fat12_set(fat,0,0x123);fat12_set(fat,1,0x456)
        self.assertEqual(fat[:3],bytes.fromhex('23 61 45'))
        fat12_set(fat,0,0xABC);self.assertEqual(fat[:3],bytes.fromhex('bc 6a 45'))
        fat12_set(fat,340,0x135);fat12_set(fat,341,0xABC);fat12_set(fat,342,0x246)
        self.assertEqual(fat[510:515],bytes.fromhex('35 c1 ab 46 02'))
        fat12_set(fat,2848,0xFFF);self.assertEqual(fat[4272:4274],b'\xff\x0f')
        for cluster,value in ((-1,0),(2849,0),(2,-1),(2,4096)):
            with self.subTest(cluster=cluster,value=value),self.assertRaises(ValueError):fat12_set(fat,cluster,value)

    def test_header_crc_and_memory_budget_are_validated_before_image_creation(self):
        p=payload();self.assertEqual(inspect_payload(p)['file_bytes'],847)
        self.assertEqual(struct.unpack_from('<I',p,12)[0],zlib.crc32(p[32:]))
        for offset in (0,1,2,6,8,10,16,18,20,26,28,30):
            bad=bytearray(p);bad[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):inspect_payload(bad)
        for offset,value in ((22,846),(24,847),(24,0xE001)):
            bad=bytearray(p);struct.pack_into('<H',bad,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):inspect_payload(bad)
        inspect_payload(payload(0xC000))
        with self.assertRaises(ValueError):payload(0xC001)
        with self.assertRaises(ValueError):inspect_payload(bytes(32))
        bad=bytearray(p);bad[40]^=1
        with self.assertRaisesRegex(ValueError,'Unsealed'):make_image(boot(),bad)
        self.assertEqual(seal_payload(p),p)

    def test_rescue_fixture_contains_only_mbr_and_ebr_metadata(self):
        size,extents=hdd_fixture('metadata-only')
        self.assertEqual(size,64*1024*1024);self.assertEqual(set(extents),{0,63*512})
        mbr,ebr=extents[0],extents[63*512]
        self.assertEqual(mbr[:432],bytes(432));self.assertEqual(mbr[432:436],b'RBM1')
        self.assertEqual(mbr[510:],b'\x55\xaa');self.assertEqual(ebr[:446],bytes(446))
        self.assertEqual(struct.unpack_from('<I',mbr,440)[0],0x52425431)
        self.assertEqual(mbr[450],0);self.assertEqual(mbr[498],5)
        unknown=hdd_fixture('unknown-code')[1][0]
        self.assertEqual(unknown[:440],b'\xcc'*440);self.assertEqual(unknown[440:],mbr[440:])
        self.assertEqual(hdd_fixture('erased-mbr')[1][0],bytes(512))
        self.assertEqual(hdd_fixture('loop-ebr')[1][63*512][466],5)
        with self.assertRaises(ValueError):hdd_fixture('../disk')

    def test_read_oracle_and_failed_screen_reject_stale_evidence(self):
        self.assertEqual(expected_reads({},0),[0,63,0])
        self.assertEqual(expected_reads(dict(fault_once=True),0),[0,0,63,0])
        self.assertEqual(expected_reads(dict(fault_once=True),1),[0,63,0])
        self.assertEqual(expected_reads(dict(status=4),0),[0,0,0])
        self.assertEqual(expected_reads(dict(layout=2),0),[0,0])
        self.assertEqual(expected_reads(dict(fault_lba=63),0),[0,63,63,63,0])
        for status in (1,2,3):self.assertEqual(expected_reads(dict(status=status),0),[])
        trace='ide_sector_read sector=0 nsectors=1\nide_sector_read sector=63 nsectors=1\n'
        self.assertEqual(trace_reads(trace),[0,63])
        with self.assertRaises(ValueError):trace_reads(trace.replace('nsectors=1','nsectors=2'))
        s=load_catalog('en');data=bytearray(b' \x17'*2000)
        def put(row,col,value):
            for i,c in enumerate(value.encode('cp437')):data[2*(row*80+col+i)]=c
        for row in range(2,23):
            if row!=4:
                data[2*(row*80+1)]=0xB3;data[2*(row*80+78)]=0xB3
        for row,col,value in ((2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['SCOPE']),
                (6,4,s['LIMIT']),(8,4,s['NO_DISK']),(9,4,s['CODES']),(9,32,'0001 / 0000'),
                (11,4,s['DRIVES']),(11,32,'0000 / 0080'),(19,4,s['LBA']),(19,32,'00000000'),
                (21,4,s['HELP']),(22,4,s['IDENTITY'])):put(row,col,value)
        data[2*(8*80+4)+1]=0x1E
        def check(d):check_screen(d,s,1,dict(status=1),'EDD',0,(0,0),bytes(512))
        check(data)
        for offset in (2*(15*80+32),2*(16*80+32),2*(17*80+32),2*(18*80+32),2*(2*80+78),2*(8*80+4)+1):
            bad=bytearray(data);bad[offset]=ord('X')
            with self.subTest(offset=offset),self.assertRaises(ValueError):check(bad)

    def test_catalog_encoding_bounds_and_output_isolation(self):
        self.assertIn('ß',load_catalog('de')['HELP']);self.assertTrue(render_header('de').isascii())
        for language in ('en','de'):
            s=load_catalog(language);validate(s)
            for text in ('','a\n','a\x7f','€','x'*29):
                with self.subTest(text=text),self.assertRaises(ValueError):validate(dict(s,CODES=text))
        s=load_catalog('en');del s['HELP']
        with self.assertRaises(ValueError):validate(s)
        with self.assertRaises(ValueError):validate(dict(load_catalog('en'),UNKNOWN='x'))
        with self.assertRaises(ValueError):json.loads('{"HELP":"a","HELP":"b"}',object_pairs_hook=unique_keys)
        self.assertIn('\\341',render_header('de'))
        self.assertEqual(len({output_name(k,l) for k in ('rescue','rescue-repeat','rescue-test') for l in ('en','de')}),6)
        for kind,language in (('../rescue','en'),('hdd','en'),('rescue','../de')):
            with self.assertRaises(ValueError):output_name(kind,language)


if __name__=='__main__':unittest.main()
