"""Synthetic saved-record consistency fixtures; not collected disk backups."""
import struct
import zlib

try:
    from .backup_container import Identity, Chunk, encode
    from .config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, layout_crc, encode as configuration
    from .state_records import encode as installation_state
except ImportError:
    from backup_container import Identity, Chunk, encode
    from config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, layout_crc, encode as configuration
    from state_records import encode as installation_state


def fixture(chain=False):
    mbr, ebr, second = bytearray(512), bytearray(512), bytearray(512)
    mbr[432:436] = b'RBM1'
    struct.pack_into('<II', mbr, 436, 126, 0x52425431)
    mbr[446], mbr[450], mbr[498], ebr[450] = 0x80, 6, 5, 0x16
    struct.pack_into('<II', mbr, 454, 131072, 5073)
    struct.pack_into('<II', mbr, 502, 63, 130937 if chain else 128520)
    struct.pack_into('<II', ebr, 454, 63, 128457)
    mbr[510:] = ebr[510:] = second[510:] = b'\x55\xaa'
    extents = {0: mbr, 63*512: ebr}
    if chain:
        ebr[466] = 5
        struct.pack_into('<II', ebr, 470, 129000-63, 2000)
        second[450] = 6
        struct.pack_into('<II', second, 454, 63, 1000)
        extents[129000*512] = second
    binding = dict(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126, admin_sectors=128457)
    target = dict(install_id=TEST_INSTALL_ID, slot=1, type=6, kind=1, start=131072, sectors=5073)
    config = configuration(**binding, media_id=FIXTURE_MEDIA_ID,
                           profiles=[dict(target, id=1, name='Test VBR', installed=2, approved=1)])
    state = installation_state(**binding, installations=[dict(target, phase=6, vbr_crc=0x12345678)])
    # The original sector and boot bytes are deliberately opaque zero patterns.
    # Acceptance must not imply an executable boot path or an original-MBR proof.
    chunks = [Chunk(1, 0, 0, bytes(512)), Chunk(2, 0, 0, bytes(mbr)), Chunk(3, 0, 63, bytes(ebr))]
    if chain:
        chunks.append(Chunk(3, 1, 129000, bytes(second)))
    chunks += [Chunk(4, 0, 126, bytes(512), 126, 128457), Chunk(4, 1, 131072, bytes(512), 131072, 5073)]
    if chain:
        chunks.append(Chunk(4, 2, 129063, bytes(512), 129063, 1000))
    chunks += [Chunk(kind, 0, 11603 + 400*(kind-5), config if kind < 7 else state, 126, 128457)
               for kind in range(5, 9)]
    return encode(Identity(1, binding['disk_id'], binding['layout'], 126, 128457, 262144, FIXTURE_MEDIA_ID), chunks)


def entries(data):
    return [struct.unpack_from('<HH7I', data, 512 + i*32) for i in range(struct.unpack_from('<H', data, 36)[0])]


def seal(data, record_mask=0):
    """Reseal outer integrity separately from the four embedded record CRCs."""
    data = bytearray(data)
    for i, e in enumerate(entries(data)):
        kind, _, _, sectors, file_sector, _, _, _, _ = e
        start, end = file_sector*512, (file_sector+sectors)*512
        if kind in range(5, 9) and record_mask & (1 << (kind-5)):
            struct.pack_into('<I', data, start+508, zlib.crc32(data[start:start+508]))
        struct.pack_into('<I', data, 512 + i*32 + 16, zlib.crc32(data[start:end]))
    struct.pack_into('<I', data, 72, zlib.crc32(data[512:2560]))
    struct.pack_into('<I', data, 508, zlib.crc32(data[:508]))
    return bytes(data)


