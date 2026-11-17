"""Independent live-address, explicit-MBR and complete wire-output oracles."""
from dataclasses import replace
import struct
import zlib

try:
    from .backup_container import Chunk, encode, inspect
    from .backup_boot_vectors import fixture
    from .backup_plan_vectors import sectors, patches, SYSTEM
    from .backup_payload_vectors import extents, expected_reads as capture_reads, cases as capture_cases
    from .rescue_match_fixtures import acquisition, RECORDS
except ImportError:
    from backup_container import Chunk, encode, inspect
    from backup_boot_vectors import fixture
    from backup_plan_vectors import sectors, patches, SYSTEM
    from backup_payload_vectors import extents, expected_reads as capture_reads, cases as capture_cases
    from rescue_match_fixtures import acquisition, RECORDS


def mbr_bytes(kind):
    return bytes(((0x51 if kind == 1 else 0xA2) + (3 if kind == 1 else 5)*i) & 255 for i in range(512))


def seeds():
    result = []
    for name, bits, reserved, route, capacity in (
            ('fat32', 32, 32, 1, 262144), ('chs', 32, 32, 2, 262144),
            ('wide-capacity', 32, 32, 1, 1 << 32), ('fat16', 16, 1, 1, 262144),
            ('over-64k', 32, 130, 1, 262144), ('one-mib', 32, 2035, 1, 262144),
            ('short-boot-claim', 32, 32, 1, 262144), ('missing-boot-claim', 32, 32, 1, 262144)):
        disk = sectors(bits, reserved)
        identity = replace(inspect(fixture(bits, min(reserved, 32)))[0], generation=17,
                           route=route, heads=16 if route == 2 else 0,
                           sectors_per_track=63 if route == 2 else 0, capacity=capacity)
        chunks = [Chunk(kind, 0, 0, mbr_bytes(kind)) for kind in (1, 2)]
        for kind, index, lba, count in extents(reserved)[1:]:
            owner = 0 if kind == 3 else SYSTEM if lba == SYSTEM else 126
            length = 0 if not owner else (5073 if bits == 16 else 71126) if owner == SYSTEM else 128457
            data = b''.join(disk.get(lba+i, bytes(512)) for i in range(count))
            if name == 'short-boot-claim' and lba == SYSTEM: data = data[:-512]
            if name == 'missing-boot-claim' and kind == 4 and index == 1: continue
            chunks.append(Chunk(kind, index, lba, data, owner, length))
        result.append(dict(name=name, disk=disk, wire=encode(identity, chunks),
                           identity=identity, reserved=reserved))
    return result


def reads_for(seed):
    reserved = seed['reserved']
    live = [lba+i for _, _, lba, count in extents(reserved) for i in range(count)]
    validation = acquisition()*2 + [SYSTEM, 126] + list(range(SYSTEM, SYSTEM+reserved)) + [126]
    capture = (validation + live + [0])*2
    return capture, live[1:]


def expected_reads():
    capture, live = reads_for(seeds()[0])
    assert capture == capture_reads()
    return capture + live*2 + capture


def check_reads(actual):
    if actual != expected_reads(): raise ValueError('Live source binding addresses or order differ')


