"""Synthetic independent record pairs for read-only F6 diagnosis."""
import struct
import zlib
try:
    from .config_records import CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID, encode as config, layout_crc, seal
    from .state_records import encode as state
    from .config_fixtures import BASE_READS as CONFIG_READS
    from .handoff_fixtures import mutate_handoff_fixture
except ImportError:
    from config_records import CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID, encode as config, layout_crc, seal
    from state_records import encode as state
    from config_fixtures import BASE_READS as CONFIG_READS
    from handoff_fixtures import mutate_handoff_fixture

FILE_LBAS = tuple(411 + (c - 2) * 4 for c in STATE_CLUSTERS)
STATE_READS = [0, 63, 126, 379, 380, 138, 264, FILE_LBAS[0], 139, 265, FILE_LBAS[1]]
PROOF_READS = [0, 63, 131072]
BASE_READS = CONFIG_READS + STATE_READS
STATE_CASES = {
    'state-match': {}, 'state-rename': {}, 'state-legacy': {'proof': 4},
    'state-crc-a': {'proof': 3, 'copies': [4, 0]},
    'state-crc-b': {'proof': 3, 'source': 0, 'copies': [0, 4]},
    'state-crc-both': {'proof': 2, 'status': 4, 'copies': [4, 4], 'detail': 4, 'error_lba': FILE_LBAS[0]},
    'state-version': {'proof': 2, 'status': 3, 'copies': [3, 3], 'detail': 3, 'error_lba': FILE_LBAS[0]},
    'state-conflict': {'proof': 2, 'status': 7, 'detail': 7},
    'state-media-newer': {'proof': 5}, 'state-install-newer': {'proof': 8},
    'state-planned': {'proof': 10, 'detail': 1},
    **{'state-phase-' + str(p): {'proof': 7, 'detail': p} for p in (2, 3, 4, 5, 7)},
    'state-other-pending': {'proof': 7, 'detail': 5},
    'state-approval': {'proof': 11}, 'state-target-kind': {'proof': 9},
    'state-vbr-code': {'proof': 15, 'error_lba': 131072},
    'state-vbr-bpb': {'proof': 14, 'detail': 10, 'error_lba': 131072},
    'state-missing-a': {'proof': 3, 'copies': [1, 0], 'reads': CONFIG_READS + STATE_READS[:5] + STATE_READS[8:]},
    'state-missing-both': {'proof': 2, 'status': 1, 'detail': 1, 'copies': [1, 1], 'reads': CONFIG_READS + STATE_READS[:5]},
    'state-alias': {'proof': 1, 'config_copies': [10, 10], 'status': 10, 'copies': [10, 10],
                    'detail': 10, 'error_lba': 379, 'reads': CONFIG_READS[:5] + STATE_READS[:5]},
    'state-duplicate': {'proof': 1, 'config_copies': [10, 10], 'status': 10, 'copies': [10, 10],
                        'detail': 10, 'error_lba': 380, 'reads': CONFIG_READS[:5] + STATE_READS[:5]},
    'state-fat': {'proof': 2, 'status': 11, 'copies': [11, 11], 'detail': 11,
                  'error_lba': 264, 'reads': CONFIG_READS + STATE_READS[:7]},
    'state-file-io': {'proof': 3, 'copies': [2, 0], 'error_lba': FILE_LBAS[0],
                      'fault_lba': FILE_LBAS[0], 'fault_once': False,
                      'reads': CONFIG_READS + STATE_READS[:7] + [FILE_LBAS[0]] * 3 + STATE_READS[8:]},
    'state-file-retry': {'fault_lba': FILE_LBAS[0], 'fault_once': True,
                         'reads': CONFIG_READS + STATE_READS[:7] + [FILE_LBAS[0]] * 2 + STATE_READS[8:]},
    'state-vbr-io': {'proof': 14, 'detail': 1, 'error_lba': 131072,
                     'fault_lba': 131072, 'fault_once': False, 'proof_reads': [0, 63] + [131072] * 3},
    'state-vbr-retry': {'fault_lba': 131072, 'fault_once': True, 'proof_reads': [0, 63] + [131072] * 2},
}


def mutate_state_fixture(size, source, name, vbr, language):
    if name not in STATE_CASES: raise ValueError('Unknown state fixture')
    size, source = mutate_handoff_fixture(size, source, 'retroboot-handoff', vbr)
    extents = dict(source)
    if name == 'state-other-pending':
        mbr = bytearray(extents[0]); mbr[466] = 6
        struct.pack_into('<II', mbr, 470, 140000, 5073); extents[0] = bytes(mbr)
    binding = dict(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126, admin_sectors=128457)
    entry = dict(install_id=TEST_INSTALL_ID, slot=1, type=6, start=131072, sectors=5073, kind=1)
    profiles = [dict(entry, id=i + 1, name='ÄÖÜäöüß test' if i == 0 else 'Renamed target',
                     installed=2, approved=0 if name == 'state-approval' else 1) for i in range(2)]
    if name == 'state-rename':
        for p in profiles: p['id'] += 40
    if name == 'state-target-kind':
        for p in profiles: p['kind'] = 2
    cfg = config(**binding, profiles=profiles, language=language,
                 generation=9 if name == 'state-rename' else 1,
                 media_id=None if name == 'state-legacy' else FIXTURE_MEDIA_ID)
    entries = [dict(entry, phase=6, vbr_crc=zlib.crc32(vbr))]
    if name == 'state-planned' or name.startswith('state-phase-'):
        entries[0].update(phase=1 if name == 'state-planned' else int(name[-1]), vbr_crc=0)
    if name == 'state-other-pending': entries.append(dict(entry, install_id=2, slot=2, start=140000, phase=5))
    records = [bytearray(state(**binding, generation=i + 1, installations=entries)) for i in range(2)]
    if name == 'state-conflict': records[1][:] = records[0]; records[1][48] ^= 1
    if name == 'state-media-newer': records[1][48] ^= 1
    if name == 'state-install-newer': records[1][64] ^= 2
    if name == 'state-version':
        for r in records: r[8] = 2
    records = [bytearray(seal(r)) for r in records]
    if name in ('state-crc-a', 'state-crc-both'): records[0][508] ^= 1
    if name in ('state-crc-b', 'state-crc-both'): records[1][508] ^= 1
    for cluster in CLUSTERS: extents[(411 + (cluster - 2) * 4) * 512] = cfg
    for lba, record in zip(FILE_LBAS, records): extents[lba * 512] = bytes(record)
    root = bytearray(extents[379 * 512])
    if name in ('state-missing-a', 'state-missing-both'): root[736] = 0xE5
    if name == 'state-missing-both': root[768] = 0xE5
    if name == 'state-alias': struct.pack_into('<H', root, 736 + 26, CLUSTERS[0])
    if name == 'state-duplicate': root[800:832] = root[736:768]; root[832] = 0
    extents[379 * 512] = bytes(root)
    if name == 'state-fat':
        table = bytearray(extents[253 * 512]); struct.pack_into('<H', table, STATE_CLUSTERS[0] * 2, 0xFFF8)
        extents[253 * 512] = bytes(table)
    if name in ('state-vbr-code', 'state-vbr-bpb'):
        target = bytearray(vbr); target[509 if name == 'state-vbr-code' else 28] ^= 1
        extents[131072 * 512] = bytes(target)
    return size, extents
