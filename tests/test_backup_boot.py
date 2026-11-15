"""Independent fixture and native-transfer evidence for saved boot-area checks."""
import struct
import unittest
import zlib

from tools.backup_container import inspect
from tools.backup_record_vectors import entries, seal
from tools.backup_boot_vectors import cases, fixture, materialize, model_data, model_header, payload, sources


def sector(data,relative):
    for e in entries(data):
        if e[0]==4 and e[2]<=131072+relative<e[2]+e[3]:
            pos=(e[4]+131072+relative-e[2])*512
            return data[pos:pos+512]
    raise AssertionError('Missing test boot sector')


class BackupBootTests(unittest.TestCase):
    def test_supported_fixture_bounds_and_backups(self):
        for data in sources():
            identity, descriptors=inspect(data)
            self.assertEqual(identity.capacity,262144)
            first=sector(data,0)
            reserved=struct.unpack_from('<H',first,14)[0]
            extents=[e for e in entries(data) if e[0]==4 and e[6]==131072]
            self.assertEqual(sum(e[3] for e in extents),reserved)
            self.assertEqual({e[6:8] for e in extents},{(131072,struct.unpack_from('<I',first,32)[0])})
            if struct.unpack_from('<H',first,22)[0]==0:
                backup=struct.unpack_from('<H',first,50)[0]
                self.assertEqual(struct.unpack_from('<H',first,48)[0],1)
                if backup:
                    for rel in range(3):
                        self.assertEqual(sector(data,rel),sector(data,backup+rel))
                self.assertEqual([sector(data,r)[510:] for r in range(3)],[b'\x55\xaa']*3)
            self.assertEqual(struct.unpack_from('<I',data,payload(data,7)+84)[0],zlib.crc32(first))
        self.assertGreater(len(sources()[3]),65536)
        self.assertEqual([e[2] for e in entries(sources()[2]) if e[0]==4],[126,131075,131072])

    def test_semantic_failures_keep_all_checksums_valid(self):
        for case in cases():
            with self.subTest(name=case['name']):
                data=materialize(case)
                inspect(data)
                for kind in range(5,9):
                    pos=payload(data,kind)
                    self.assertEqual(zlib.crc32(data[pos:pos+508]),struct.unpack_from('<I',data,pos+508)[0])

    def test_stale_hints_are_not_boot_copy_conflicts(self):
        case=next(c for c in cases() if c['name']=='stale-backup-hints')
        data=materialize(case)
        self.assertEqual(case['status'],0)
        self.assertEqual(struct.unpack_from('<II',sector(data,1),488),(123,456))
        self.assertEqual(struct.unpack_from('<II',sector(data,7),488),(0xFFFFFFFF,0xFFFFFFFF))
        self.assertEqual(sector(data,0),sector(data,6))
        self.assertEqual(sector(data,2),sector(data,8))

    def test_reopening_after_late_failure_uses_distinct_boot_copies(self):
        vectors=cases()
        self.assertEqual(vectors[-2]['name'],'over-64k-last-source-change')
        self.assertNotEqual(vectors[-2]['status'],0)
        case=vectors[-1]
        self.assertEqual(case['name'],'reopen-with-nonzero-boot-copies')
        self.assertEqual(case['status'],0)
        data=materialize(case)
        self.assertEqual([sector(data,r)[100] for r in (0,6,2,8)],[0xCC,0xCC,0xA5,0xA5])
        self.assertEqual(sector(data,0),sector(data,6))
        self.assertEqual(sector(data,2),sector(data,8))
        self.assertEqual(struct.unpack_from('<I',data,payload(data,7)+84)[0],zlib.crc32(sector(data,0)))

    def test_sparse_native_seeds_and_mutations_round_trip(self):
        model=model_data()
        pools=[]
        for start,count in model['seed_pools']:
            block=bytearray(512)
            for pos,first,length in model['seed_spans'][start:start+count]:
                block[pos:pos+length]=bytes(model['seed_bytes'][first:first+length])
            pools.append(bytes(block))
        seeds=[]
        for first,count in model['seed_sources']:
            seeds.append(b''.join(pools[i] for i in model['seed_maps'][first:first+count]))
        self.assertEqual(seeds,sources())
        self.assertEqual(len(model['boot_vectors']),len(cases()))
        self.assertEqual(len({c['name'] for c in cases()}),len(cases()))
        for case,vector in zip(cases(),model['boot_vectors']):
            source,first,count,io,change,status,detail,*_=vector
            data=bytearray(seeds[source])
            for lba,offset,value in model['boot_patches'][first:first+count]:
                self.assertLess(lba*512+offset,len(data))
                self.assertLess(offset,512)
                data[lba*512+offset]=value
            self.assertEqual(seal(data,15),materialize(case),case['name'])
            self.assertEqual((io,change,status,detail),(case['io'],case['change'],case['status'],case['detail']))
        self.assertTrue(model_header().isascii())
        self.assertEqual(model_header(),model_header())

    def test_read_faults_cover_boot_record_copies_and_tail(self):
        start=len(fixture())//512+6
        by_name={c['name']:c for c in cases()}
        for relative in (1,2,3,7,8,9,32,33):
            self.assertEqual(by_name['boot-read-error-'+str(relative)]['io'],start+relative)
        for relative in (4,32,33):
            self.assertEqual(by_name['boot-source-changed-'+str(relative)]['change'],start+relative)

    def test_examples_are_not_disk_snapshots_or_executable_images(self):
        data=fixture()
        self.assertEqual(data[payload(data,1):payload(data,1)+512],bytes(512))
        self.assertEqual(data[payload(data,2):payload(data,2)+432],bytes(432))
        self.assertEqual(sector(data,0)[90:510],bytes(420))
        self.assertEqual(sector(data,2)[:510],bytes(510))
        for e in entries(data):
            self.assertIn(e[0],range(1,9))
            if e[0]==4:
                self.assertLessEqual(e[2]+e[3],e[6]+(32 if e[6]==131072 else 1))


if __name__=='__main__':
    unittest.main()
