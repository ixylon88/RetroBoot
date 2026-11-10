"""Produce canonical, owned RBCFG fixtures; no import or device write path."""
import struct
import zlib

MAGIC = b'RBCFG\0\0\0'
CLUSTERS = (2800, 2900)
STATE_CLUSTERS = (3000, 3100)
# Reproducible synthetic media only; a future installer must allocate IDs.
FIXTURE_MEDIA_ID = bytes.fromhex('a6216f345cd2467790abc0137d8452e9')
TEST_INSTALL_ID = 0x0000000100000001


def visible(ptype):
    return ptype - 0x10 if ptype in (0x16, 0x1E, 0x1B, 0x1C, 0x17) else ptype


def layout_crc(extents):
    """RBL1 canonical layout from generated MBR/EBR extents, excluding visibility."""
    mbr = extents[0]
    entries, ebrs = [], []
    extended = None
    for i in range(4):
        entry = mbr[446 + i * 16:462 + i * 16]
        start, length = struct.unpack_from('<II', entry, 8)
        entries.append((start, length, 0, visible(entry[4]), i + 1, 0))
        if entry[4] in (5, 15): extended = start
    current = extended
    while current is not None:
        if current in ebrs or len(ebrs) == 16: raise ValueError('Invalid fixture EBR chain')
        ebrs.append(current)
        sector = extents[current * 512]
        start, length = struct.unpack_from('<II', sector, 454)
        if sector[450]: entries.append((current + start, length, current, visible(sector[450]), len(entries) - 3, 1))
        current = extended + struct.unpack_from('<I', sector, 470)[0] if sector[466] else None
    data = b'RBL1' + struct.pack('<HH', len(entries), len(ebrs))
    data += b''.join(struct.pack('<I', lba) for lba in ebrs)
    data += b''.join(struct.pack('<IIIHHH', *entry) for entry in entries)
    return zlib.crc32(data)


def seal(record):
    if len(record) != 512: raise ValueError('A configuration record is exactly one sector')
    result = bytearray(record)
    struct.pack_into('<I', result, 508, zlib.crc32(result[:508]))
    return bytes(result)


def encode(*, disk_id, layout, admin_start, admin_sectors, generation=1,
           profiles=(), default_id=0, countdown=0, language='en', media_id=None):
    version, stride = (1, 48) if media_id is None else (2, 52)
    if media_id is not None and (not isinstance(media_id, bytes) or len(media_id) != 16 or not any(media_id)):
        raise ValueError('Invalid media identity')
    if (not 1 <= generation <= 0xFFFFFFFF or not 1 <= disk_id <= 0xFFFFFFFF
            or not 0 <= layout <= 0xFFFFFFFF or not 0 < admin_start < admin_start + admin_sectors <= 0x100000000
            or not 0 <= countdown <= 60 or language not in ('en', 'de') or len(profiles) > 8):
        raise ValueError('Invalid configuration header')
    result = bytearray(512)
    struct.pack_into('<8sHHIIIIIIHHIB', result, 0, MAGIC, version, 64, 512, generation,
                     disk_id, layout, admin_start, admin_sectors, len(profiles), countdown,
                     default_id, int(language == 'de'))
    if version == 2: result[48:64] = media_id
    identifiers = set()
    for index, p in enumerate(profiles):
        name = p['name'].encode('cp437')
        slot, ptype, kind = p['slot'], p['type'], p.get('kind', 1)
        installed, approved = p.get('installed', 0), p.get('approved', 0)
        install_id = p.get('install_id', 0)
        mask = p.get('visible_mask', 1 << (slot - 1)) if 1 <= slot <= 4 else 0
        if (not 1 <= p['id'] <= 0xFFFFFFFF or p['id'] in identifiers
                or not 1 <= slot <= 4 or ptype not in (6, 14, 11, 12, 7) or kind not in (1, 2)
                or installed not in (0, 1, 2) or approved not in (0, 1) or (approved and installed != 2)
                or mask & ~15 or not mask & (1 << (slot - 1))
                or (kind == 1 and (mask != 1 << (slot - 1) or ptype == 7))
                or not 0 < p['start'] < p['start'] + p['sectors'] <= 0x100000000
                or not 1 <= len(name) <= 24 or any(c < 32 or c == 127 for c in name)
                or not 0 <= install_id <= 0xFFFFFFFFFFFFFFFF
                or (version == 2 and approved and install_id == 0)):
            raise ValueError('Invalid profile')
        identifiers.add(p['id'])
        struct.pack_into('<IIIBBBBBBBB24s', result, 64 + index * stride, p['id'], p['start'], p['sectors'],
                         slot, ptype, kind, installed, approved, mask, len(name), 0, name)
        if version == 2: struct.pack_into('<Q', result, 108 + index * stride, install_id)
    if default_id != 0 and default_id not in identifiers: raise ValueError('Unknown default entry ID')
    return seal(result)


