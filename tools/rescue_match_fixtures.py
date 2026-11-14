"""Synthetic, nonbootable HDD metadata and independent rescue F5 expectations."""
from dataclasses import replace
import struct
import zlib

try:
    from .backup_container import Chunk, encode, inspect
    from .backup_boot_vectors import fixture
    from .config_records import FIXTURE_MEDIA_ID, layout_crc, seal
    from .rescue_file_fixtures import put_backup, expected_file_reads
except ImportError:
    from backup_container import Chunk, encode, inspect
    from backup_boot_vectors import fixture
    from config_records import FIXTURE_MEDIA_ID, layout_crc, seal
    from rescue_file_fixtures import put_backup, expected_file_reads

CAPACITY = 262144
CHS_CAPACITY = 259 * 16 * 63
ADMIN = 126
ROOT = 629
DATA = 661
RECORDS = [6257, 6457, 6657, 6857]
CHAINS = ([2, 3], [20, 300, 40, 500, 60], [2800], [2900], [3000], [3100],
          [3200, 3202], [3300, 3302])


def backup(chs=False, generation=1, capacity=None):
    raw = fixture(); identity, entries = inspect(raw)
    identity = replace(identity, generation=generation,
                       capacity=capacity or (CHS_CAPACITY if chs else CAPACITY),
                       route=2 if chs else 1, heads=16 if chs else 0,
                       sectors_per_track=63 if chs else 0)
    return encode(identity, [Chunk(e['kind'], e['index'], e['lba'],
        raw[e['file_sector']*512:(e['file_sector']+e['sectors'])*512],
        e['owner_start'], e['owner_sectors']) for e in entries])


def disk(kind='match'):
    raw = backup(); _, entries = inspect(raw)
    chunks = {e['kind']: raw[e['file_sector']*512:(e['file_sector']+e['sectors'])*512]
              for e in entries if e['kind'] != 4}
    mbr, ebr = bytearray(chunks[2]), bytearray(chunks[3])
    admin = bytearray(raw[entries[3]['file_sector']*512:(entries[3]['file_sector']+1)*512])
    admin[62:66] = b'RBV1'; struct.pack_into('<IH', admin, 66, DATA, 3)
    struct.pack_into('<H', admin, 72, 0)
    struct.pack_into('<H', admin, 72, -sum(struct.unpack('<256H',admin)) & 65535)
    fat = bytearray(251*512); struct.pack_into('<HH', fat, 0, 0xFFF8, 0xFFFF)
    root = bytearray(32*512)
    for slot in range(1,20): root[slot*32] = 0xE5
    names = (b'RBBOOT  SYS',b'RBSTG2  BIN',b'RBCFG   A  ',b'RBCFG   B  ',
             b'RBSTATE A  ',b'RBSTATE B  ',b'RBTXN   A  ',b'RBTXN   B  ')
    for i, chain in enumerate(CHAINS):
        slot = 0 if not i else i+19; at = slot*32
        root[at:at+12] = names[i]+b'\x20'
        struct.pack_into('<HI', root, at+26, chain[0], 1536 if i==0 or i>=6 else 5000 if i==1 else 512)
        for c,n in zip(chain, [*chain[1:],65535]): struct.pack_into('<H',fat,c*2,n)
    records = [bytearray(chunks[k]) for k in range(5,9)]
    if kind=='identity':
        for r in records: r[48] ^= 1; r[:] = seal(r)
    elif kind=='config-crc': records[0][80] ^= 1
    elif kind=='state-crc': records[2][80] ^= 1
    elif kind=='missing-file': root[25*32] = 0xE5
    elif kind=='unowned': struct.pack_into('<H',fat,2000*2,0xFFFF)
    elif kind=='bad-mbr': mbr[510] = 0
    elif kind=='layout':
        # One primary moves; its live configuration/state must move with it.
        struct.pack_into('<I',mbr,454,131073)
        crc = layout_crc({0:bytes(mbr),63*512:bytes(ebr)})
        for i,r in enumerate(records):
            struct.pack_into('<I',r,24,crc)
            struct.pack_into('<I',r,68 if i<2 else 72,131073)
            r[:] = seal(r)
    elif kind not in ('match','fat-copies','capacity'): raise ValueError('Unknown target fixture')
    other = bytearray(fat)
    if kind=='fat-copies': other[-1] ^= 1
    extents = {0:bytes(mbr),63*512:bytes(ebr),ADMIN*512:bytes(admin),
               127*512:bytes(fat),378*512:bytes(other),ROOT*512:bytes(root)}
    extents.update({lba*512:bytes(r) for lba,r in zip(RECORDS,records)})
    # Program and journal allocations contain zeros. There is no HDD loader,
    # operating system or backup collector in this fixture.
    return (CAPACITY + (1 if kind=='capacity' else 0))*512, extents


