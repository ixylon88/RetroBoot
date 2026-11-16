"""Sparse owned HDD model and independent capture-plan/read expectations."""
import struct
import zlib

try:
    from .backup_boot_vectors import fixture
    from .backup_container import inspect
    from .config_records import seal
    from .rescue_match_fixtures import acquisition, disk, RECORDS, CAPACITY
except ImportError:
    from backup_boot_vectors import fixture
    from backup_container import inspect
    from config_records import seal
    from rescue_match_fixtures import acquisition, disk, RECORDS, CAPACITY

SYSTEM = 131072
ACQUISITION = len(acquisition())
HEADERS = ACQUISITION * 2
PASS = HEADERS + 36


def sectors(bits=32, reserved=32, backup=6, kind=None):
    _, extents = disk()
    result = {at//512+i: block[i*512:(i+1)*512]
              for at, block in extents.items() for i in range(len(block)//512)}
    raw = fixture(bits=bits, reserved=min(reserved,32), backup=backup, kind=0x0B if kind == 0x1B else kind)
    _, entries = inspect(raw)
    for e in entries:
        first = raw[e['file_sector']*512:(e['file_sector']+1)*512]
        if e['kind'] == 2: result[0] = first
        elif e['kind'] == 4 and e['lba'] == SYSTEM:
            for i in range(e['sectors']):
                result[SYSTEM+i] = raw[(e['file_sector']+i)*512:(e['file_sector']+i+1)*512]
        elif e['kind'] >= 5: result[RECORDS[e['kind']-5]] = first
    if kind == 0x1B:
        mbr=bytearray(result[0]); mbr[450]=kind; result[0]=bytes(mbr)
    if reserved > 32:
        for i in range(32,reserved):result[SYSTEM+i]=bytes(512)
        vbr=bytearray(result[SYSTEM]); struct.pack_into('<H',vbr,14,reserved); result[SYSTEM]=bytes(vbr)
        if bits==32 and backup:result[SYSTEM+backup]=bytes(vbr)
        for lba in RECORDS[2:]:
            state=bytearray(result[lba]); struct.pack_into('<I',state,84,zlib.crc32(vbr)); result[lba]=seal(state)
    return result


def expected_reads():
    return (acquisition()*2 + [SYSTEM,126] + list(range(SYSTEM,SYSTEM+32)) + [126,0])*2


def check_reads(actual):
    if actual != expected_reads():
        raise ValueError('Capture-plan model addresses or acquisition order differ')


def patches(before, after):
    """Four-byte replacements, including zeros; no native full-disk buffer."""
    result = []
    for lba, block in sorted(after.items()):
        old = before.get(lba, bytes(512))
        for at in range(0, 512, 4):
            if old[at:at+4] != block[at:at+4]:
                result.append((lba, at, int.from_bytes(block[at:at+4], 'little')))
    return result


def cases():
    base = sectors(); result = []

    def add(name, status=0, detail=0, nested=0, index=0, lba=0,
            reads=None, changed=None, initial=None, start=1, io=0, device=0,
            reserved=32, length=71126):
        if reads is None:reads=2*(HEADERS+reserved+4)
        result.append(dict(name=name, status=status, detail=detail, nested=nested,
            index=index, lba=lba, reads=reads, initial=patches(base, initial or base),
            patches=patches({**base, **(initial or {})}, changed or {}),
            start=start, io=io, device=device, reserved=reserved, length=length))

    def edit(lba, offset, width, value):
        block = bytearray(base[lba]); block[offset:offset+width] = value.to_bytes(width, 'little')
        return {lba: bytes(block)}

    add('fat32-edd')
    add('chs', device=1)
    add('edd-with-geometry', device=2)
    add('64-bit-capacity', device=3)
    add('fat16', changed=sectors(16, 1), reserved=1, length=5073)
    add('fat16-four-reserved', changed=sectors(16, 4), reserved=4, length=5073)
    add('over-64k-reserved-area', changed=sectors(reserved=130), reserved=130)
    add('no-backup-copy', changed=sectors(backup=0))
    add('backup-at-ten', changed=sectors(backup=10))
    add('hidden-fat32', changed=sectors(kind=0x1B))
    # 2,035 system-reserved + seven other live sectors + six container/original.
    add('exact-container-limit', changed=sectors(reserved=2035), reserved=2035)
    add('container-one-sector-too-large', 5, 8, lba=RECORDS[3],
        reads=HEADERS+2, changed=sectors(reserved=2036))
    add('large-reserved-area-rejected', 5, 4, lba=SYSTEM,
        reads=HEADERS+1, changed=sectors(reserved=4096))
    add('unsupported-type-07', 3, 16, lba=SYSTEM, reads=HEADERS, changed=sectors(kind=7))
    for name, at, width, value, status in (
        ('signature',510,1,0,2), ('sector-size',11,2,4096,4),
        ('reserved-zero',14,2,0,6), ('hidden-lba',28,4,SYSTEM+1,10)):
        add('vbr-'+name, 3, status, lba=SYSTEM, reads=HEADERS+1, changed=edit(SYSTEM,at,width,value))
    for name, at, value in (('fsinfo-at-two',48,2), ('backup-overlap',50,2), ('backup-end',50,31)):
        add(name, 4, lba=SYSTEM, reads=HEADERS+1, changed=edit(SYSTEM,at,2,value))
    add('missing-device', 1, reads=0, device=4)
    add('missing-reader', 1, reads=0, device=5)
    for code,name in enumerate(('wrong-drive','invalid-mode','empty-capacity','invalid-chs','half-geometry'),6):
        add(name, 2, 1, 2, reads=0, device=code)
    add('unknown-mbr', 2, 6, 1, reads=1, changed=edit(0,432,4,0))
    add('bad-config-crc', 2, 4, 4, lba=RECORDS[0], reads=ACQUISITION-3,
        changed=edit(RECORDS[0],80,1,base[RECORDS[0]][80]^1))
    add('bad-state-crc', 2, 5, 4, lba=RECORDS[2], reads=ACQUISITION-1,
        changed=edit(RECORDS[2],80,1,base[RECORDS[2]][80]^1))
    add('fat-mirror-disagreement', 2, 3, 7, lba=628, reads=ACQUISITION-5,
        changed=edit(628,511,1,1))
    for outer in (0, PASS):
        for at,detail,nested in ((1,2,0),(3,3,1),(5,3,3),(7,3,3),
                (ACQUISITION-4,2,5),(ACQUISITION-3,2,6),
                (ACQUISITION-2,2,7),(ACQUISITION-1,2,8),
                (ACQUISITION,2,0),(ACQUISITION+1,2,0)):
            call = outer+at
            add(f'io-{call}',2,detail,nested,lba=expected_reads()[call-1],reads=call,io=call)
        for at,index in ((HEADERS+1,0),(HEADERS+2,4),
                *((HEADERS+3+offset,0) for offset in (0,1,2,6,7,8,31)),
                (PASS-1,4),(PASS,0)):
            call=outer+at
            add(f'io-{call}',7,1 if at<PASS else 0,index=index,
                lba=expected_reads()[call-1],reads=call,io=call)
    # Valid changes between complete planning passes, including CRC-resealed
    # records: the ordinary target observer sees two internally equal copies.
    changed_config = {}
    for lba in RECORDS[:2]:
        block=bytearray(base[lba]);struct.pack_into('<I',block,16,2)
        changed_config[lba]=seal(block)
    admin=bytearray(base[126]);admin[8]^=1;struct.pack_into('<H',admin,72,0)
    struct.pack_into('<H',admin,72,-sum(struct.unpack('<256H',admin))&65535)
    def bound_header(at,width,value):
        changed=edit(SYSTEM,at,width,value);changed[SYSTEM+6]=changed[SYSTEM]
        for lba in RECORDS[2:]:
            state=bytearray(base[lba]);struct.pack_into('<I',state,84,zlib.crc32(changed[SYSTEM]));changed[lba]=seal(state)
        return changed

    # Live and saved validators agree on FSInfo bounds, but live diagnostics use
    # the physical failing sector. No backup/primary hint equality is required.
    for offset,label in ((1,'primary'),(7,'backup')):
        for at,value,detail,suffix in ((0,0,1,'lead'),(484,0,1,'structure'),(508,0,1,'trail'),
                (4,1,2,'reserved-first'),(496,1,2,'reserved-last'),
                (488,70001,3,'free-range'),(492,1,4,'next-low'),(492,70002,4,'next-high')):
            add(label+'-fsinfo-'+suffix,9,7,detail,lba=SYSTEM+offset,
                reads=HEADERS+3+offset,changed=edit(SYSTEM+offset,at,4,value))
    for offset,at,value,nested,name in ((2,510,0,3,'continuation-signature'),
            (6,100,0xCC,1,'backup-vbr-code'),(8,100,0xCC,2,'backup-continuation')):
        add(name,9,8,nested,lba=SYSTEM+offset,reads=HEADERS+3+offset,
            changed=edit(SYSTEM+offset,at,1,value))
    ready={}
    for lba in RECORDS[2:]:
        state=bytearray(base[lba]);struct.pack_into('<I',state,84,0);ready[lba]=seal(state)
    add('ready-crc-mismatch',9,9,lba=SYSTEM,reads=HEADERS+34,changed=ready)
    older=dict(ready)
    state=bytearray(base[RECORDS[3]]);struct.pack_into('<I',state,16,2);older[RECORDS[3]]=seal(state)
    add('older-ready-crc-ignored',changed=older)
    # Generation two with a wrong claim must be selected and rejected.
    state=bytearray(ready[RECORDS[3]]);struct.pack_into('<I',state,16,2)
    add('selected-ready-crc-mismatch',9,9,lba=SYSTEM,reads=HEADERS+34,
        changed={RECORDS[3]:seal(state)})
    pending={}
    for lba in RECORDS[2:]:
        state=bytearray(base[lba]);state[83]=5;struct.pack_into('<I',state,84,0);pending[lba]=seal(state)
    add('approved-pending-installation',2,11,lba=SYSTEM,reads=ACQUISITION-1,changed=pending)
    for lba in RECORDS[:2]:
        config=bytearray(base[lba]);config[79:81]=bytes((1,0));pending[lba]=seal(config)
    add('pending-installation',changed=pending)
    # Independently valid records can still refer to incompatible installations.
    # These cases exercise the shared saved/live rule after A/B selection.
    def record_change(lbas, at, width, value):
        return {lba:seal(edit(lba,at,width,value)[lba]) for lba in lbas}
    bad_reference=record_change(RECORDS[:2],108,4,2)
    add('bad-reference',2,11,lba=SYSTEM,reads=ACQUISITION-1,changed=bad_reference)
    add('bad-reference-high',2,11,lba=SYSTEM,reads=ACQUISITION-1,
        changed=record_change(RECORDS[:2],112,4,2))
    add('different-installation-kind',2,11,lba=SYSTEM,reads=ACQUISITION-1,
        changed=record_change(RECORDS[2:],82,1,2))
    for phase in (1,2,3,4,7):
        changed={}
        for lba in RECORDS[2:]:
            state=bytearray(base[lba]);state[83]=phase;struct.pack_into('<I',state,84,0);changed[lba]=seal(state)
        add('approved-phase-'+str(phase),2,11,lba=SYSTEM,reads=ACQUISITION-1,changed=changed)
    for family,lbas,at in (('config',RECORDS[:2],108),('state',RECORDS[2:],64)):
        for copy,lba in enumerate(lbas):
            invalid=bytearray(base[lba]);struct.pack_into('<I',invalid,at,2)
            struct.pack_into('<I',invalid,16,2)
            add(f'selected-{family}-{copy}-unlinked',2,11,lba=SYSTEM,reads=ACQUISITION-1,
                changed={lba:seal(invalid)})
            struct.pack_into('<I',invalid,16,1)
            newer=bytearray(base[lbas[1-copy]]);struct.pack_into('<I',newer,16,2)
            add(f'older-{family}-{copy}-unlinked',changed={lba:seal(invalid),lbas[1-copy]:seal(newer)})
    empty={}
    for lba in RECORDS:
        record=bytearray(base[lba]);record[64:508]=bytes(444);struct.pack_into('<H',record,36,0)
        struct.pack_into('<I',record,40,0);empty[lba]=seal(record)
    add('empty-profile-and-state',changed=empty)
    draft={}
    for lba in RECORDS[:2]:
        record=bytearray(base[lba]);record[79:81]=bytes(2);record[108:116]=bytes(8);draft[lba]=seal(record)
    add('unbound-draft',changed=draft)
    multiple={}
    for lba in RECORDS[:2]:
        record=bytearray(base[lba]);struct.pack_into('<H',record,36,8)
        for i in range(8):
            record[64+i*52:116+i*52]=record[64:116];struct.pack_into('<I',record,64+i*52,i+1)
        multiple[lba]=seal(record)
    add('eight-profiles-one-installation',changed=multiple)
    renamed={}
    for lba in RECORDS[:2]:
        record=bytearray(multiple[lba]);record[84+7*52]=ord('X');renamed[lba]=seal(record)
    add('resealed-tail-stable',initial=multiple,changed=renamed)
    add('resealed-tail-inner',2,10,reads=HEADERS,initial=multiple,changed=renamed,start=ACQUISITION+1)
    add('resealed-tail-outer',6,initial=multiple,changed=renamed,start=PASS+1)
    for lba in RECORDS[:2]:
        record=bytearray(multiple[lba]);struct.pack_into('<I',record,108+7*52,2);multiple[lba]=seal(record)
    add('last-profile-unlinked',2,11,7,lba=SYSTEM,reads=ACQUISITION-1,changed=multiple)
    for start,label in ((ACQUISITION+1,'inner'),(PASS+1,'outer')):
        add('unlinked-second-'+label,2,11,lba=SYSTEM,reads=start+ACQUISITION-2,
            changed=bad_reference,start=start)
    add('stale-backup-hints',changed=edit(SYSTEM+1,488,4,123))
    add('hint-boundaries',changed={**edit(SYSTEM+1,488,4,70000),**edit(SYSTEM+7,492,4,70001)})
    for name,changed in (
        ('mbr-code',edit(0,100,1,1)),('ebr-chs',edit(63,447,1,1)),
        ('admin-header',{126:bytes(admin)}),('root-date',edit(629,14,1,1)),
        ('resealed-config',changed_config),('system-oem',bound_header(3,1,0x58)),
        ('fsinfo-hint',edit(SYSTEM+1,488,4,123)),
        ('backup-fsinfo-hint',edit(SYSTEM+7,492,4,456)),
        ('continuation',{**edit(SYSTEM+2,100,1,0xCC),**edit(SYSTEM+8,100,1,0xCC)}),
        ('reserved-tail',edit(SYSTEM+31,511,1,0xA5))):
        add('changed-'+name,6,changed=changed,start=PASS+1)
    add('changed-reserved-count',6,changed=bound_header(14,2,33),start=PASS+1,reads=PASS*2+1)
    add('reserved-count-changes-after-sizing',6,lba=SYSTEM,reads=HEADERS+3,
        changed=bound_header(14,2,33),start=HEADERS+3)
    add('mbr-changed-after-vbrs',6,reads=PASS,changed=edit(0,100,1,1),start=PASS)
    add('mbr-changed-between-inner-acquisitions',6,2,0,reads=ACQUISITION+1,
        changed=edit(0,100,1,1),start=ACQUISITION+1)
    return result


def assertions():
    return 5*len(cases())+15


def model_header(vectors=None):
    lines=['/* Generated owned model; no OS or disk writer. */',
           'typedef struct { rb_u32 lba; rb_u16 offset; rb_u32 value; } rb_plan_patch;',
           'typedef struct { rb_u16 status, detail, nested, index; rb_u32 lba;',
           '    rb_u16 reads, start, io, device, reserved, config_generation, state_generation; rb_u32 length, layout_crc;',
           '    const rb_plan_patch *initial; rb_u16 initial_count;',
           '    const rb_plan_patch *patches; rb_u16 count; } rb_plan_case;']
    def array(name, values):
        lines.append(f'static const rb_plan_patch {name}[] = {{')
        lines.extend(f'    {{{lba}UL, {at}, {value}UL}},' for lba,at,value in values or [(0,0,0)])
        lines.append('};')
    base=sectors(); seed=patches({},base);array('rb_plan_seed',seed)
    vectors=cases() if vectors is None else vectors
    arrays={}
    for c in vectors:
        for field in ('initial','patches'):
            key=tuple(c[field])
            if key not in arrays:
                arrays[key]=f'rb_plan_edits_{len(arrays)}';array(arrays[key],key)
    lines.append('static const rb_plan_case rb_plan_cases[] = {')
    for i,c in enumerate(vectors):
        # Expected layout comes from the independently encoded record binding.
        record=bytearray(base[RECORDS[0]])
        for lba,at,value in c['initial']+c['patches']:
            if lba==RECORDS[0]:struct.pack_into('<I',record,at,value)
        crc=struct.unpack_from('<I',record,24)[0]
        fields=[str(c[k]) for k in ('status','detail','nested','index')]
        fields += [str(c['lba'])+'UL']
        fields += [str(c[k]) for k in ('reads','start','io','device','reserved')]
        records={lba:bytearray(base[lba]) for lba in RECORDS}
        for lba,at,value in c['initial']+c['patches']:
            if lba in records:struct.pack_into('<I',records[lba],at,value)
        fields += [str(max(struct.unpack_from('<I',records[lba],16)[0] for lba in group))
                   for group in (RECORDS[:2],RECORDS[2:])]
        fields += [str(c['length'])+'UL',str(crc)+'UL',arrays[tuple(c['initial'])],str(len(c['initial'])),
                   arrays[tuple(c['patches'])],str(len(c['patches']))]
        lines.append('    {'+', '.join(fields)+'}, /* '+c['name']+' */')
    lines += ['};',f'#define RB_PLAN_SEED_COUNT {len(seed)}U',
              f'#define RB_PLAN_CASES {len(vectors)}U',f'#define RB_PLAN_ACQUISITION {ACQUISITION}U',
              f'#define RB_PLAN_READY_CRC {zlib.crc32(base[SYSTEM])}UL',
              f'#define RB_PLAN_TAIL_CASE {next(i for i,c in enumerate(vectors) if c["name"]=="resealed-tail-inner")}U',
              f'#define RB_PLAN_LINK_CASE {next(i for i,c in enumerate(vectors) if c["name"]=="bad-reference")}U']
    return '\n'.join(lines)+'\n'
