"""Owned F7 fixtures with independent, literal expected primary-table results."""
import struct
import zlib

try:
    from .config_records import CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID, encode as config, layout_crc
    from .state_records import encode as state
    from .state_fixtures import BASE_READS
    from .handoff_fixtures import mutate_handoff_fixture
except ImportError:
    from config_records import CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID, encode as config, layout_crc
    from state_records import encode as state
    from state_fixtures import BASE_READS
    from handoff_fixtures import mutate_handoff_fixture


def plan(status, changed, visible, active, types, flags):
    return dict(status=status, changed=changed, visible=visible, active=active, types=types, flags=flags)


def blocked(proof, detail=0, lba=0):
    return dict(status=2, proof=proof, detail=detail, error_lba=lba)


DOS = [plan(1, 2, 1, 1, [6, 0x16, 0x17, 5], [0x80, 0, 0, 0]),
       plan(1, 3, 2, 2, [0x16, 6, 0x17, 5], [0, 0x80, 0, 0])]
NT = [plan(0, 0, 3, 1, [6, 6, 0x17, 5], [0x80, 0, 0, 0]),
      plan(1, 7, 6, 2, [0x16, 6, 7, 5], [0, 0x80, 0, 0])]

# LBA lists distinguish the metadata loads from each fresh per-profile proof.
# A blocked record gate performs no target reads. NTFS stops before a VBR read.
VISIBILITY_CASES = {
    'visibility-dos': {'plans': DOS},
    'visibility-dos-matching': {'current_visible': 1, 'plans': [dict(DOS[0], status=0, changed=0), DOS[1]]},
    'visibility-hidden-target': {'current_visible': 2, 'current_active': 2,
                                 'plans': [dict(DOS[0], changed=3), dict(DOS[1], status=0, changed=0)]},
    'visibility-no-active': {'current_active': 0, 'plans': [dict(DOS[0], changed=3), DOS[1]]},
    'visibility-nt-group': {'plans': NT},
    'visibility-nt-hidden': {'current_visible': 0, 'current_active': 0,
                             'plans': [dict(NT[0], status=1, changed=3), dict(NT[1], changed=6)]},
    'visibility-nt-types': {'plans': [dict(NT[0], types=[6, 14, 0x1C, 5]), dict(NT[1], types=[0x16, 14, 12, 5])]},
    'visibility-stale-install': {'plans': [blocked(8), blocked(8)]},
    'visibility-pending': {'plans': [blocked(7, 5), blocked(7, 5)]},
    'visibility-degraded': {'copies': [4, 0], 'source': 1, 'plans': [blocked(3), blocked(3)]},
    'visibility-vbr-code': {'plans': [blocked(15, lba=131072), DOS[1]]},
    'visibility-vbr-io': {'fault_lba': 131072, 'fault_once': False,
                          'plans': [dict(blocked(14, 1, 131072), proof_reads=[0, 63, 131072, 131072, 131072]), DOS[1]]},
    'visibility-vbr-retry': {'fault_lba': 131072, 'fault_once': True,
                             'plans': [dict(DOS[0], proof_reads=[0, 63, 131072, 131072]), DOS[1]]},
    'visibility-admin-visible': {'record_status': 9, 'copies': [9, 9], 'source': 0xFFFF,
                                 'have_profiles': False, 'reads': [0, 63, 0, 63], 'plans': [blocked(1, 9, 126)]},
    'visibility-unknown-type': {'record_status': 8, 'copies': [8, 8], 'source': 0xFFFF,
                                'have_profiles': False, 'reads': [0, 0], 'plans': [blocked(1, 8)]},
    'visibility-ntfs-target': {'plans': [dict(NT[0], types=[6, 7, 0x17, 5]),
                                        dict(blocked(14, 16, 140000), proof_reads=[0, 63])]},
}


def mutate_visibility_fixture(size, source, name, vbr, language):
    if name not in VISIBILITY_CASES:
        raise ValueError('Unknown visibility fixture')

    size, source = mutate_handoff_fixture(size, source, 'retroboot-handoff', vbr)
    extents = dict(source)
    mbr = bytearray(extents[0])
    mbr[462:478] = bytes(16)
    mbr[466] = 6
    struct.pack_into('<II', mbr, 470, 140000, 5073)
    mbr[478:494] = bytes(16)
    mbr[482] = 0x17
    struct.pack_into('<II', mbr, 486, 150000, 5073)

    nt = name.startswith('visibility-nt')
    if name == 'visibility-dos-matching': mbr[466] = 0x16
    if name == 'visibility-hidden-target': mbr[446], mbr[450], mbr[462] = 0, 0x16, 0x80
    if name == 'visibility-no-active': mbr[446] = 0
    if name == 'visibility-nt-hidden': mbr[446], mbr[450], mbr[466] = 0, 0x16, 0x16
    if name == 'visibility-nt-types': mbr[466], mbr[482] = 14, 0x1C
    if name == 'visibility-ntfs-target': mbr[466] = 7
    extents[0] = bytes(mbr)

    # The second target is only header/CRC test data. It is never executed.
    targets = [vbr, bytearray(vbr)]
    struct.pack_into('<I', targets[1], 28, 140000)
    profiles, installations = [], []
    for i, start in enumerate((131072, 140000)):
        visible_type = mbr[450 + i * 16] & 0xEF
        target = dict(install_id=TEST_INSTALL_ID + i, start=start, sectors=5073,
                      slot=i + 1, type=visible_type, kind=2 if nt else 1)
        profiles.append(dict(target, id=i + 1, name=('ÄÖÜäöüß NT' if nt else 'ÄÖÜäöüß DOS')
                             if i == 0 else ('NT group' if nt else 'Second DOS'),
                             installed=2, approved=1, visible_mask=(3 if i == 0 else 6) if nt else 1 << i))
        installations.append(dict(target, phase=6, vbr_crc=zlib.crc32(targets[i])))
        extents[start * 512] = bytes(targets[i])

    if name == 'visibility-stale-install':
        for profile in profiles: profile['install_id'] += 10
    if name == 'visibility-pending': installations[1].update(phase=5, vbr_crc=0)

    binding = dict(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126, admin_sectors=128457)
    cfg = config(**binding, profiles=profiles, language=language, media_id=FIXTURE_MEDIA_ID)
    record = state(**binding, installations=installations)
    for cluster in CLUSTERS:
        extents[(411 + (cluster - 2) * 4) * 512] = cfg
    for i, cluster in enumerate(STATE_CLUSTERS):
        data = bytearray(record)
        if name == 'visibility-degraded' and i == 0: data[508] ^= 1
        extents[(411 + (cluster - 2) * 4) * 512] = bytes(data)

    if name == 'visibility-vbr-code':
        data = bytearray(vbr); data[509] ^= 1; extents[131072 * 512] = bytes(data)
    if name == 'visibility-admin-visible':
        data = bytearray(extents[63 * 512]); data[450] = 6; extents[63 * 512] = bytes(data)
    if name == 'visibility-unknown-type':
        data = bytearray(extents[0]); data[482] = 0x83; extents[0] = bytes(data)

    return size, extents