def cases():
    fixtures = seeds(); result = []
    cap, live = reads_for(fixtures[0]); a, n = len(cap), len(live)
    size = len(fixtures[0]['wire']) // 512
    entries = inspect(fixtures[0]['wire'])[1]

    def add(name, seed=0, fault=0, at=0, status=0, detail=0, edits=(), disk_edits=(),
            reads=None, mbrs=4, sinks=None, capture=(0, 0, 0, 0), lba=0,
            stream=0, pos=0, file_sectors=0):
        prefix, payload = reads_for(fixtures[seed])
        sectors_in_file = len(fixtures[seed]['wire']) // 512
        e = next((e for e in entries if e['file_sector'] <= pos < e['file_sector']+e['sectors']), None)
        result.append(dict(name=name, seed=seed, fault=fault, at=at, status=status, detail=detail,
            edits=edits, disk_edits=disk_edits, reads=2*(len(prefix)+len(payload)) if reads is None else reads,
            mbrs=mbrs, sinks=sectors_in_file if sinks is None else sinks, capture=capture, lba=lba,
            stream=stream, pos=pos, kind=e['kind'] if e else 0, index=e['index'] if e else 0,
            file_sectors=file_sectors))

    for i in range(6): add(fixtures[i]['name'], seed=i)
    # A closing failure follows success without poisoning/reinitializing the result.
    add('closing-last-read', fault=1, at=2*(a+n), status=3, reads=2*(a+n), capture=(7,0,0,0))
    add('closing-first-read', fault=1, at=a+2*n+1, status=3, reads=a+2*n+1, capture=(2,2,0,0))
    capture_vectors = {c['name']: c for c in capture_cases()}
    for source in ('unknown-mbr', 'primary-fsinfo-lead', 'bad-reference'):
        c = capture_vectors[source]
        add('capture-'+source, status=3, reads=c['reads'], mbrs=0, sinks=0,
            disk_edits=c['initial']+c['patches'], capture=(c['status'],c['detail'],c['nested'],c['index']), lba=c['lba'])
    add('preflight-io', fault=1, at=1, status=3, reads=1, mbrs=0, sinks=0, capture=(2,2,0,0))
    for phase in (0,1):
        for offset, lba in enumerate(live):
            pos=7+offset; at=a+phase*n+offset+1
            add(f'live-io-{phase}-{offset}', fault=1, at=at, status=6, detail=3, reads=at,
                mbrs=2+phase*2, sinks=pos if phase else 0, stream=3, pos=pos)
        add(f'resealed-stream-{phase}', fault=5, at=a+(phase+1)*n, status=6, detail=5,
            reads=a+2*n, stream=5)
        at=a+phase*n+33
        add(f'changed-stream-{phase}', fault=4, at=at, status=6, detail=4, reads=at,
            mbrs=2+phase*2, sinks=40 if phase else 0, stream=4, pos=8)
    for at in range(1,5):
        phase=(at-1)//2; pos=5+(at-1)%2
        add(f'explicit-mbr-io-{at}', fault=2, at=at, status=6, detail=3,
            reads=a+phase*n, mbrs=at, sinks=pos if phase else 0, stream=3, pos=pos)
    for pos in (0,5,6,size-1):
        add(f'sink-{pos}', fault=3, at=pos, status=6, detail=6,
            reads=a+n+max(0,pos-6), mbrs=2+min(2,max(0,pos-4)), sinks=pos+1, stream=6, pos=pos)
    add('closing-resealed-config', fault=6, at=a+2*n+1, status=7)
    # Framing-valid but stale or invented claims must never steer disk reads.
    meta=fixtures[0]['wire'][:2560]
    def word(at):return int.from_bytes(meta[at:at+4],'little')
    for name, detail, edits in (
            ('capacity',1,((48,262145),)), ('route',2,((40,0x00100002),(44,63))),
            ('disk-id',3,((20,word(20)^1),)), ('media-id',3,((56,word(56)^1),)),
            ('layout',4,((24,word(24)^1),))):
        add('identity-'+name, status=4, detail=detail, edits=edits, reads=a, mbrs=0, sinks=0)
    for name, index, edits in (
            ('ebr-address',2,((512+2*32+4,64),)),
            ('record-address',5,((512+5*32+4,RECORDS[0]+1),)),
            ('owner-range',3,((512+3*32+20,SYSTEM-1),(512+3*32+24,71127))),
            ('payload-crc',8,((512+8*32+16,word(512+8*32+16)^1),))):
        add('extent-'+name, status=5, detail=index, edits=edits, reads=a, mbrs=0, sinks=0,
            lba=entries[index]['lba'])
    add('extent-short',seed=6,status=5,detail=3,reads=a,mbrs=0,sinks=0,lba=SYSTEM)
    add('extent-missing',seed=7,status=5,reads=a,mbrs=0,sinks=0)
    for name, detail, edits, size_override in (
            ('role',2,((512,0),),0), ('role-index',5,((512+32,0x00010002),),0),
            ('wrapped-address',4,((512+4,0xFFFFFFFF),),0), ('file-offset',4,((512+12,6),),0),
            ('file-limit',2,(),2049)):
        add('metadata-'+name,status=2,detail=detail,edits=edits,file_sectors=size_override,reads=0,mbrs=0,sinks=0)
    for fault,name in enumerate(('result','metadata','device','reader','mbr-source','sink'),10):
        add('null-'+name,fault=fault,status=1,reads=0,mbrs=0,sinks=0)
    return result