def acquisition():
    reads = [0,0,63,126,629,630]; cached = None
    for chain in CHAINS:
        for c in chain:
            index = c//256
            if index != cached: reads += [127+index,378+index]
            cached = index
    reads += [lba for i in range(251) for lba in (127+i,378+i)]
    return reads + RECORDS + [0]


def specs():
    result = {}
    def add(name, status=0, detail=0, nested=0, **kw):
        result[name] = dict(status=status,detail=detail,nested=nested,record=0,file_lba=0,
                            disk_lba=0,kind='match',rom=0,**kw)
    add('match')
    add('changed-hdd-after-success', mutation='hdd')
    add('missing-file-after-success', mutation='floppy')
    add('chs', chs=True)
    add('no-hdd',3,1,absent=True)
    add('missing-backup',1,5,file_case='file-missing')
    add('bad-backup',2,1,1,file_case='file-container-crc');result['bad-backup']['record']=3
    add('bad-saved-boot',2,7,1,file_case='file-fsinfo');result['bad-saved-boot']['disk_lba']=131073
    for name,status,detail,nested in (
        ('capacity',4,7,0),('geometry',4,8,0),('identity',4,6,4),('layout',4,9,0),
        ('bad-mbr',4,6,1),('missing-file',4,3,4),('fat-copies',4,3,7),
        ('unowned',4,3,9),('config-crc',4,4,4),('state-crc',4,5,4)):
        add(name,status,detail,nested)
        if name=='geometry':result[name]['chs']=True;result[name]['saved_edd']=True
        else:result[name]['kind']=name
    result['missing-file']['disk_lba']=ROOT
    result['fat-copies']['disk_lba']=628
    result['unowned']['disk_lba']=134
    result['config-crc']['disk_lba']=RECORDS[0]
    result['state-crc']['disk_lba']=RECORDS[2]
    for name,lba in (('mbr-io',0),('record-io',RECORDS[0])):
        add(name,4,2,0 if not lba else 5,fault_lba=lba);result[name]['disk_lba']=lba
    for name,rom,code,detail in (('changed-probe',14,5,1),('failed-reprobe',15,3,2),
                               ('changed-file',16,2,1),('resealed-file',17,5,2)):
        add(name,code,detail);result[name]['rom']=rom
    result['changed-file']['nested']=1;result['changed-file']['record']=3
    return result


def floppy(original,spec):
    try:
        from .rescue_file_fixtures import make_fixture
    except ImportError:
        from rescue_file_fixtures import make_fixture
    if spec.get('file_case'):return make_fixture(original,spec['file_case'])
    return bytes(put_backup(original,backup(spec.get('chs',False) and not spec.get('saved_edd',False),
        capacity=CHS_CAPACITY if spec.get('saved_edd') else None))[0])


def hdd_reads(spec):
    if spec['status'] in (1,2,3) and spec.get('rom',0)<14:return []
    if spec['detail'] in (7,8) and spec['status']==4:return []
    reads=acquisition();kind=spec['kind']
    if 'fault_lba' in spec:
        at=reads.index(spec['fault_lba']);return reads[:at]+[spec['fault_lba']]*3
    if kind=='bad-mbr':return [0]
    if kind=='missing-file':return reads[:6]
    if kind=='fat-copies':return reads[:-5]
    if kind=='unowned':return reads[:reads.index(134)+2]
    if kind in ('config-crc','state-crc'):
        return reads[:reads.index(RECORDS[1 if kind=='config-crc' else 3])+1]
    return reads*2


def floppy_reads(image,spec):
    case=spec.get('file_case','file-demo')
    reads=expected_file_reads(image,case)
    if not spec['status'] or spec['rom'] in (16,17):
        # The map is reused; full content and then metadata are checked again.
        reads+=reads[33:34] if spec['rom']==16 else reads[33:]
    return reads


def observed(spec):
    identity,_=inspect(backup(spec.get('chs',False)))
    return dict(disk_id=identity.disk_id,media_id=FIXTURE_MEDIA_ID.hex().upper(),
                layout_crc=identity.layout_crc,admin_start=ADMIN,admin_sectors=128457,
                capacity=identity.capacity,route='CHS' if spec.get('chs') else 'EDD',
                heads=identity.heads,spt=identity.sectors_per_track,config_generation=1,state_generation=1)
