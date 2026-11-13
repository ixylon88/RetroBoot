"""Synthetic container vectors, not snapshots or restorable disk backups."""
import struct
import zlib

try:
    from .backup_container import Chunk, Identity, encode
except ImportError:
    from backup_container import Chunk, Identity, encode


def pattern(sector):
    return bytes((sector * 17 + offset) & 255 for offset in range(512))


def fixture(boot_sectors=32, full_table=False):
    identity = Identity(1, 0x52425431, 0x12345678, 126, 128457, 300000,
                        bytes.fromhex('a6216f345cd2467790abc0137d8452e9'))
    descriptors = [(1, 0, 0, 1, 0, 0), (2, 0, 0, 1, 0, 0)]
    descriptors += [(3, i, 63 + i, 1, 0, 0) for i in range(16 if full_table else 1)]
    descriptors += [(4, 0, 126, boot_sectors, 126, 128457)]
    if full_table:
        descriptors += [(4, i, 150000 + i * 1000, 1, 150000 + i * 1000, 1000) for i in range(1, 20)]
    descriptors += [(kind, 0, 11603 + 400 * (kind - 5), 1, 126, 128457) for kind in range(5, 9)]
    chunks, position = [], 5
    for kind, index, lba, sectors, owner, length in descriptors:
        data = b''.join(pattern(i) for i in range(position, position + sectors))
        chunks.append(Chunk(kind, index, lba, data, owner, length))
        position += sectors
    return encode(identity, chunks)


def cases():
    """Expected status numbers are independent test expectations."""
    result = []

    def add(name, expected, edits=(), reseal=True, source=0, file_sectors=0, fail_sector=0xFFFF, corrupt_sector=0xFFFF):
        # Edits use (byte offset, width in bytes, little-endian value).
        result.append(dict(name=name, expected=expected, edits=edits, reseal=reseal,
                           source=source, file_sectors=file_sectors,
                           fail_sector=fail_sector, corrupt_sector=corrupt_sector))

    add('valid', 0)
    add('boot-area-over-64k', 0, source=1)
    add('maximum-file', 0, source=2)
    add('maximum-entry-count', 0, source=3)
    add('chs', 0, [(40, 2, 2), (42, 2, 256), (44, 2, 63)])
    add('edd-with-observed-geometry', 0, [(42, 2, 16), (44, 2, 63)])
    add('capacity-high-word', 0, [(48, 8, 1 << 32)])
    add('header-crc', 3, [(24, 1, 0)], reseal=False)
    add('table-crc', 3, [(512 + 16, 1, 0)], reseal=False)
    add('payload-crc', 3, corrupt_sector=10)
    add('last-payload-crc', 3, corrupt_sector=43)
    add('long-last-payload-crc', 3, source=1, corrupt_sector=141)
    add('maximum-last-payload-crc', 3, source=2, corrupt_sector=2047)
    for offset, width, value, name in [(0, 1, 0, 'magic'), (8, 2, 2, 'version'),
            (10, 2, 511, 'header-size'), (12, 4, 0, 'file-size'),
            (16, 4, 0, 'generation'), (20, 4, 0, 'disk-id'),
            (36, 2, 0, 'no-entries'), (36, 2, 43, 'too-many-entries'),
            (38, 2, 28, 'entry-stride'), (40, 2, 0, 'route'),
            (42, 2, 1, 'edd-geometry'), (46, 2, 1, 'reserved-word'), (100, 1, 1, 'reserved-header')]:
        add(name, 2, [(offset, width, value)])
    add('zero-media-id', 2, [(56, 8, 0), (64, 8, 0)])
    add('chs-no-geometry', 2, [(40, 2, 2)])
    add('chs-bad-heads', 2, [(40, 2, 2), (42, 2, 257), (44, 2, 63)])
    add('chs-bad-track', 2, [(40, 2, 2), (42, 2, 16), (44, 2, 64)])
    add('chs-unreachable-capacity', 4, [(40, 2, 2), (42, 2, 1), (44, 2, 1)])
    add('zero-capacity', 4, [(48, 8, 0)])
    add('admin-outside-capacity', 4, [(48, 8, 128000)])
    add('admin-overflow', 4, [(28, 4, 0xFFFFFFF0)])
    add('zero-admin', 4, [(28, 4, 0)])
    add('unused-descriptor', 2, [(512 + 8 * 32, 1, 1)])
    add('descriptor-flags', 2, [(512 + 28, 4, 1)])
    add('unknown-kind', 2, [(512, 2, 9)])
    add('duplicate-role', 5, [(544, 2, 1)])
    add('reversed-kind', 5, [(512, 2, 2), (544, 2, 1)])
    add('ebr-index-gap', 5, [(576 + 2, 2, 1)])
    add('boot-index-gap', 5, [(608 + 2, 2, 1)])
    add('zero-sectors', 4, [(512 + 8, 4, 0)])
    add('extent-overflow', 4, [(576 + 4, 4, 0xFFFFFFFF)])
    add('extent-outside-capacity', 4, [(576 + 4, 4, 300000)])
    add('payload-hole', 4, [(544 + 12, 4, 7)])
    add('payload-alias', 4, [(544 + 12, 4, 5)])
    add('payload-too-long', 4, [(608 + 8, 4, 2048)])
    add('mbr-wrong-lba', 4, [(512 + 4, 4, 1)])
    add('ebr-at-zero', 4, [(576 + 4, 4, 0)])
    add('ebr-with-owner', 4, [(576 + 20, 4, 1)])
    add('boot-interior-region', 0, [(608 + 4, 4, 127)])
    add('discontiguous-boot-regions', 0, [(576, 2, 4), (576 + 4, 4, 126),
        (576 + 20, 4, 126), (576 + 24, 4, 128457), (608 + 2, 2, 1), (608 + 4, 4, 128551)])
    add('boot-exceeds-owner', 4, [(608 + 24, 4, 31)])
    add('owner-overflow', 4, [(608 + 24, 4, 0xFFFFFFFF)])
    add('config-wrong-owner', 4, [(640 + 20, 4, 127)])
    add('config-outside-owner', 4, [(640 + 4, 4, 126 + 128457)])
    add('disk-overlap', 6, [(672 + 4, 4, 11603)])
    add('boot-ebr-overlap', 6, [(576 + 4, 4, 126)])
    # Drop the last descriptor, zero the newly unused slot, and shorten framing.
    add('missing-state-b', 7, [(36, 2, 7), (12, 4, 43 * 512)] + [(736 + i, 8, 0) for i in range(0, 32, 8)], file_sectors=43)
    add('trailing-sector', 4, [(12, 4, 45 * 512)], file_sectors=45)
    add('too-small-file', 2, file_sectors=4)
    add('too-large-file', 2, file_sectors=2049)
    for sector in (0, 1, 2, 3, 4, 5, 10, 43):
        add('read-error-' + str(sector), 1, fail_sector=sector)
    add('maximum-last-read-error', 1, source=2, fail_sector=2047)
    return result


