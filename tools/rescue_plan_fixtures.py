"""Owned live-HDD fixtures and independent expectations for rescue F6."""
import struct

try:
    from .backup_boot_vectors import fixture
    from .backup_container import inspect
    from .rescue_match_fixtures import disk as match_disk, acquisition, RECORDS
except ImportError:
    from backup_boot_vectors import fixture
    from backup_container import inspect
    from rescue_match_fixtures import disk as match_disk, acquisition, RECORDS

SYSTEM = 131072


def disk(kind='match'):
    base = kind if kind in ('config-crc','unowned','fat-copies') else 'match'
    size, extents = match_disk(base)
    raw = fixture(); _, entries = inspect(raw)
    e = next(e for e in entries if e['kind']==4 and e['lba']==SYSTEM)
    area = bytearray(raw[e['file_sector']*512:(e['file_sector']+e['sectors'])*512])
    if kind=='unknown-mbr':
        mbr=bytearray(extents[0]);mbr[432:436]=bytes(4);extents[0]=bytes(mbr)
    elif kind=='invalid-vbr':area[510]=0
    elif kind=='bad-fsinfo-layout':struct.pack_into('<H',area,48,2)
    elif kind=='oversized':struct.pack_into('<H',area,14,4096)
    elif kind=='reserved-unread':area[512:1024]=bytes(512)
    elif kind not in ('match','config-crc','unowned','fat-copies'):raise ValueError('Unknown plan HDD fixture')
    # Full synthetic FAT32 reserved area, with no HDD loader or operating system.
    # F6 deliberately reads only its first VBR; reserved-unread tests that limit.
    extents[SYSTEM*512]=bytes(area)
    return size,extents


def specs():
    result={}
    def add(name,probe=0,status=0,detail=0,nested=0,**kw):
        result[name]=dict(probe=probe,status=status,detail=detail,nested=nested,
            index=0,lba=0,kind='match',rom=0,**kw)
    add('plan')
    add('demo',demo=True,cross_view=True)
    add('chs',chs=True)
    add('changed-after-success',mutation=True)
    add('no-hdd',probe=1,absent=True)
    for name,status,detail,nested,lba in (
        ('unknown-mbr',2,6,1,0),('config-crc',2,4,4,RECORDS[0]),
        ('unowned',2,3,9,134),('fat-copies',2,3,7,628),
        ('invalid-vbr',3,2,0,SYSTEM),('bad-fsinfo-layout',4,0,0,SYSTEM),
        ('oversized',5,4,0,SYSTEM),('reserved-unread',0,0,0,0)):
        add(name,status=status,detail=detail,nested=nested)
        result[name].update(kind=name,lba=lba)
    add('mbr-io',status=2,detail=2,fault_lba=0)
    add('vbr-io',status=7,detail=1,fault_lba=SYSTEM);result['vbr-io']['lba']=SYSTEM
    add('changed-probe',status=6,detail=1);result['changed-probe']['rom']=14
    add('failed-reprobe',probe=2);result['failed-reprobe']['rom']=15
    add('failed-probe',probe=2);result['failed-probe']['rom']=6
    add('bad-chs',probe=3);result['bad-chs']['rom']=4
    return result


def hdd_reads(spec):
    if spec['probe'] and spec['rom']!=15:return []
    reads=acquisition();kind=spec['kind']
    if kind=='unknown-mbr':return [0]
    if kind=='config-crc':return reads[:reads.index(RECORDS[1])+1]
    if kind=='unowned':return reads[:reads.index(134)+2]
    if kind=='fat-copies':return reads[:-5]
    reads=reads*2+[SYSTEM,126,0]
    if 'fault_lba' in spec:
        at=reads.index(spec['fault_lba']);return reads[:at]+[spec['fault_lba']]*3
    if kind in ('invalid-vbr','bad-fsinfo-layout','oversized'):return reads[:-2]
    return reads*2


def ranges():
    return [('P_MBR',0,1),('EBR',63,1),('P_BOOT',SYSTEM,32),('P_BOOT',126,1),
            *[(name,lba,1) for name,lba in zip(('RBCFG.A','RBCFG.B','RBSTATE.A','RBSTATE.B'),RECORDS)]]
