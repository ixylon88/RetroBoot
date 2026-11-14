"""Synthetic reserved-area fixtures, without OS code, FATs or user data."""
import struct
import zlib

try:
    from .backup_container import Identity, Chunk, encode
    from .backup_record_vectors import entries, seal
    from .config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, layout_crc, encode as configuration
    from .state_records import encode as installation_state
    from .volume_fixtures import header
except ImportError:
    from backup_container import Identity, Chunk, encode
    from backup_record_vectors import entries, seal
    from config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, layout_crc, encode as configuration
    from state_records import encode as installation_state
    from volume_fixtures import header


def fixture(bits=32, reserved=32, split=False, backup=6, kind=None):
    kind = kind or (6 if bits == 16 else 11)
    length = 5073 if bits == 16 else 71126
    mbr, ebr = bytearray(512), bytearray(512)
    mbr[432:436] = b'RBM1'
    struct.pack_into('<II', mbr, 436, 126, 0x52425431)
    mbr[446], mbr[450], mbr[498], ebr[450] = 0x80, kind, 5, 0x16
    struct.pack_into('<II', mbr, 454, 131072, length)
    struct.pack_into('<II', mbr, 502, 63, 128520)
    struct.pack_into('<II', ebr, 454, 63, 128457)
    mbr[510:] = ebr[510:] = b'\x55\xaa'
    admin = header(16,126)
    admin[13] = 2
    struct.pack_into('<H',admin,22,251)
    struct.pack_into('<I',admin,32,128457)
    boot = bytearray(reserved*512)
    boot[:512] = header(bits,131072)
    struct.pack_into('<H',boot,14,reserved)
    if bits == 32:
        struct.pack_into('<H',boot,50,backup)
        info = bytearray(512)
        for offset,value in ((0,0x41615252),(484,0x61417272),(488,0xFFFFFFFF),
                             (492,0xFFFFFFFF),(508,0xAA550000)):
            struct.pack_into('<I',info,offset,value)
        boot[512:1024] = info
        boot[1534:1536] = b'\x55\xaa'
        if backup:
            boot[backup*512:(backup+3)*512] = boot[:1536]
    binding = dict(disk_id=0x52425431,layout=layout_crc({0:mbr,63*512:ebr}),admin_start=126,admin_sectors=128457)
    target = dict(install_id=TEST_INSTALL_ID,slot=1,type=kind,kind=2 if kind==7 else 1,start=131072,sectors=length)
    config = configuration(**binding,media_id=FIXTURE_MEDIA_ID,
                           profiles=[dict(target,id=1,name='Test VBR',installed=2,approved=1)])
    state = installation_state(**binding,installations=[dict(target,phase=6,vbr_crc=zlib.crc32(boot[:512]))])
    chunks = [Chunk(1,0,0,bytes(512)),Chunk(2,0,0,bytes(mbr)),Chunk(3,0,63,bytes(ebr)),
              Chunk(4,0,126,bytes(admin),126,128457)]
    # Reverse LBA order deliberately: descriptor indices are not disk order.
    if split:
        chunks += [Chunk(4,1,131075,bytes(boot[1536:]),131072,length),
                   Chunk(4,2,131072,bytes(boot[:1536]),131072,length)]
    else:
        chunks.append(Chunk(4,1,131072,bytes(boot),131072,length))
    chunks += [Chunk(k,0,11603+400*(k-5),config if k<7 else state,126,128457) for k in range(5,9)]
    return encode(Identity(1,binding['disk_id'],binding['layout'],126,128457,262144,FIXTURE_MEDIA_ID),chunks)


def sources():
    return [fixture(), fixture(16,1), fixture(split=True), fixture(reserved=130),
            fixture(backup=0), fixture(backup=10), fixture(16,4), fixture(kind=7)]


def payload(data,kind,index=0):
    return next(e[4]*512 for e in entries(data) if e[:2] == (kind,index))