def sources():
    return [fixture(), fixture(130), fixture(2036), fixture(1, True)]


def materialize(source, case):
    data = bytearray(source)
    for offset, width, value in case['edits']:
        data[offset:offset + width] = value.to_bytes(width, 'little')
    if case['reseal']:
        struct.pack_into('<I', data, 72, zlib.crc32(data[512:2560]))
        struct.pack_into('<I', data, 508, zlib.crc32(data[:508]))
    if case['file_sectors']:
        size = case['file_sectors'] * 512
        data = data[:size] + bytes(max(0, size - len(data)))
    if case['corrupt_sector'] != 0xFFFF:
        data[case['corrupt_sector'] * 512] ^= 1
    return bytes(data)


def model_header():
    """Small metadata seeds; native reader generates large payloads on demand."""
    vectors = sources()
    lines = ['/* Synthetic metadata only; generated by tools/backup_vectors.py. */']
    for i, data in enumerate(vectors):
        lines.append(f'static const rb_u8 seed_{i}[2560] = {{')
        lines.extend(','.join(str(b) for b in data[n:n+32]) + ',' for n in range(0, 2560, 32))
        lines.append('};')
    lines += ['static const rb_u8 * const seeds[] = {seed_0,seed_1,seed_2,seed_3};',
              'static const rb_u16 sizes[] = {' + ','.join(str(len(v)//512) for v in vectors) + '};']
    patches, rows = [], []
    for case in cases():
        start = len(patches)
        for offset, width, value in case['edits']:
            patches += [(offset + i, byte) for i, byte in enumerate(value.to_bytes(width, 'little'))]
        rows.append((case['source'], start, len(patches) - start, int(case['reseal']),
                     case['file_sectors'], case['fail_sector'], case['corrupt_sector'], case['expected']))
    lines += ['static const rb_u16 patches[][2] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in patches]
    lines += ['};', 'static const rb_u16 vectors[][8] = {']
    lines += ['{' + ','.join(map(str, row)) + '},' for row in rows]
    lines += ['};']
    return '\n'.join(lines) + '\n'
