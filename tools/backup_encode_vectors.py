"""Independent Python wire images for the native metadata encoder model."""
from dataclasses import replace
try:
    from .backup_container import Chunk, encode, inspect
    from .backup_vectors import cases as decode_cases, pattern, sources as decode_sources
except ImportError:
    from backup_container import Chunk, encode, inspect
    from backup_vectors import cases as decode_cases, pattern, sources as decode_sources


def repack(data, count):
    identity, entries = inspect(data)
    # Keep both MBRs, one boot area and all four records. Vary table boundaries
    # by dropping optional EBR/boot descriptors, then explicitly reindex them.
    ebrs = min(16, count - 7)
    chosen = (entries[:2] + [e for e in entries if e['kind'] == 3][:ebrs]
              + [e for e in entries if e['kind'] == 4][:count - 6 - ebrs] + entries[-4:])
    chunks, position, indices = [], 5, {}
    for entry in chosen:
        kind = entry['kind']; index = indices.get(kind, 0); indices[kind] = index + 1
        payload = b''.join(pattern(n) for n in range(position, position + entry['sectors']))
        chunks.append(Chunk(kind, index, entry['lba'], payload, entry['owner_start'], entry['owner_sectors']))
        position += entry['sectors']
    return encode(identity, chunks)


def sources():
    result = decode_sources()
    result += [repack(result[3], count) for count in (7, 15, 16, 17, 31, 32, 33)]
    # Nontrivial bytes in both halves of capacity and in physical/owner LBAs.
    identity, entries = inspect(result[0])
    identity = replace(identity, generation=0x10203040, disk_id=0x50607080,
                       layout_crc=0x90A0B0C0, admin_start=0x10203040,
                       capacity=0x0102030405)
    chunks = []
    for e in entries:
        start = e['file_sector'] * 512
        delta = identity.admin_start - 126 if e['kind'] >= 4 else 0
        chunks.append(Chunk(e['kind'], e['index'], e['lba'] + delta,
            result[0][start:start + e['sectors'] * 512],
            e['owner_start'] + delta, e['owner_sectors']))
    result.append(encode(identity, chunks))
    return result


def cases():
    # Wire-only fields do not exist in rb_backup. The encoder supplies their
    # canonical values; decoder-only CRC/read errors belong to its own model.
    wire_only = {'magic', 'version', 'header-size', 'file-size', 'entry-stride',
                 'reserved-word', 'reserved-header', 'unused-descriptor', 'descriptor-flags'}
    result = [dict(c, decoded=c['expected']) for c in decode_cases()
              if c['name'] not in wire_only and c['reseal']
              and c['fail_sector'] == c['corrupt_sector'] == 0xFFFF]

    def add(name, expected=0, edits=(), source=0, decoded=None):
        result.append(dict(name=name, expected=expected, edits=edits, source=source,
                           reseal=True, file_sectors=0, fail_sector=0xFFFF,
                           corrupt_sector=0xFFFF, decoded=expected if decoded is None else decoded))

    for source, count in enumerate((7, 15, 16, 17, 31, 32, 33), 4):
        add('table-count-' + str(count), source=source)
    add('asymmetric-wide-fields', source=11)
    add('current-mbr-is-not-original', 2, [(512, 2, 0)])
    add('zero-layout-crc-is-a-value', edits=[(24, 4, 0)])
    add('maximum-generation-is-a-value', edits=[(16, 4, 0xFFFFFFFF)])
    add('payload-crc-is-only-a-claim', edits=[(512 + 16, 4, 0)], decoded=3)
    add('payload-crc-all-ones', edits=[(544 + 16, 4, 0xFFFFFFFF)], decoded=3)
    add('maximum-index-is-rejected', 5, [(512 + 2, 2, 0xFFFF)])
    add('maximum-file-offset-is-rejected', 4, [(512 + 12, 4, 0xFFFFFFFF)])
    add('maximum-sector-count-is-rejected', 4, [(608 + 8, 4, 0xFFFFFFFF)])
    return result


def assertions():
    # Six out-of-order/repeated sector requests, three assertions each; one
    # source/result guard assertion, plus two for accepted framing round trips.
    return sum(19 + (2 if c['expected'] == 0 else 0) for c in cases()) + 8


def model_header():
    lines = ['/* Generated independent wire oracles; synthetic payloads only. */']
    data = sources()
    for i, source in enumerate(data):
        lines.append(f'static const rb_u8 encode_seed_{i}[2560] = {{')
        lines.extend(','.join(str(b) for b in source[n:n+32]) + ',' for n in range(0, 2560, 32))
        lines.append('};')
    lines += ['static const rb_u8 * const encode_seeds[] = {' +
              ','.join(f'encode_seed_{i}' for i in range(len(data))) + '};',
              'static const rb_u16 encode_sizes[] = {' + ','.join(str(len(v)//512) for v in data) + '};']
    patches, rows = [], []
    for case in cases():
        start = len(patches)
        for offset, width, value in case['edits']:
            patches += [(offset + i, byte) for i, byte in enumerate(value.to_bytes(width, 'little'))]
        rows.append((case['source'], start, len(patches)-start, case['file_sectors'],
                     case['expected'], case['decoded']))
    lines += ['static const rb_u16 encode_patches[][2] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in patches]
    lines += ['};', 'static const rb_u16 encode_vectors[][6] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in rows]
    return '\n'.join(lines + ['};']) + '\n'
