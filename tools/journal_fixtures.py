"""Owned journal-diagnosis media: explicit expected outcomes, no installer."""
import struct

try:
    from .journal_records import encode, seal, EMPTY, PREPARED, COMMITTED
    from .config_records import encode as config, layout_crc, FIXTURE_MEDIA_ID
    from .state_records import encode as state
    from .handoff_fixtures import entry_bytes
except ImportError:
    from journal_records import encode, seal, EMPTY, PREPARED, COMMITTED
    from config_records import encode as config, layout_crc, FIXTURE_MEDIA_ID
    from state_records import encode as state
    from handoff_fixtures import entry_bytes

# Load / journal / copy / observation codes are independent expected values.
CASES = {
    'baseline': dict(observation=1, sequence=1, phase=0, source=0, changed=0),
    'prepared-old': dict(observation=2, sequence=2, phase=1, source=0, changed=1),
    'prepared-new': dict(observation=3, sequence=2, phase=1, source=0, changed=1),
    'committed': dict(observation=4, sequence=2, phase=2, source=1, changed=1),
    'diverged': dict(observation=5, sequence=2, phase=2, source=1, changed=1),
    'bad-a': dict(journal=9, copies=[3,0]),
    'bad-b': dict(journal=9, copies=[0,3]),
    'bad-both': dict(journal=8, copies=[3,3]),
    'conflict': dict(journal=10),
    'identity': dict(journal=8, copies=[4,4]),
    'geometry': dict(journal=8, copies=[5,5]),
    'protected': dict(journal=8, copies=[7,7]),
    'missing': dict(load=1, detail=4, journal=8, copies=[1,1], lba=379, audit_status=4),
    'size': dict(load=1, detail=4, journal=8, copies=[1,1], lba=380, audit_status=4),
    'shared': dict(load=1, detail=6, journal=8, copies=[1,1], lba=139, audit_status=6, audit_file=8),
    'config': dict(load=2, detail=4, journal=8, copies=[1,1], lba=11603, identity_reads=2),
    'state': dict(load=3, detail=4, journal=8, copies=[1,1], lba=12403, identity_reads=4),
    'media': dict(load=4, detail=2, journal=8, copies=[1,1], lba=0, identity_reads=4),
    'io': dict(load=5, detail=7, journal=9, copies=[1,0], lba=13204, fault_lba=13204, fault_once=False),
    'retry': dict(observation=2, sequence=2, phase=1, source=0, changed=1, fault_lba=13204, fault_once=True),
}
JOURNAL_CASES = {'journal-'+kind+'-'+mode.lower(): dict(spec, kind=kind, mode=mode)
                 for kind,spec in CASES.items() for mode in ('EDD','CHS')}


def mutate(size, source, name):
    if size != 64*1024*1024 or name not in JOURNAL_CASES: raise ValueError('Unknown journal fixture')
    spec=JOURNAL_CASES[name];kind=spec['kind'];result=dict(source);size=128*1024*1024
    before=bytearray(result[0]);before[446:462]=entry_bytes();before[446]=0;before[450]=0x16
    after=bytearray(before);after[446]=0x80;after[450]=6
    result[0]=bytes(before)
    binding=dict(disk_id=0x52425431,layout=layout_crc(result),admin_start=126,admin_sectors=128457)
    for lba in (11603,12003):result[lba*512]=config(media_id=FIXTURE_MEDIA_ID,**binding)
    for lba in (12403,12803):result[lba*512]=state(**binding)
    # With explicit 260/16/63, SeaBIOS AH=08 exposes 259 cylinders.
    geometry=dict(capacity=262144) if spec['mode']=='EDD' else dict(capacity=261072,io_mode=2,heads=16,sectors_per_track=63)
    common=dict(before=bytes(before),media_id=FIXTURE_MEDIA_ID,**binding,**geometry)
    seed=encode(after=bytes(before),sequence=1,phase=EMPTY,**common)
    prepared=encode(after=bytes(after),sequence=2,phase=PREPARED,**common)
    committed=encode(after=bytes(after),sequence=2,phase=COMMITTED,**common)
    a,b=prepared,seed
    if kind=='baseline':a=b=seed
    if kind in ('prepared-new','committed','diverged'):result[0]=bytes(after)
    if kind in ('committed','diverged'):b=committed
    if kind=='diverged':m=bytearray(result[0]);m[444]=1;result[0]=bytes(m)
    if kind=='conflict':b=encode(after=bytes(after),sequence=3,phase=PREPARED,**common)
    if kind in ('bad-a','bad-b','bad-both'):
        if kind!='bad-b':m=bytearray(a);m[700]^=1;a=bytes(m)
        if kind!='bad-a':m=bytearray(b);m[700]^=1;b=bytes(m)
    if kind in ('identity','geometry','protected'):
        m=bytearray(prepared)
        if kind=='identity':m[48]^=1
        elif kind=='geometry':struct.pack_into('<I',m,40,geometry['capacity']+1)
        else:m[1024+444]^=1
        a=b=seal(m)
    result[13203*512]=a;result[13603*512]=b
    root=bytearray(result[379*512])
    if kind=='missing':root[25*32]=0xE5
    elif kind=='size':struct.pack_into('<I',root,26*32+28,512)
    elif kind=='shared':struct.pack_into('<H',root,26*32+26,3200)
    result[379*512]=bytes(root)
    if kind in ('config','state'):
        lba=11603 if kind=='config' else 12403;m=bytearray(result[lba*512]);m[80]^=1;result[lba*512]=bytes(m)
    if kind=='media':
        for lba in (12403,12803):result[lba*512]=state(media_id=b'Other medium ID!',**binding)
    return size,result