def cases():
    seeds = [fixture(), fixture(True)]
    result = []

    def payload(kind, index=0, source=0):
        return next(e[4]*512 for e in entries(seeds[source]) if e[:2] == (kind, index))

    def table(kind, index=0, source=0):
        return 512 + 32*next(i for i,e in enumerate(entries(seeds[source])) if e[:2] == (kind, index))

    def pair(kind, offset, width, value):
        return [(payload(k)+offset, width, value) for k in (kind, kind+1)]

    def add(name, status=0, detail=0, edits=(), records=0, source=0, io=0, change=0, seal_outer=True,
            config_source=0, state_source=0, config_generation=1, state_generation=1):
        result.append(dict(name=name, status=status, detail=detail, edits=list(edits), records=records,
                           source=source, io=io, change=change, seal_outer=seal_outer,
                           config_source=config_source, state_source=state_source,
                           config_generation=config_generation, state_generation=state_generation))

    add('consistent-records')
    add('two-ebr-chain', source=1)
    add('newer-copies', edits=[(payload(6)+16,4,2),(payload(6)+84,1,ord('B')),(payload(8)+16,4,3)],
        records=10, config_source=1, state_source=1, config_generation=2, state_generation=3)
    add('older-copies-remain-valid', edits=[(payload(5)+16,4,4),(payload(7)+16,4,5)],
        records=5, config_generation=4, state_generation=5)
    add('pending-not-approved', edits=pair(5,79,1,1)+pair(5,80,1,0)+pair(7,83,1,2)+pair(7,84,4,0), records=15)
    add('visibility-excluded-from-layout', edits=[(payload(2)+446,1,0),(payload(2)+450,1,0x16)])
    add('opaque-boot-and-original-bytes', edits=[(payload(1),1,0xCC),(payload(4),1,0xCC)])
    add('outer-header-crc', 1, 3, [(24,1,0)], seal_outer=False)
    add('outer-payload-crc', 1, 3, [(payload(5),1,0)], seal_outer=False)
    add('approved-signature', 4, 2, [(payload(2)+510,1,0)])
    add('approved-disk-id', 4, 3, [(payload(2)+440,4,7)])
    add('unsupported-partition', 4, 5, [(payload(2)+450,1,0xEE)])
    add('approved-overlap', 4, 9, [(payload(2)+454,4,1000)])
    add('ebr-signature', 4, 2, [(payload(3)+510,1,0)])
    add('ebr-loop', 4, 12, [(payload(3)+466,1,5),(payload(3)+470,4,0),(payload(3)+474,4,128520)])
    add('missing-ebr', 5, 1, [(table(3)+4,4,64)])
    add('ebr-descriptor-order', 5, 2, [(table(3,0,1)+4,4,129000),(table(3,1,1)+4,4,63),
        # Swap the corresponding sector payloads too, keeping a readable chain.
        *[(payload(3,0,1)+i,1,b) for i,b in enumerate(seeds[1][payload(3,1,1):payload(3,1,1)+512])],
        *[(payload(3,1,1)+i,1,b) for i,b in enumerate(seeds[1][payload(3,0,1):payload(3,0,1)+512])]], source=1)
    first = bytearray(seeds[1][payload(3,0,1):payload(3,0,1)+512])
    first[462:478] = bytes(16)
    layout = layout_crc({0:seeds[1][payload(2,0,1):payload(2,0,1)+512],63*512:first})
    add('unreferenced-ebr', 5, 2, [(payload(3,0,1)+462,8,0),(payload(3,0,1)+470,8,0),(24,4,layout)]
        + [(payload(kind,0,1)+24,4,layout) for kind in range(5,9)], records=15, source=1)
    add('boot-owner-not-in-table', 5, 3, [(table(4,1)+24,4,5074)])
    add('missing-volume-start', 5, 4, [(table(4,1)+4,4,131073)])
    add('boot-owned-by-extended-container', 5, 3, [(table(4)+20,4,63),(table(4)+24,4,128520)])
    add('wrong-marker', 6, 0, [(payload(2)+432,1,0)])
    add('wrong-admin-pointer', 6, 0, [(payload(2)+436,4,127)])
    add('admin-not-hidden', 6, 1, [(payload(3)+450,1,6)])
    add('wrong-layout-claim', 9, 3, [(24,4,0)])
    for kind, outer in ((5,7),(7,8)):
        name = 'config' if kind == 5 else 'state'
        add(name+'-internal-crc', outer, 4, [(payload(kind)+508,1,0)])
        add(name+'-copy-b-internal-crc', outer, 4, [(payload(kind+1)+508,1,0)])
        for offset, label in ((20,'disk-id'),(24,'layout'),(28,'admin-start'),(32,'admin-size')):
            add(name+'-wrong-'+label, outer, 5, [(payload(kind)+offset,4,7)], records=1<<(kind-5))
        add(name+'-unknown-version', outer, 3, [(payload(kind)+8,2,9)], records=1<<(kind-5))
        add(name+'-equal-generation-conflict', outer, 7,
            [(payload(kind+1)+84,1,0x42)], records=1<<(kind+1-5))
        add(name+'-foreign-media', 9, 2, pair(kind,48,1,0), records=3<<(kind-5))
        add(name+'-older-foreign-media', 9, 2,
            [(payload(kind)+48,1,0),(payload(kind+1)+16,4,2)], records=3<<(kind-5))
        add(name+'-older-foreign-copy-b', 9, 2,
            [(payload(kind+1)+48,1,0),(payload(kind)+16,4,2)], records=3<<(kind-5))
    add('config-invalid-profile', 7, 6, pair(5,76,1,4), records=3)
    add('state-invalid-target', 8, 6, pair(7,72,4,131073), records=12)
    add('state-invalid-phase', 8, 6, pair(7,83,1,8), records=12)
    add('unresolved-installation', 10, 0, pair(5,108,8,0x200000001), records=3)
    add('different-installation-kind', 10, 0, pair(7,82,1,2), records=12)
    add('approved-but-not-ready', 10, 0, pair(7,83,1,5)+pair(7,84,4,0), records=12)
    binding = dict(disk_id=0x52425431, layout=struct.unpack_from('<I',seeds[0],24)[0],admin_start=126,admin_sectors=128457)
    legacy = configuration(**binding)
    edits = [(payload(kind)+i,1,b) for kind in (5,6) for i,b in enumerate(legacy)
             if b != seeds[0][payload(kind)+i]]
    add('legacy-config-without-media-id', 9, 1, edits)
    add('older-legacy-copy-b', 9, 1, [(payload(5)+16,4,2)]
        + [(payload(6)+i,1,b) for i,b in enumerate(legacy) if b != seeds[0][payload(6)+i]], records=1)
    empty_config = configuration(**binding,media_id=FIXTURE_MEDIA_ID)
    empty_state = installation_state(**binding)
    edits = [(payload(kind)+i,1,b) for kind in range(5,9)
             for i,b in enumerate(empty_config if kind<7 else empty_state) if b != seeds[0][payload(kind)+i]]
    add('empty-profile-and-installation-lists', edits=edits)
    add('missing-installation-record', 10, 0, [(payload(kind)+i,1,b) for kind in (7,8)
        for i,b in enumerate(empty_state) if b != seeds[0][payload(kind)+i]])
    second_profile = bytearray(seeds[0][payload(5)+64:payload(5)+116])
    struct.pack_into('<I',second_profile,0,2)
    two_profiles = pair(5,36,2,2)+[(payload(kind)+116+i,1,b) for kind in (5,6) for i,b in enumerate(second_profile)]
    add('two-profiles-one-installation', edits=two_profiles, records=3)
    add('second-profile-unresolved', 10, 1, two_profiles+pair(5,160,4,9), records=3)
    # Calls 1..14 are the initial complete container pass. The semantic pass
    # rereads only the approved MBR, EBR and four complete config/state records.
    for call in (1, 5, 14):
        add('container-read-error-'+str(call), 1, 1, io=call)
    for call in range(15, 21):
        add('semantic-read-error-'+str(call), 2, io=call)
        add('semantic-changed-'+str(call), 3, change=call)
    return result