def cases():
    seeds = sources()
    result = []
    def add(name,status=0,detail=0,edits=(),source=0,bind=True,io=0,change=0,
            ready=1,lba=131072,index=1,kind=4):
        result.append(dict(name=name,status=status,detail=detail,edits=list(edits),source=source,
                           bind=bind,io=io,change=change,ready=ready,
                           lba=lba if status else 0,index=index if status else 0,kind=kind if status else 0))
    def pair(offset,width,value):
        return [(payload(seeds[0],k)+offset,width,value) for k in (7,8)]
    b = payload(seeds[0],4,1)
    for source,name in enumerate(('fat32','fat16','split-reversed-extents','over-64k-extent',
                                  'no-backup-copy','backup-at-10','fat16-four-reserved')):
        add(name,source=source)
    add('unsupported-type-07',4,16,source=7)
    add('stale-backup-hints',edits=[(b+512+488,4,123),(b+512+492,4,456)])
    add('hint-boundaries',edits=[(b+512+488,4,70000),(b+512+492,4,70001)])
    add('zero-free-clusters',edits=[(b+512+488,4,0),(b+512+492,4,2)])
    add('last-reserved-sector-preserved',edits=[(b+31*512+511,1,0xA5)])
    add('hidden-fat32-target',edits=[(payload(seeds[0],2)+450,1,0x1B)])
    add('vbr-signature',4,2,[(b+510,1,0)])
    add('vbr-hidden-lba',4,10,[(b+28,4,131073)])
    add('vbr-fat-too-small',4,13,[(b+36,4,546)])
    add('not-fat32',4,12,[(b+13,1,2)])
    add('fsinfo-other-position',6,0,[(b+48,2,3)])
    add('backup-overlaps-primary',6,0,[(b+50,2,2)])
    add('backup-region-overruns-reserved',6,0,[(b+50,2,31)])
    add('backup-offset-overflow',4,14,[(b+50,2,65535)])
    add('missing-reserved-tail',5,1,[(b+14,2,33)],lba=131104,index=65535)
    add('extra-sector-outside-reserved',5,2,[(b+14,2,31)])
    split = seeds[2]
    table = 512 + 32*next(i for i,e in enumerate(entries(split)) if e[:2] == (4,1))
    # Move the latter extent one sector right, and extend the BPB by one sector.
    add('gap-between-extents',5,1,[(table+4,4,131076),(payload(split,4,2)+14,2,33)],source=2,lba=131075,index=65535)
    for rel,label in ((1,'primary'),(7,'backup')):
        for offset,value,detail,suffix in ((0,0,1,'lead'),(484,0,1,'structure'),(508,0,1,'trail'),
                (4,1,2,'reserved-first'),(496,1,2,'reserved-last'),
                (488,70001,3,'free-range'),(492,1,4,'next-low'),(492,70002,4,'next-high')):
            add(label+'-fsinfo-'+suffix,7,detail,[(b+rel*512+offset,4,value)],lba=131072+rel)
    add('continuation-signature',8,3,[(b+2*512+510,1,0)],lba=131074)
    add('backup-vbr-bpb',8,1,[(b+6*512+13,1,2)],lba=131078)
    add('backup-vbr-code',8,1,[(b+6*512+100,1,0xCC)],lba=131078)
    add('backup-continuation-code',8,2,[(b+8*512+100,1,0xCC)],lba=131080)
    add('backup-continuation-signature',8,2,[(b+8*512+510,1,0)],lba=131080)
    add('ready-crc-mismatch',9,0,pair(84,4,0),bind=False)
    add('older-ready-crc-ignored',edits=[(payload(seeds[0],7)+84,4,0),
        (payload(seeds[0],8)+16,4,2)],bind=False)
    add('selected-ready-crc-mismatch',9,0,[(payload(seeds[0],8)+84,4,0),
        (payload(seeds[0],8)+16,4,2)],bind=False)
    add('pending-installation',edits=pair(83,1,5)+pair(84,4,0)
        +[(payload(seeds[0],k)+80,1,0) for k in (5,6)],bind=False,ready=0)
    empty_profiles=[(payload(seeds[0],k)+36,2,0) for k in (5,6)]
    empty_profiles += [(payload(seeds[0],k)+offset,1,0) for k in (5,6) for offset in range(64,116)]
    add('unreferenced-ready-still-checked',9,0,empty_profiles+pair(84,4,0),bind=False)
    add('record-validation-first',1,6,[(payload(seeds[0],2)+432,1,0)],kind=2,index=0,lba=0)
    add('late-admin-bpb-failure',4,2,[(payload(seeds[0],4)+510,1,0)],index=0,lba=126)
    # Initial container + six record reads, then target reserved area, then admin.
    begin = len(seeds[0])//512 + 6
    for relative in (1,2,3,7,8,9,32,33):
        add('boot-read-error-'+str(relative),2,io=begin+relative,
            index=0 if relative==33 else 1,lba=126 if relative==33 else 131071+relative)
    # Changing opaque bytes preserves structure, so the streamed CRC detects it.
    for relative in (4,32,33):
        add('boot-source-changed-'+str(relative),3,change=begin+relative,
            index=0 if relative==33 else 1,lba=126 if relative==33 else 131072)
    long_begin=len(seeds[3])//512+6
    add('over-64k-last-read-error',2,source=3,io=long_begin+130,lba=131201)
    add('over-64k-last-source-change',3,source=3,change=long_begin+130)
    return result


