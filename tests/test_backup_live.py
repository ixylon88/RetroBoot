"""Independent boundaries for freshly bound provisional live output."""
import struct
import unittest
import zlib

from tools.backup_container import inspect
from tools.backup_live_vectors import cases, seeds, reads_for, expected_reads, mbr_bytes
from tools.backup_payload_vectors import expected_reads as capture_reads
from tools.rescue_match_fixtures import RECORDS


class BackupLiveTests(unittest.TestCase):
    def test_wire_oracles_use_explicit_mbrs_and_exact_live_extents(self):
        for seed in seeds()[:6]:
            identity, entries = inspect(seed['wire'])
            self.assertEqual(identity, seed['identity'])
            self.assertEqual([e['kind'] for e in entries], [1,2,3,4,4,5,6,7,8])
            for e in entries:
                actual=seed['wire'][e['file_sector']*512:(e['file_sector']+e['sectors'])*512]
                expected=mbr_bytes(e['kind']) if e['kind']<=2 else b''.join(
                    seed['disk'].get(e['lba']+i,bytes(512)) for i in range(e['sectors']))
                self.assertEqual(actual,expected)
            self.assertEqual(len({mbr_bytes(1),mbr_bytes(2),seed['disk'][0]}),3)
        self.assertGreater(len(seeds()[4]['wire']),65536)
        self.assertEqual(len(seeds()[5]['wire']),1024*1024)

    def test_address_oracle_keeps_live_mbr_out_of_stream_roles(self):
        capture, live=reads_for(seeds()[0])
        self.assertEqual(capture,capture_reads())
        self.assertNotIn(0,live)
        self.assertEqual(expected_reads(),capture+live*2+capture)
        self.assertEqual(len(expected_reads()),4608)
        for phase in (0,1):
            faults=[c for c in cases() if c['name'].startswith(f'live-io-{phase}-')]
            self.assertEqual([c['at'] for c in faults],list(range(len(capture)+phase*len(live)+1,len(capture)+(phase+1)*len(live)+1)))
            self.assertEqual([c['pos'] for c in faults],list(range(7,45)))
            self.assertTrue(all(c['status']==6 and c['stream']==3 for c in faults))

    def test_stale_claims_and_null_arguments_cannot_emit_output(self):
        vectors=cases()
        preflight=[c for c in vectors if c['name'].startswith(('identity-','extent-','metadata-','null-','capture-'))]
        self.assertTrue(preflight)
        self.assertTrue(all(c['status'] and c['mbrs']==c['sinks']==0 for c in preflight))
        self.assertTrue(all(c['reads']==0 for c in preflight if c['name'].startswith(('metadata-','null-'))))
        self.assertEqual({c['detail'] for c in vectors if c['name'].startswith('identity-')},{1,2,3,4})

    def test_closing_capture_can_revoke_a_fully_delivered_stream(self):
        vectors={c['name']:c for c in cases()}
        for name in ('closing-first-read','closing-last-read','closing-resealed-config'):
            self.assertEqual(vectors[name]['sinks'],45)
            self.assertNotEqual(vectors[name]['status'],0)
        original=seeds()[0]['disk'][RECORDS[0]]
        changed=bytearray(original)
        struct.pack_into('<I',changed,16,2)
        struct.pack_into('<I',changed,508,zlib.crc32(changed[:508]))
        self.assertNotEqual(original,changed)
        self.assertEqual(zlib.crc32(original),zlib.crc32(changed))
        self.assertNotEqual(zlib.crc32(original[:508]),zlib.crc32(changed[:508]))
        self.assertEqual(vectors['closing-resealed-config']['status'],7)
