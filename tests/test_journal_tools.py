"""Independent format vectors, checksum coverage and journal fixture limits."""
import re
import struct
import unittest
import zlib

from tools.config_records import FIXTURE_MEDIA_ID
from tools.journal_records import encode, model_record, model_header, seal, EMPTY, PREPARED, COMMITTED


def arguments():
    r = model_record()
    return dict(before=r[512:1024], after=r[1024:], sequence=2, phase=PREPARED,
                disk_id=0x52425431, layout=0x5AC2C6E5, admin_start=126,
                admin_sectors=128457, media_id=FIXTURE_MEDIA_ID, capacity=262144)


class JournalToolsTests(unittest.TestCase):
    def test_literal_three_sector_vector_and_native_bridge(self):
        r = model_record()
        self.assertEqual(len(r),1536)
        self.assertEqual(r[:16],b'RBTXN\0\0\0\x01\0\0\x02\0\x06\0\0')
        self.assertEqual(struct.unpack_from('<IIIIIHHII',r,16),
                         (2,0x52425431,0x5AC2C6E5,126,128457,1,1,262144,0))
        self.assertEqual(r[48:64],FIXTURE_MEDIA_ID)
        self.assertEqual(struct.unpack_from('<II',r,64),(0xDF25514C,0x1E786A6D))
        self.assertEqual(struct.unpack_from('<I',r,508)[0],0x09E5A5BC)
        self.assertEqual(r[76:508],bytes(432))
        self.assertEqual(r[1022:1024],b'\x55\xaa');self.assertEqual(r[1534:],b'\x55\xaa')
        values=bytes(map(int,re.findall(r'\d+',model_header().split('{',1)[1].split('}',1)[0])))
        self.assertEqual(values,r)
        self.assertEqual(seal(r),r)

    def test_every_byte_is_covered_by_header_or_snapshot_crc(self):
        r=model_record()
        def checks(p):
            return (zlib.crc32(p[:508])==struct.unpack_from('<I',p,508)[0]
                    and zlib.crc32(p[512:1024])==struct.unpack_from('<I',p,64)[0]
                    and zlib.crc32(p[1024:1536])==struct.unpack_from('<I',p,68)[0])
        self.assertTrue(checks(r))
        for offset in range(1536):
            damaged=bytearray(r);damaged[offset]^=1
            with self.subTest(offset=offset):self.assertFalse(checks(damaged))

    def test_prepare_completion_and_next_transaction_preserve_exact_snapshots(self):
        args=arguments();prepared=encode(**args)
        baseline=encode(**dict(args,after=args['before'],sequence=1,phase=EMPTY))
        committed=encode(**dict(args,phase=COMMITTED))
        following=encode(**dict(args,before=args['after'],after=args['before'],sequence=3))
        self.assertEqual(baseline[512:1024],baseline[1024:])
        self.assertEqual(prepared[512:],committed[512:])
        self.assertEqual(following[512:1024],committed[1024:])
        self.assertEqual({i for i in range(512) if prepared[512+i]!=prepared[1024+i]}, {446,450,462,466})
        self.assertEqual(struct.unpack_from('<HH',committed,36),(2,1))
        self.assertEqual(struct.unpack_from('<I',following,16)[0],3)
        chs=encode(**dict(args,io_mode=2,heads=16,sectors_per_track=63,capacity=1032192))
        self.assertEqual(struct.unpack_from('<HH',chs,72),(16,63))
        self.assertEqual(chs[512:],prepared[512:])

    def test_noncanonical_inputs_and_protected_changes_are_rejected(self):
        args=arguments()
        changes=[dict(sequence=0),dict(sequence=1),dict(sequence=0x100000000),dict(phase=3),
                 dict(phase=EMPTY),dict(before=b''),dict(after=bytes(511)),dict(after=bytes(513)),
                 dict(media_id=bytes(16)),dict(media_id=b'ID'),dict(admin_start=0),dict(admin_sectors=0),
                 dict(admin_start=0xFFFFFFFF,admin_sectors=2),dict(capacity=0),dict(capacity=0x10000000000000000),
                 dict(io_mode=0),dict(heads=1),dict(io_mode=2,heads=0,sectors_per_track=63),
                 dict(io_mode=2,heads=257,sectors_per_track=63),dict(io_mode=2,heads=16,sectors_per_track=64),
                 dict(io_mode=2,heads=16,sectors_per_track=63,capacity=1032193),dict(after=args['before'])]
        for change in changes:
            with self.subTest(change=change.keys()),self.assertRaises(ValueError):encode(**dict(args,**change))
        for offset in (0,431,432,436,440,444,447,454,470,502,510,511):
            after=bytearray(args['after']);after[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(ValueError):encode(**dict(args,after=bytes(after)))
        for length in (0,512,1535,1537):
            with self.subTest(length=length),self.assertRaises(ValueError):seal(bytes(length))


if __name__=='__main__':unittest.main()