def materialize(case,reseal=True):
    data = bytearray(sources()[case['source']])
    for offset,width,value in case['edits']:
        data[offset:offset+width] = value.to_bytes(width,'little')
    if case['bind']:
        e = next(e for e in entries(data) if e[0]==4 and e[2]==131072)
        crc = zlib.crc32(data[e[4]*512:(e[4]+1)*512])
        for k in (7,8):
            struct.pack_into('<I',data,payload(data,k)+84,crc)
    return seal(data,15) if reseal else bytes(data)


def model_data():
    """Deduplicate sparse sectors; no complete container fits in native RAM."""
    pools, maps, seeds, spans, values, patches, vectors = [],[],[],[],[],[],[]
    originals = sources()
    for data in originals:
        start = len(maps)
        for offset in range(0,len(data),512):
            block = data[offset:offset+512]
            if block not in pools:
                pools.append(block)
            maps.append(pools.index(block))
        seeds.append((start,len(data)//512))
    pool_ranges = []
    for block in pools:
        first = len(spans)
        pos = 0
        while pos < 512:
            if not block[pos]:
                pos += 1
                continue
            end = pos+1
            while end<512 and block[end]:
                end += 1
            spans.append((pos,len(values),end-pos))
            values.extend(block[pos:end])
            pos = end
        pool_ranges.append((first,len(spans)-first))
    for case in cases():
        first = len(patches)
        original = originals[case['source']]
        edited = materialize(case,False)
        patches.extend((i//512,i%512,b) for i,b in enumerate(edited) if b!=original[i])
        reserved = (32,1,32,130,32,32,4,32)[case['source']]
        vectors.append((case['source'],first,len(patches)-first,case['io'],case['change'],
                        case['status'],case['detail'],reserved,case['ready'],case['kind'],case['index'],
                        case['lba'] & 65535,case['lba'] >> 16))
    return dict(seed_bytes=values,seed_spans=spans,seed_pools=pool_ranges,seed_maps=maps,
                seed_sources=seeds,boot_patches=patches,boot_vectors=vectors)


def model_header():
    rows = ['/* Generated synthetic boot-area cases; no boot or restore authority. */']
    for name,values in model_data().items():
        if values and isinstance(values[0],tuple):
            rows.append('static const rb_u16 '+name+'[]['+str(len(values[0]))+'] = {')
            rows.extend('    {'+','.join(map(str,row))+'},' for row in values)
        else:
            rows.append('static const '+('rb_u8' if name=='seed_bytes' else 'rb_u16')+' '+name+'[] = {')
            rows.extend('    '+','.join(map(str,values[i:i+24]))+',' for i in range(0,len(values),24))
        rows.append('};')
    return '\n'.join(rows)+'\n'