def install_records(extents, admin, *, language='en', profiles=(), state_records=None):
    """Allocate owned configuration/state files in the generated fixture root."""
    extents = dict(extents)
    start = admin['start_lba']
    fat = admin['fat']
    spf, spc = fat['sectors_per_fat'], fat['sectors_per_cluster']
    root_lba, data_lba = start + 1 + 2 * spf, start + 1 + 2 * spf + 32
    record = encode(disk_id=struct.unpack_from('<I', extents[0], 440)[0], layout=layout_crc(extents),
                    admin_start=start, admin_sectors=admin['sectors'], language=language, profiles=profiles,
                    media_id=FIXTURE_MEDIA_ID)
    records = (record, record) + (() if state_records is None else tuple(state_records))
    if len(records) not in (2, 4) or any(len(r) != 512 for r in records): raise ValueError('Invalid record set')
    root = bytearray(extents[root_lba * 512])
    tables = [bytearray(extents[(start + 1 + i * spf) * 512]) for i in range(2)]
    for index, (cluster, record) in enumerate(zip(CLUSTERS + STATE_CLUSTERS, records)):
        if cluster >= fat['data_clusters'] + 2: raise ValueError('Configuration cluster outside admin volume')
        entry = 672 + index * 32
        if any(root[entry:entry + 32]): raise ValueError('Configuration directory slot is occupied')
        root[entry:entry + 11] = (b'RBCFG   ' if index < 2 else b'RBSTATE ') + bytes([ord('A') + index % 2]) + b'  '
        root[entry + 11] = 0x20
        struct.pack_into('<HI', root, entry + 26, cluster, 512)
        for table in tables:
            if struct.unpack_from('<H', table, cluster * 2)[0]: raise ValueError('Configuration cluster is occupied')
            struct.pack_into('<H', table, cluster * 2, 0xFFFF)
        offset = (data_lba + (cluster - 2) * spc) * 512
        if offset in extents: raise ValueError('Configuration extent already exists')
        extents[offset] = record
    extents[root_lba * 512] = bytes(root)
    for i, table in enumerate(tables): extents[(start + 1 + i * spf) * 512] = bytes(table)
    return extents


def model_record():
    mbr, ebr = bytearray(512), bytearray(512)
    mbr[450], mbr[498], ebr[450] = 6, 5, 0x16
    struct.pack_into('<II', mbr, 454, 131072, 5073)
    struct.pack_into('<II', mbr, 502, 63, 128520)
    struct.pack_into('<II', ebr, 454, 63, 128457)
    return encode(disk_id=0x52425431, layout=layout_crc({0: mbr, 63 * 512: ebr}),
                  admin_start=126, admin_sectors=128457, generation=100, default_id=0x12345678,
                  countdown=10, language='de', profiles=[dict(id=0x12345678, name='ÄÖÜäöüß test',
                  slot=1, type=6, start=131072, sectors=5073, installed=2, approved=1)])


def model_header():
    data = model_record()
    return ('/* Generated host-to-C16 format vector. */\n'
            'static const rb_u8 rb_config_vector[512] = {\n'
            + '\n'.join('    ' + ','.join(str(c) for c in data[i:i + 16]) + ',' for i in range(0, 512, 16))
            + '\n};\n')