def materialize(case):
    data = bytearray(fixture(bool(case['source'])))
    for offset, width, value in case['edits']:
        data[offset:offset+width] = value.to_bytes(width,'little')
    return seal(data,case['records']) if case['seal_outer'] else bytes(data)


def model_header():
    seeds = [fixture(),fixture(True)]
    lines = ['/* Synthetic saved-record vectors; no collected disk snapshot. */']
    for i,data in enumerate(seeds):
        lines += [f'static const rb_u8 record_seed_{i}[{len(data)}] = {{']
        lines += [','.join(str(b) for b in data[n:n+32])+',' for n in range(0,len(data),32)]
        lines += ['};']
    lines += ['static const rb_u8 * const record_seeds[] = {record_seed_0,record_seed_1};',
              'static const rb_u16 record_sizes[] = {14,16};']
    patches, rows = [], []
    for case in cases():
        start = len(patches)
        # Keep only effective byte changes. This shrinks sector-swap fixtures.
        for offset,width,value in case['edits']:
            patches += [(offset+i,b) for i,b in enumerate(value.to_bytes(width,'little')) if b != seeds[case['source']][offset+i]]
        rows.append((case['source'],start,len(patches)-start,case['records'],int(case['seal_outer']),
                     case['io'],case['change'],case['status'],case['detail'],case['config_source'],case['state_source'],
                     case['config_generation'],case['state_generation']))
    lines += ['static const rb_u16 record_patches[][2] = {']
    lines += ['{'+','.join(map(str,row))+'},' for row in patches]
    lines += ['};','static const rb_u16 record_vectors[][13] = {']
    lines += ['{'+','.join(map(str,row))+'},' for row in rows]
    lines += ['};']
    return '\n'.join(lines)+'\n'
