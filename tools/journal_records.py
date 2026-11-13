"""Encode owned in-memory journal fixtures; no disk, file-import or writer API."""
import struct
import zlib

try:
    from .config_records import FIXTURE_MEDIA_ID, layout_crc, visible
except ImportError:
    from config_records import FIXTURE_MEDIA_ID, layout_crc, visible

BYTES = 1536
EMPTY, PREPARED, COMMITTED = range(3)


def seal(record):
    if len(record) != BYTES: raise ValueError('A journal record has exactly three sectors')
    result = bytearray(record)
    struct.pack_into('<II', result, 64, zlib.crc32(result[512:1024]), zlib.crc32(result[1024:]))
    struct.pack_into('<I', result, 508, zlib.crc32(result[:508]))
    return bytes(result)


def encode(*, before, after, sequence, phase, disk_id, layout, admin_start, admin_sectors,
           media_id, capacity, io_mode=1, heads=0, sectors_per_track=0):
    if (not isinstance(before, bytes) or not isinstance(after, bytes) or len(before) != 512 or len(after) != 512
            or not isinstance(media_id, bytes) or len(media_id) != 16 or not any(media_id)
            or not 1 <= sequence <= 0xFFFFFFFF or phase not in (EMPTY, PREPARED, COMMITTED)
            or (sequence != 1 if phase == EMPTY else sequence < 2)
            or not 1 <= disk_id <= 0xFFFFFFFF or not 0 <= layout <= 0xFFFFFFFF
            or not 0 < admin_start < admin_start + admin_sectors <= min(capacity, 0x100000000)
            or not 1 <= capacity <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError('Invalid journal header or snapshot length')
    if io_mode == 1:
        if heads or sectors_per_track: raise ValueError('EDD journal has no CHS geometry')
    elif (io_mode != 2 or not 1 <= heads <= 256 or not 1 <= sectors_per_track <= 63
            or capacity > heads * sectors_per_track * 1024 or capacity % (heads * sectors_per_track)):
        raise ValueError('Invalid CHS journal geometry')
    for sector in (before, after):
        if (sector[510:] != b'\x55\xaa' or sector[432:436] != b'RBM1'
                or struct.unpack_from('<II',sector,436) != (admin_start,disk_id)):
            raise ValueError('Snapshot differs from loader/medium binding')
    allowed = set()
    for slot in range(4):
        offset = 446 + slot * 16
        ptype = visible(before[offset+4])
        if ptype in (6,14,11,12,7):
            if visible(after[offset+4]) != ptype: raise ValueError('Partition family changed')
            allowed.update((offset,offset+4))
    changed = {i for i in range(512) if before[i] != after[i]}
    if changed - allowed or (bool(changed) if phase == EMPTY else not changed):
        raise ValueError('Journal is not a visibility-only change or baseline')
    # Structural/EBR validity and actual target policy come from independent
    # checks; this fixture encoder is not an installer or a partition scanner.
    result = bytearray(BYTES)
    struct.pack_into('<8sHHIIIIIIHHII16s',result,0,b'RBTXN\0\0\0',1,512,BYTES,sequence,
                     disk_id,layout,admin_start,admin_sectors,phase,io_mode,
                     capacity & 0xFFFFFFFF,capacity >> 32,media_id)
    struct.pack_into('<HH',result,72,heads,sectors_per_track)
    result[512:1024],result[1024:] = before,after
    return seal(result)


def model_record():
    before, ebr = bytearray(512), bytearray(512)
    before[432:436] = b'RBM1'
    struct.pack_into('<II',before,436,126,0x52425431)
    before[446],before[450],before[462],before[466],before[498] = 0x80,6,0,0x16,5
    struct.pack_into('<II',before,454,131072,5073)
    struct.pack_into('<II',before,470,140000,5073)
    struct.pack_into('<II',before,502,63,128520)
    ebr[450] = 0x16;struct.pack_into('<II',ebr,454,63,128457)
    before[510:] = ebr[510:] = b'\x55\xaa'
    after = bytearray(before)
    after[446],after[450],after[462],after[466] = 0,0x16,0x80,6
    return encode(before=bytes(before),after=bytes(after),sequence=2,phase=PREPARED,
                  disk_id=0x52425431,layout=layout_crc({0:before,63*512:ebr}),
                  admin_start=126,admin_sectors=128457,media_id=FIXTURE_MEDIA_ID,capacity=262144)


def model_header():
    data = model_record()
    return ('/* Generated host-to-C16 journal vector; complete MBR snapshots. */\n'
            'static const rb_u8 rb_journal_vector[1536] = {\n'
            + '\n'.join('    '+','.join(str(c) for c in data[i:i+16])+',' for i in range(0,len(data),16))
            + '\n};\n')
