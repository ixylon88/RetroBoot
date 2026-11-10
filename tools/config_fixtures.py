"""Bounded read-only configuration campaigns on generated fixture media."""
import struct
try:
    from .config_records import CLUSTERS, encode, layout_crc, seal
    from .handoff_fixtures import mutate_handoff_fixture
except ImportError:
    from config_records import CLUSTERS, encode, layout_crc, seal
    from handoff_fixtures import mutate_handoff_fixture

FILE_LBAS = tuple(411 + (c - 2) * 4 for c in CLUSTERS)
BASE_READS = [0, 63, 126, 379, 380, 137, 263, FILE_LBAS[0], 138, 264, FILE_LBAS[1]]
CONFIG_CASES = {
    'config-newer': {}, 'config-older': {'source': 0}, 'config-equal': {'source': 0},
    'config-declared-ready': {},
    'config-conflict': {'status': 7},
    'config-crc-a': {'copies': [4, 0]}, 'config-crc-b': {'source': 0, 'copies': [0, 4]},
    'config-crc-both': {'status': 4, 'copies': [4, 4]},
    'config-version': {'status': 3, 'copies': [3, 3]},
    'config-foreign': {'status': 5, 'copies': [5, 5]},
    'config-layout': {'status': 5, 'copies': [5, 5]},
    'config-target': {'status': 6, 'copies': [6, 6]},
    'config-name': {'status': 6, 'copies': [6, 6]},
    'config-missing-a': {'copies': [1, 0], 'reads': BASE_READS[:5] + BASE_READS[8:]},
    'config-missing-both': {'status': 1, 'copies': [1, 1], 'reads': BASE_READS[:5]},
    **{name: {'status': 10, 'copies': [10, 10], 'reads': BASE_READS[:5]} for name in
       ('config-duplicate', 'config-alias', 'config-size', 'config-directory', 'config-cluster-range')},
    'config-fat-mismatch': {'status': 11, 'copies': [11, 11], 'reads': BASE_READS[:7]},
    'config-fat-long': {'status': 11, 'copies': [11, 11], 'reads': BASE_READS[:6]},
    'config-fat-eoc': {},
    'config-root-full': {'reads': BASE_READS[:3] + list(range(379, 411)) + BASE_READS[5:]},
    'config-fat-io': {'status': 2, 'copies': [2, 2], 'fault_lba': 137, 'fault_once': False,
                      'reads': BASE_READS[:5] + [137] * 3},
    'config-file-io': {'copies': [2, 0], 'fault_lba': FILE_LBAS[0], 'fault_once': False,
                       'reads': BASE_READS[:7] + [FILE_LBAS[0]] * 3 + BASE_READS[8:]},
    'config-file-retry': {'fault_lba': FILE_LBAS[0], 'fault_once': True,
                          'reads': BASE_READS[:7] + [FILE_LBAS[0]] * 2 + BASE_READS[8:]},
    'config-ebr': {'status': 8, 'copies': [8, 8], 'reads': [0, 63]},
    'config-admin-type': {'status': 9, 'copies': [9, 9], 'reads': [0, 63]},
}


def profiles(language):
    return [dict(id=index + 1, name=(('Profile ' if language == 'en' else 'Profil ') + str(index + 1))
                 if index else 'ÄÖÜäöüß test', slot=1, type=6, start=131072, sectors=5073,
                 kind=1 if index % 2 == 0 else 2) for index in range(8)]


def mutate_config_fixture(size, source, name, vbr, language):
    if name not in CONFIG_CASES: raise ValueError('Unknown configuration fixture')
    size, source = mutate_handoff_fixture(size, source, 'retroboot-handoff', vbr)
    extents = dict(source)
    records = [bytearray(encode(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126,
               admin_sectors=128457, generation=i + 1, profiles=profiles(language), language=language)) for i in range(2)]
    if name == 'config-declared-ready':
        for record in records:
            struct.pack_into('<HI', record, 38, 1, 1)
            for offset in range(64, 448, 48): record[offset + 15:offset + 17] = b'\x02\x01'
    if name == 'config-older': records.reverse()
    if name in ('config-equal', 'config-conflict'): records[1] = bytearray(records[0])
    if name == 'config-conflict': records[1][44] ^= 1
    changes = {'config-version': 8, 'config-foreign': 20, 'config-layout': 24,
               'config-target': 68, 'config-name': 84}
    if name in changes:
        for record in records: record[changes[name]] = 0 if name == 'config-name' else record[changes[name]] ^ 2
    records = [bytearray(seal(record)) for record in records]
    if name in ('config-crc-a', 'config-crc-both'): records[0][508] ^= 1
    if name in ('config-crc-b', 'config-crc-both'): records[1][508] ^= 1
    for lba, record in zip(FILE_LBAS, records): extents[lba * 512] = bytes(record)
    root = bytearray(extents[379 * 512])
    if name in ('config-missing-a', 'config-missing-both'): root[672] = 0xE5
    if name == 'config-missing-both': root[704] = 0xE5
    if name == 'config-duplicate': root[736:768] = root[672:704]
    if name == 'config-alias': struct.pack_into('<H', root, 704 + 26, CLUSTERS[0])
    if name == 'config-size': struct.pack_into('<I', root, 672 + 28, 511)
    if name == 'config-directory': root[672 + 11] = 0x10
    if name == 'config-cluster-range': struct.pack_into('<H', root, 672 + 26, 0xFFFF)
    if name == 'config-root-full':
        for offset in range(736, len(root), 32): root[offset] = 0xE5
    extents[379 * 512] = bytes(root)
    if name in ('config-fat-mismatch', 'config-fat-long', 'config-fat-eoc'):
        for copy in range(2):
            table = bytearray(extents[(127 + copy * 126) * 512])
            if name == 'config-fat-eoc' or (name == 'config-fat-mismatch' and copy == 1):
                struct.pack_into('<H', table, CLUSTERS[0] * 2, 0xFFF8)
            if name == 'config-fat-long': struct.pack_into('<H', table, CLUSTERS[0] * 2, 3000)
            extents[(127 + copy * 126) * 512] = bytes(table)
    if name in ('config-ebr', 'config-admin-type'):
        ebr = bytearray(extents[63 * 512]); ebr[510 if name == 'config-ebr' else 450] = 6
        extents[63 * 512] = bytes(ebr)
    return size, extents
