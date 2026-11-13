"""Host evidence that semantic counterexamples still have valid container CRCs."""
import re
import struct
import unittest
import zlib

from tools.backup_container import InvalidBackup, inspect
from tools.backup_record_vectors import cases, entries, fixture, materialize, model_header, seal
from tools.config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID


def payload(data, kind, index=0):
    entry = next(e for e in entries(data) if e[:2] == (kind,index))
    return data[entry[4]*512:(entry[4]+entry[3])*512]


class BackupRecordTests(unittest.TestCase):
    def test_literal_partition_and_record_bindings(self):
        for chain, layout, count in ((False,0x420CE91C,9),(True,0x75D61DE1,11)):
            with self.subTest(chain=chain):
                data = fixture(chain)
                identity, descriptors = inspect(data)
                self.assertEqual(len(data), (16 if chain else 14)*512)
                self.assertEqual(identity.layout_crc, layout)
                self.assertEqual(len(descriptors), count)
                mbr, ebr = payload(data,2), payload(data,3)
                self.assertEqual(mbr[432:436], b'RBM1')
                self.assertEqual(struct.unpack_from('<II',mbr,436),(126,0x52425431))
                self.assertEqual(mbr[510:], b'\x55\xaa')
                self.assertEqual(struct.unpack_from('<II',mbr,454),(131072,5073))
                self.assertEqual(struct.unpack_from('<II',ebr,454),(63,128457))
                for kind in range(5,9):
                    record = payload(data,kind)
                    self.assertEqual(struct.unpack_from('<4I',record,20),(0x52425431,layout,126,128457))
                    self.assertEqual(record[48:64],FIXTURE_MEDIA_ID)
                    self.assertEqual(zlib.crc32(record[:508]),struct.unpack_from('<I',record,508)[0])
                self.assertEqual(struct.unpack_from('<Q',payload(data,5),108)[0],TEST_INSTALL_ID)
                self.assertEqual(struct.unpack_from('<Q',payload(data,7),64)[0],TEST_INSTALL_ID)
                if chain:
                    self.assertEqual(struct.unpack_from('<II',ebr,470),(128937,2000))
                    self.assertEqual(struct.unpack_from('<II',payload(data,3,1),454),(63,1000))

    def test_semantic_counterexamples_retain_outer_integrity(self):
        for case in cases():
            with self.subTest(case=case['name']):
                data = materialize(case)
                if case['status'] == 1 and not case['io']:
                    with self.assertRaises(InvalidBackup) as error:
                        inspect(data)
                    self.assertEqual(error.exception.status,case['detail'])
                else:
                    inspect(data)
                    bad = [kind for kind in range(5,9) if zlib.crc32(payload(data,kind)[:508])
                           != struct.unpack_from('<I',payload(data,kind),508)[0]]
                    expected={'config-internal-crc':[5],'config-copy-b-internal-crc':[6],
                              'state-internal-crc':[7],'state-copy-b-internal-crc':[8]}
                    self.assertEqual(bad,expected.get(case['name'],[]))

    def test_foreign_media_and_unresolved_ids_are_checksumming_correctly(self):
        by_name = {case['name']:case for case in cases()}
        for name,kind in (('config-foreign-media',5),('state-foreign-media',7)):
            data = materialize(by_name[name])
            identity,_ = inspect(data)
            self.assertNotEqual(payload(data,kind)[48:64],identity.media_id)
            self.assertEqual(payload(data,kind),payload(data,kind+1))
        data = materialize(by_name['config-older-foreign-media'])
        self.assertEqual(struct.unpack_from('<I',payload(data,6),16)[0],2)
        self.assertEqual(payload(data,6)[48:64],FIXTURE_MEDIA_ID)
        self.assertNotEqual(payload(data,5)[48:64],FIXTURE_MEDIA_ID)
        data = materialize(by_name['unresolved-installation'])
        self.assertNotEqual(struct.unpack_from('<Q',payload(data,5),108)[0],
                            struct.unpack_from('<Q',payload(data,7),64)[0])

    def test_generated_native_vectors_preserve_all_mutations(self):
        header = model_header()
        self.assertEqual(header,model_header())
        self.assertTrue(header.isascii())
        seeds = [fixture(),fixture(True)]
        for i,seed in enumerate(seeds):
            values = re.search(r'record_seed_'+str(i)+r'\[\d+\] = \{(.*?)\};',header,re.S)[1]
            self.assertEqual(bytes(int(n) for n in re.findall(r'\d+',values)),seed)
        def rows(name):
            values=re.search(name+r'\[\]\[\d+\] = \{(.*?)\};',header,re.S)[1]
            return [tuple(int(n) for n in re.findall(r'\d+',row)) for row in re.findall(r'\{(.*?)\}',values)]
        patches,vectors=rows('record_patches'),rows('record_vectors')
        self.assertEqual(len(vectors),len(cases()))
        self.assertEqual(len({case['name'] for case in cases()}),len(vectors))
        for case,vector in zip(cases(),vectors):
            data=bytearray(seeds[vector[0]])
            for offset,value in patches[vector[1]:vector[1]+vector[2]]:
                self.assertLess(offset,len(data))
                data[offset]=value
            data=seal(data,vector[3]) if vector[4] else bytes(data)
            self.assertEqual(data,materialize(case),case['name'])
            self.assertEqual(vector[5:9],(case['io'],case['change'],case['status'],case['detail']))

    def test_positive_pair_selection_expectations(self):
        for case in cases():
            if case['status']:
                continue
            with self.subTest(case=case['name']):
                data=materialize(case)
                for kind,family in ((5,'config'),(7,'state')):
                    a,b=(struct.unpack_from('<I',payload(data,k),16)[0] for k in (kind,kind+1))
                    self.assertEqual(int(b>a),case[family+'_source'])
                    self.assertEqual(max(a,b),case[family+'_generation'])
                    if a==b:
                        self.assertEqual(payload(data,kind),payload(data,kind+1))

    def test_fixtures_cannot_be_mistaken_for_bootable_full_snapshots(self):
        data=fixture()
        self.assertEqual(payload(data,1),bytes(512))
        self.assertEqual(payload(data,4),bytes(512))
        self.assertEqual(payload(data,4,1),bytes(512))
        self.assertEqual(payload(data,2)[:432],bytes(432))
        # The advertised check deliberately accepts opaque boot/original bytes;
        # these are no substitute for filesystem or provenance checks.
        case=next(c for c in cases() if c['name']=='opaque-boot-and-original-bytes')
        self.assertEqual(case['status'],0)
        self.assertEqual(payload(materialize(case),1)[0],0xCC)


if __name__=='__main__':
    unittest.main()
