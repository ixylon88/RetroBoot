"""Owned F9 fixtures; even matching records cannot authorize arbitrary code."""
import struct
import zlib

try:
    from .state_fixtures import STATE_CASES, BASE_READS, FILE_LBAS, mutate_state_fixture
    from .visibility_fixtures import VISIBILITY_CASES, mutate_visibility_fixture, plan, blocked
    from .config_records import seal
except ImportError:
    from state_fixtures import STATE_CASES, BASE_READS, FILE_LBAS, mutate_state_fixture
    from visibility_fixtures import VISIBILITY_CASES, mutate_visibility_fixture, plan, blocked
    from config_records import seal

MATCH = plan(0, 0, 1, 1, [6, 0, 0, 5], [0x80, 0, 0, 0])
PROFILE_CASES = {
    'profile-ready': {'base': 'state-match', 'selected': 1},
    'profile-nt': {'base': 'visibility-nt-group'},
    'profile-change': {'base': 'visibility-dos', 'status': 3},
    'profile-pending': {'base': 'state-phase-5', 'status': 2},
    'profile-degraded': {'base': 'state-crc-a', 'status': 2},
    'profile-stale': {'base': 'state-install-newer', 'status': 2},
    'profile-unapproved': {'base': 'state-approval', 'status': 2},
    'profile-vbr-crc': {'base': 'state-vbr-code', 'status': 2},
    'profile-vbr-substituted': {'base': 'state-match', 'status': 5},
    'profile-chs-entry': {'base': 'state-match', 'status': 4},
    'profile-other-target': {'base': 'visibility-hidden-target', 'selected': 1, 'status': 4},
    'profile-io': {'base': 'state-vbr-io', 'status': 2},
    'profile-retry': {'base': 'state-vbr-retry'},
    'profile-state-io': {'base': 'state-file-io', 'status': 2},
    'profile-legacy': {'base': 'state-legacy', 'status': 1},
    'profile-empty': {'base': 'retroboot-hdd', 'status': 1},
}


def expected_preview(spec):
    """Literal F7 expectations shared with the independent screen checker."""
    base = spec['base']
    if base in VISIBILITY_CASES: return dict(VISIBILITY_CASES[base])
    if base == 'retroboot-hdd':
        return dict(current_visible=0, have_profiles=False, plans=[blocked(6)])
    if base == 'retroboot-handoff':
        return dict(current_visible=1, plans=[MATCH])
    source = STATE_CASES[base]
    proof = source.get('proof', 0)
    expected = dict(blocked(proof, source.get('detail', 0), source.get('error_lba', 0))) if proof else dict(MATCH)
    if 'proof_reads' in source: expected['proof_reads'] = source['proof_reads']
    return dict(current_visible=1, plans=[expected, expected], reads=source.get('reads', BASE_READS),
                **{key: source[key] for key in ('fault_lba', 'fault_once') if key in source})


def mutate_profile_fixture(size, source, name, vbr, language):
    base = PROFILE_CASES[name]['base']
    if base in VISIBILITY_CASES:
        return mutate_visibility_fixture(size, source, base, vbr, language)
    if base == 'retroboot-hdd': return size, source
    size, extents = mutate_state_fixture(size, source, base, vbr, language)

    if name == 'profile-chs-entry':
        mbr = bytearray(extents[0]); mbr[447] ^= 1; extents[0] = bytes(mbr)
    if name == 'profile-vbr-substituted':
        sector = bytearray(vbr); sector[509] ^= 1; extents[131072 * 512] = bytes(sector)
        for lba in FILE_LBAS:
            record = bytearray(extents[lba * 512])
            struct.pack_into('<I', record, 84, zlib.crc32(sector))
            extents[lba * 512] = seal(record)
    return size, extents
