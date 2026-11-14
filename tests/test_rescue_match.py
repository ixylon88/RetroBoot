"""Independent fixture ownership, composition reads and failed-screen checks."""
from dataclasses import replace
import struct
import unittest
import zlib

from tools.backup_container import inspect
from tools.config_records import FIXTURE_MEDIA_ID
from tools.rescue_match_fixtures import backup, disk, acquisition, specs, floppy, hdd_reads, floppy_reads
from tools.rescue_file_fixtures import file_chain
from tools.rescue_text import load_catalog
from tools.test_rescue_match import check_match_screen, check_discovery_calls
from tools.build_rescue import make_image
from tests.test_rescue_tools import boot, payload


class RescueMatchTests(unittest.TestCase):
    def test_live_fixture_has_closed_allocation_and_independent_record_locations(self):
        raw=backup();identity,entries=inspect(raw);size,extents=disk()
        self.assertEqual(size,128*1024*1024)
        self.assertEqual((identity.capacity,identity.admin_start,identity.admin_sectors),(262144,126,128457))
        self.assertEqual(identity.media_id,FIXTURE_MEDIA_ID)
        self.assertEqual(extents[0][:432],bytes(432))
        self.assertNotIn(131072*512,extents) # no OS or system-volume code
        self.assertEqual(extents[127*512],extents[378*512])
        fat=extents[127*512];root=extents[629*512];used=[];first=[]
        for slot in (0,20,21,22,23,24,25,26):
            c,n=struct.unpack_from('<HI',root,slot*32+26);first.append(c);chain=[]
            while c<0xFFF8:
                self.assertNotIn(c,used);used.append(c);chain.append(c)
                c=struct.unpack_from('<H',fat,c*2)[0]
            self.assertEqual(len(chain),(n+1023)//1024)
        self.assertEqual(len(used),15)
        self.assertEqual({i for i in range(2,63963) if struct.unpack_from('<H',fat,i*2)[0]},set(used))
        live=[661+(c-2)*2 for c in first[2:6]]
        self.assertEqual(live,[6257,6457,6657,6857])
        claimed=[e['lba'] for e in entries if e['kind'] in (5,6,7,8)]
        self.assertTrue(set(live).isdisjoint(claimed))
        for lba,e in zip(live,[e for e in entries if e['kind'] in (5,6,7,8)]):
            self.assertEqual(extents[lba*512],raw[e['file_sector']*512:(e['file_sector']+1)*512])
        vbr=extents[126*512]
        self.assertEqual(vbr[62:66],b'RBV1');self.assertEqual(sum(struct.unpack('<256H',vbr))&65535,0)

    def test_failure_fixtures_change_only_the_intended_metadata(self):
        size,base=disk()
        expected={'capacity':set(),'bad-mbr':{0},'missing-file':{629*512},
            'fat-copies':{378*512},'unowned':{127*512,378*512},
            'config-crc':{6257*512},'state-crc':{6657*512},
            'identity':{n*512 for n in (6257,6457,6657,6857)},
            'layout':{n*512 for n in (0,6257,6457,6657,6857)}}
        for name,changed in expected.items():
            length,data=disk(name)
            self.assertEqual(length,size+(512 if name=='capacity' else 0))
            self.assertEqual(data.keys(),base.keys())
            self.assertEqual({k for k in base if data[k]!=base[k]},changed)
        for name in ('identity','layout'):
            data=disk(name)[1]
            for lba in (6257,6457,6657,6857):
                record=data[lba*512]
                self.assertEqual(zlib.crc32(record[:508]),struct.unpack_from('<I',record,508)[0])

    def test_read_oracles_cover_two_acquisitions_and_full_file_revalidation(self):
        reads=acquisition();self.assertEqual(len(reads),529)
        self.assertEqual(reads[:6],[0,0,63,126,629,630])
        self.assertEqual(reads[-5:],[6257,6457,6657,6857,0])
        self.assertEqual(set(reads),{0,63,126,*range(127,631),6257,6457,6657,6857})
        base=make_image(boot(),payload(30001));all_specs=specs()
        s=all_specs['match'];image=floppy(base,s);mapping=file_chain(image)
        self.assertEqual(b''.join(image[n*512:(n+1)*512] for n in mapping),backup())
        f=floppy_reads(image,s)
        self.assertEqual(len(f),267);self.assertEqual(f[:33],list(range(33)))
        self.assertEqual(f[33:150],f[150:]);self.assertEqual(f[-33:],list(range(33)))
        self.assertEqual(hdd_reads(s),reads*2)
        calls=['41','48']+['42']*1058+['41','48']
        check_discovery_calls(''.join('@'+c+'\n' for c in calls),s)
        for wrong in (calls[2:],calls[:-2],['41','08']+calls[2:]):
            with self.assertRaises(ValueError):check_discovery_calls(''.join('@'+c+'\n' for c in wrong),s)
        for name in ('no-hdd','missing-backup','bad-backup','bad-saved-boot','capacity','geometry'):
            self.assertEqual(hdd_reads(all_specs[name]),[])
        self.assertEqual(hdd_reads(all_specs['mbr-io']),[0,0,0])
        self.assertEqual(hdd_reads(all_specs['record-io'])[-3:],[6257]*3)
        bad=all_specs['changed-file'];self.assertEqual(len(floppy_reads(floppy(base,bad),bad)),151)

    def test_resealed_source_is_valid_but_changes_the_generation(self):
        original,changed=backup(),backup(generation=2)
        a,_=inspect(original);b,_=inspect(changed)
        self.assertEqual(replace(a,generation=2),b)
        self.assertEqual(original[512:],changed[512:])
        self.assertNotEqual(original[:256],changed[:256])
        # A whole-sector CRC alone cannot detect this legitimate rewrite.
        self.assertEqual(zlib.crc32(original[:512]),zlib.crc32(changed[:512]))
        chs,_=inspect(backup(True));self.assertEqual((chs.capacity,chs.route,chs.heads,chs.sectors_per_track),(261072,2,16,63))

    def test_failed_match_page_rejects_stale_identity_and_geometry(self):
        s=load_catalog('en');spec=specs()['missing-backup'];data=bytearray(b' \x17'*2000)
        def put(row,col,value):
            for i,c in enumerate(value.encode('cp437')):data[2*(row*80+col+i)]=c
        for row in range(2,23):
            if row!=4:data[2*(row*80+1)]=data[2*(row*80+78)]=0xB3
        for row,col,value in ((2,4,s['TITLE']),(2,65,s['READ_ONLY']),(5,4,s['T_SCOPE']),
            (6,4,s['T_LIMIT']),(8,4,s['B_MISSING']),(9,4,s['T_CODES']),(9,32,'0001 / 0005 / 0000'),
            (10,4,s['B_NESTED']),(10,32,'0000'),(18,4,s['B_FILE_LBA']),(18,32,'00000000'),
            (19,4,s['T_LBA']),(19,32,'00000000'),(21,4,s['T_HELP']),(22,4,s['T_BOUNDARY'])):put(row,col,value)
        data[2*(8*80+4)+1]=0x1E;check_match_screen(data,s,spec)
        for row in range(11,18):
            bad=bytearray(data);bad[2*(row*80+32)]=ord('1')
            with self.assertRaises(ValueError):check_match_screen(bad,s,spec)


if __name__=='__main__':unittest.main()
