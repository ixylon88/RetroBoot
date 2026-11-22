"""Independent source sectors, MBR history and expected bytes for the completion check."""
import struct
import zlib

try:
    from .backup_container import Chunk, encode, inspect
    from .backup_plan_vectors import SYSTEM, sectors as model_disk
    from .backup_record_vectors import seal as seal_container
    from .mbr_restart_fixtures import CARRIER, TARGET, WITNESS, Checkpoint, ORIGIN, header, seal
    from .rescue_plan_fixtures import disk, stream_reference
except ImportError:
    from backup_container import Chunk, encode, inspect
    from backup_plan_vectors import SYSTEM, sectors as model_disk
    from backup_record_vectors import seal as seal_container
    from mbr_restart_fixtures import CARRIER, TARGET, WITNESS, Checkpoint, ORIGIN, header, seal
    from rescue_plan_fixtures import disk, stream_reference

SECTOR = 512
STAGE_ADDRESS = 0x20000


def mbr_crc(block, changed=False):
    data = bytearray(block)
    if changed:
        data[77] ^= 1
    struct.pack_into('<I', data, 428, zlib.crc32(data[:428]))
    return bytes(data)


def wire(reserved=32):
    data = bytearray(stream_reference())
    for pos in (5, 6):
        start = pos * SECTOR
        data[start:start + SECTOR] = mbr_crc(data[start:start + SECTOR])
    base = seal_container(data)
    if reserved == 32:
        return base
    identity, entries = inspect(base)
    source = model_disk(32, reserved)
    chunks = []
    for e in entries:
        n = reserved if e['kind'] == 4 and e['lba'] == SYSTEM else e['sectors']
        if e['kind'] <= 2:
            start = e['file_sector'] * SECTOR
            block = base[start:start+SECTOR]
        else:
            block = b''.join(source.get(e['lba']+i, bytes(SECTOR)) for i in range(n))
        chunks.append(Chunk(e['kind'], e['index'], e['lba'], block, e['owner_start'], e['owner_sectors']))
    return encode(identity, chunks)


def record(tag, point, capacity, original, approved, *, target_id=TARGET, carrier_id=CARRIER):
    data = bytearray(header(tag, point, carrier_id, target_id=target_id, capacity=capacity))
    struct.pack_into('<II', data, 64, zlib.crc32(original), zlib.crc32(approved) if point.approved else 0)
    return seal(data)


def alternatives(data):
    """Complete altered files; the host also checks each test's framing independently."""
    _, entries = inspect(data)
    def at(kind, index=0):
        return next(e['file_sector'] for e in entries if (e['kind'], e['index']) == (kind, index)) * SECTOR

    overlap = bytearray(data)
    config_b = next(i for i, e in enumerate(entries) if e['kind'] == 6)
    struct.pack_into('<I', overlap, SECTOR + config_b * 32 + 4, entries[config_b-1]['lba'])
    area = bytearray(data)
    area[at(4) + SECTOR] ^= 1  # FAT32 FSInfo, with valid outer framing.
    bad_state = bytearray(data)
    bad_state[at(8) + 8] ^= 1  # Unsupported state version despite intact CRCs.
    later = bytearray(data)
    struct.pack_into('<I', later, at(5) + 16, 2)
    values = dict(overlap=seal_container(overlap), boot_area=seal_container(area),
                  saved_state=seal_container(bad_state, 8), changed_config=seal_container(later, 1))
    for kind, label in ((1, 'sub_original'), (2, 'sub_approved')):
        copy = bytearray(data)
        start = at(kind)
        copy[start:start + SECTOR] = mbr_crc(copy[start:start + SECTOR], True)
        values[label] = bytes(copy)
    return values


def array(values):
    return '{' + ','.join(str(v) for v in values) + '}'


def claim_initializer(data):
    identity, entries = inspect(data)
    extent_fields = ('kind','index','lba','sectors','file_sector','crc32','owner_start','owner_sectors')
    descriptors = [array([e[k] for k in extent_fields]) for e in entries]
    fields = [identity.generation, identity.disk_id, identity.layout_crc, identity.admin_start,
              identity.admin_sectors, identity.capacity, 0, len(entries), identity.route, identity.heads,
              identity.sectors_per_track]
    return ','.join(map(str, fields)) + ',' + array(identity.media_id) + ',{\n' + ',\n'.join(descriptors) + '}'


def model_header():
    data = wire()
    identity, _ = inspect(data)
    blocks, sparse, spans = [], [], []

    def block_id(piece):
        if len(piece) != SECTOR:
            raise ValueError('Expected one complete sector')
        if piece not in blocks:
            blocks.append(piece)
            changes = [(i, byte) for i, byte in enumerate(piece) if byte]
            spans.append((len(sparse), len(changes)))
            sparse.extend(changes)
        return blocks.index(piece)

    def rows(name, values):
        return name + ' = {\n' + ',\n'.join(array(row) for row in values) + '\n};\n'

    block_id(bytes(SECTOR))
    source = []
    _, extents = disk()
    for offset, extent in sorted(extents.items()):
        for i in range(0, len(extent), SECTOR):
            piece = extent[i:i + SECTOR]
            if any(piece):
                source.append(((offset+i)//SECTOR, block_id(piece)))

    original, approved = data[5*SECTOR:6*SECTOR], data[6*SECTOR:7*SECTOR]
    current = Checkpoint(3, 2, 2)
    records = {}
    for name, point in (('approved', current), ('original', ORIGIN)):
        sectors = [record(b'RBWIT001', point, identity.capacity, original, approved),
                   original, approved if point.approved else bytes(SECTOR)]
        records['witness_' + name] = [block_id(s) for s in sectors]
        sectors = [record(b'RBORG001', ORIGIN, identity.capacity, original, approved), original,
                   record(b'RBCMT001', point, identity.capacity, original, approved), sectors[2]]
        records['carrier_' + name] = [block_id(s) for s in sectors]

    scenarios = []
    for name, altered in alternatives(data).items():
        replacements = [(p//SECTOR, block_id(altered[p:p+SECTOR])) for p in range(0, len(data), SECTOR)
                        if data[p:p+SECTOR] != altered[p:p+SECTOR]]
        scenarios.append(rows('static const sector_ref ' + name + '[]', replacements))
    long_data = wire(130)
    long_source = model_disk(32, 130)
    baseline = {sector: blocks[id_] for sector, id_ in source}
    changes = [(lba, block_id(block)) for lba, block in sorted(long_source.items())
               if block != baseline.get(lba, bytes(SECTOR))]
    return (f'#define FILE_SECTORS {len(data)//SECTOR}U\n'
            + f'#define LONG_SECTORS {len(long_data)//SECTOR}U\n'
            + 'static const rb_backup claims = {' + claim_initializer(data) + '};\n'
            + 'static const rb_backup long_claims = {' + claim_initializer(long_data) + '};\n'
            + rows('static const sector_ref long_changes[]', changes)
            + 'static const rb_mbr_binding binding = {{' + array(TARGET) + ',' + str(identity.capacity)
            + ',0},' + array(CARRIER) + '};\nstatic const rb_u8 witness_id[16] = ' + array(WITNESS) + ';\n'
            + ''.join('static const rb_u8 '+key+'[] = '+array(value)+';\n' for key, value in records.items())
            + rows('static const sector_ref source_sectors[]', source) + ''.join(scenarios)
            + rows('static const rb_u16 spans[][2]', spans) + rows('static const patch bytes[]', sparse))