def assertions():return 5*len(cases())


def model_header():
    fixtures=seeds(); vectors=cases(); lines=[
        'typedef struct { rb_u32 lba; rb_u16 offset; rb_u32 value; } rb_live_patch;',
        'typedef struct { const rb_live_patch *disk, *metadata; rb_u16 disk_count, metadata_count, sectors;',
        '    rb_rescue_device device; } rb_live_seed;',
        'typedef struct { rb_u16 seed, fault; rb_u32 at; rb_u16 status, detail;',
        '    rb_u16 edit, edits, disk_edit, disk_edits, reads, mbrs, sinks;',
        '    rb_u16 capture_status, capture_detail, capture_nested, capture_index;',
        '    rb_u32 lba; rb_u16 stream, kind, index; rb_u32 pos; rb_u16 size; } rb_live_case;']
    def table(name, data):
        lines.append('static const rb_live_patch '+name+'[] = {')
        lines.extend('    {%dUL,%d,%dUL},'%p for p in (data or [(0,0,0)]))
        lines.append('};')
    base=sectors();table('live_disk_base',patches({},base))
    lines.append('#define RB_LIVE_DISK_BASE %dU'%len(patches({},base)))
    for i,s in enumerate(fixtures):
        table('live_disk_'+str(i),patches(base,s['disk']))
        raw={i:s['wire'][i*512:(i+1)*512] for i in range(5)}
        table('live_metadata_'+str(i),patches({},raw))
    lines.append('static const rb_live_seed live_seeds[] = {')
    for i,s in enumerate(fixtures):
        d=s['identity'];raw={i:s['wire'][i*512:(i+1)*512] for i in range(5)}
        lines.append('    {live_disk_%d,live_metadata_%d,%d,%d,%d,{0x80,%d,%d,%d,%dUL,%dUL}},'%(
            i,i,len(patches(base,s['disk'])),len(patches({},raw)),len(s['wire'])//512,
            int(d.route==1),d.heads,d.sectors_per_track,d.capacity&0xFFFFFFFF,d.capacity>>32))
    lines.append('};'); edits=[];disk_edits=[]
    for c in vectors:
        c['edit']=len(edits);edits.extend((0,at,value) for at,value in c['edits'])
        c['disk_edit']=len(disk_edits);disk_edits.extend(c['disk_edits'])
    table('live_edits',edits);table('live_disk_edits',disk_edits)
    lines.append('static const rb_live_case live_cases[] = {')
    for c in vectors:
        values=[c['seed'],c['fault'],c['at'],c['status'],c['detail'],c['edit'],len(c['edits']),
                c['disk_edit'],len(c['disk_edits']),c['reads'],c['mbrs'],c['sinks'],*c['capture'],
                c['lba'],c['stream'],c['kind'],c['index'],c['pos'],c['file_sectors']]
        lines.append('    {'+','.join(str(v)+('UL' if j in (2,16,20) else '') for j,v in enumerate(values))+'},')
    lines.extend(['};','#define RB_LIVE_CASES %dU'%len(vectors)])
    return '\n'.join(lines)+'\n'
