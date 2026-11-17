"""Independent wire bytes and callback/failure oracles for provisional output."""
from dataclasses import replace
import struct
import zlib

try:
    from .backup_container import Chunk, encode, inspect
    from .backup_encode_vectors import cases as encode_cases, sources as encode_sources
    from .backup_vectors import sources as base_sources
except ImportError:
    from backup_container import Chunk, encode, inspect
    from backup_encode_vectors import cases as encode_cases, sources as encode_sources
    from backup_vectors import sources as base_sources


def sources():
    result = base_sources()
    identity, entries = inspect(result[0])
    chunks = []
    for e in entries:
        start = e['file_sector'] * 512
        payload = bytearray(result[0][start:start + e['sectors'] * 512])
        if e['kind'] == 8:
            struct.pack_into('<I', payload, 508, zlib.crc32(payload[:508]))
        chunks.append(Chunk(e['kind'], e['index'], e['lba'], bytes(payload),
                            e['owner_start'], e['owner_sectors']))
    result += [encode(identity, chunks), encode_sources()[11]]
    identity, entries = inspect(result[0])
    chunks = [Chunk(e['kind'], e['index'], e['lba'],
                    result[0][e['file_sector']*512:(e['file_sector']+e['sectors'])*512],
                    e['owner_start'], e['owner_sectors']) for e in entries]
    result.append(encode(replace(identity, route=2, heads=256, sectors_per_track=63), chunks))
    return result


def cases():
    images = sources()
    result = []

    def add(name, seed=0, fault=0, at=0, status=0, detail=0, pos=0,
            reads=None, sinks=None, edits=(), size=0):
        sectors = len(images[seed]) // 512
        _, entries = inspect(images[seed])
        entry = next((e for e in entries
                      if e['file_sector'] <= pos < e['file_sector'] + e['sectors']), None)
        result.append(dict(name=name, seed=seed, fault=fault, at=at, status=status,
            detail=detail, pos=pos, kind=entry['kind'] if entry else 0,
            index=entry['index'] if entry else 0,
            reads=2*(sectors-5) if reads is None else reads,
            sinks=sectors if sinks is None else sinks, edits=edits, size=size))

    for seed, name in enumerate(('valid', 'over-64k', 'one-mib', '42-entries',
                                  'sealed-record', 'wide-fields', 'chs')):
        add(name, seed=seed)
    for c in encode_cases():
        if c['expected']:
            assert c['source'] == 0
            add('framing-' + c['name'], status=2, detail=c['expected'],
                reads=0, sinks=0, edits=c['edits'], size=c['file_sectors'])
    sectors = len(images[0]) // 512
    count = sectors - 5
    for phase in (0, 1):
        for pos in range(5, sectors):
            at = phase*count + pos-4
            add(f'read-{phase}-{pos}', fault=1, at=at, status=3, pos=pos,
                reads=at, sinks=pos if phase else 0)
        _, entries = inspect(images[0])
        for e in entries:
            pos = e['file_sector']
            end = pos + e['sectors']
            add(f'crc-{phase}-{e["kind"]}', fault=3, at=phase*count + pos-4,
                status=4, pos=pos, reads=phase*count + end-5,
                sinks=end if phase else 0)
    for pos in range(sectors):
        add(f'sink-{pos}', fault=2, at=pos, status=6, pos=pos,
            reads=count + max(0, pos-4), sinks=pos+1)
    # Even after every output sector was delivered, success must be withheld
    # for resealed first/second-pass differences hidden by whole-record CRCs.
    for phase in (0, 1):
        add(f'resealed-last-{phase}', seed=4, fault=4, at=(phase+1)*count, status=5)
    for fault, name in ((5, 'null-metadata'), (6, 'null-source'),
                        (7, 'null-sink'), (8, 'null-result')):
        add(name, fault=fault, status=1, reads=0, sinks=0)
    for phase in (0, 1):
        add(f'one-mib-last-read-{phase}', seed=2, fault=1, at=(phase+1)*2043,
            status=3, pos=2047, reads=(phase+1)*2043, sinks=2047 if phase else 0)
    add('one-mib-last-sink', seed=2, fault=2, at=2047, status=6, pos=2047,
        reads=4086, sinks=2048)
    # Consecutive calls exercise success-result revocation without poisoning.
    add('reuse-success')
    add('reuse-failure', fault=2, at=43, status=6, pos=43, reads=78, sinks=44)
    return result


def assertions():
    return 5 * len(cases())


def model_header():
    images = sources()
    lines = ['/* Generated independent Python wire oracles. */']
    for i, data in enumerate(images):
        lines.append(f'static const rb_u8 stream_seed_{i}[2560] = {{')
        lines.extend(','.join(str(b) for b in data[n:n+32]) + ',' for n in range(0, 2560, 32))
        lines.append('};')
    lines += ['static const rb_u8 * const stream_seeds[] = {' +
              ','.join(f'stream_seed_{i}' for i in range(len(images))) + '};',
              'static const rb_u16 stream_sizes[] = {' +
              ','.join(str(len(data)//512) for data in images) + '};']
    patches, rows = [], []
    for c in cases():
        start = len(patches)
        for offset, width, value in c['edits']:
            patches += [(offset+i, byte) for i, byte in enumerate(value.to_bytes(width, 'little'))]
        rows.append([c[k] for k in ('seed', 'fault', 'at', 'status', 'detail', 'pos',
                                    'kind', 'index', 'reads', 'sinks', 'size')] +
                    [start, len(patches)-start])
    lines += ['static const rb_u16 stream_patches[][2] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in patches]
    lines += ['};', 'typedef struct { rb_u16 seed, fault, at, status, detail, pos,',
              '    kind, index, reads, sinks, size, patch, patches; } rb_stream_case;',
              'static const rb_stream_case stream_cases[] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in rows]
    return '\n'.join(lines + ['};']) + '\n'
