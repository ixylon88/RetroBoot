"""Metadata-only defects for the closed eight-file management-volume audit."""
import struct

# Expected diagnostic fields are literal, independent of the native auditor.
AUDIT_CASES = {
    'audit-mirror': dict(status=7, lba=268),
    'audit-padding': dict(status=7, lba=378),
    'audit-orphan': dict(status=9, detail=0xFFFF, cluster=4000, lba=142),
    'audit-cross-copy': dict(status=6, detail=3, file=6, cluster=2800, lba=137),
    'audit-cross-loader': dict(status=6, detail=2, file=3, cluster=20, lba=127),
    'audit-chain': dict(status=5, detail=4000, file=3, cluster=2800, lba=137),
    'audit-free': dict(status=5, file=3, cluster=2800, lba=137),
    'audit-missing': dict(status=4, detail=3, file=6, lba=379),
    'audit-extra': dict(status=4, detail=1, cluster=4000, lba=380),
    'audit-directory': dict(status=4, detail=1, cluster=4000, lba=380),
    'audit-lfn': dict(status=4, detail=1, lba=380),
    'audit-size': dict(status=4, detail=5, file=6, cluster=3100, lba=380),
    'audit-header': dict(status=8, file=1, cluster=2, lba=127),
    'audit-bootstrap': dict(status=11, file=1, cluster=4000, lba=126),
    'audit-io': dict(status=3, lba=378, fault_lba=378, fault_once=False),
    'audit-retry': dict(status=0, fault_lba=378, fault_once=True),
}


def mutate_audit_fixture(size, source, name):
    """Keep the executable payload and its loader path intact."""
    if name not in AUDIT_CASES: raise ValueError('Unknown audit fixture')
    extents = dict(source)
    tables = [bytearray(source[lba * 512]) for lba in (127, 253)]
    root = bytearray(source[379 * 512])

    def fat(cluster, value, copies=(0, 1)):
        for copy in copies: struct.pack_into('<H', tables[copy], cluster * 2, value)

    if name == 'audit-mirror': fat(4000, 0xFFFF, (1,))
    elif name == 'audit-padding': tables[1][-1] ^= 1
    elif name == 'audit-orphan': fat(4000, 0xFFFF)
    elif name == 'audit-cross-copy': struct.pack_into('<H', root, 24 * 32 + 26, 2800)
    elif name == 'audit-cross-loader': struct.pack_into('<H', root, 21 * 32 + 26, 20)
    elif name == 'audit-chain': fat(2800, 4000)
    elif name == 'audit-free': fat(2800, 0)
    elif name == 'audit-missing': root[24 * 32] = 0xE5
    elif name in ('audit-extra', 'audit-directory', 'audit-lfn'):
        entry = bytearray(32); entry[:11] = b'FOREIGN BIN'
        entry[11] = {'audit-extra': 0x20, 'audit-directory': 0x10, 'audit-lfn': 0x0F}[name]
        if name != 'audit-lfn':
            struct.pack_into('<HI', entry, 26, 4000, 512 if name == 'audit-extra' else 0)
            fat(4000, 0xFFFF)
        root[25 * 32:26 * 32] = entry
    elif name == 'audit-size': struct.pack_into('<I', root, 24 * 32 + 28, 513)
    elif name == 'audit-header': fat(1, 0x7FFF)
    elif name == 'audit-bootstrap':
        struct.pack_into('<H', root, 26, 4000)
        fat(2, 0); fat(4000, 0xFFFF)
    for lba, table in zip((127, 253), tables): extents[lba * 512] = bytes(table)
    extents[379 * 512] = bytes(root)
    return size, extents
