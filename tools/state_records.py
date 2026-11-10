"""Encode synthetic installation-state records; no installer or runtime writer."""
import struct
import zlib
try:
    from .config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, model_record, seal, encode as encode_config
except ImportError:
    from config_records import FIXTURE_MEDIA_ID, TEST_INSTALL_ID, model_record, seal, encode as encode_config

PHASES = ('planned', 'prepared', 'media_handoff', 'setup_in_progress',
          'verification_required', 'ready', 'recovery_required')


def encode(*, disk_id, layout, admin_start, admin_sectors, generation=1,
           media_id=FIXTURE_MEDIA_ID, installations=()):
    if (not 1 <= generation <= 0xFFFFFFFF or not 1 <= disk_id <= 0xFFFFFFFF
            or not 0 <= layout <= 0xFFFFFFFF or not 0 < admin_start < admin_start + admin_sectors <= 0x100000000
            or not isinstance(media_id, bytes) or len(media_id) != 16 or not any(media_id)
            or len(installations) > 4): raise ValueError('Invalid state header')
    record = bytearray(512)
    struct.pack_into('<8sHHIIIIIIH', record, 0, b'RBSTATE\0', 1, 64, 512, generation,
                     disk_id, layout, admin_start, admin_sectors, len(installations))
    record[48:64] = media_id
    ids, slots = set(), set()
    for i, entry in enumerate(installations):
        iid, slot = entry['install_id'], entry['slot']
        phase, kind, ptype, crc = entry['phase'], entry.get('kind', 1), entry['type'], entry.get('vbr_crc', 0)
        if (not 1 <= iid <= 0xFFFFFFFFFFFFFFFF or iid in ids or slot in slots or not 1 <= slot <= 4
                or phase not in range(1, 8) or kind not in (1, 2) or ptype not in (6, 14, 11, 12, 7)
                or (kind == 1 and ptype == 7) or not 0 <= crc <= 0xFFFFFFFF or (phase != 6 and crc != 0)
                or not 0 < entry['start'] < entry['start'] + entry['sectors'] <= 0x100000000):
            raise ValueError('Invalid installation entry')
        ids.add(iid); slots.add(slot)
        struct.pack_into('<QIIBBBBI', record, 64 + i * 64, iid, entry['start'], entry['sectors'],
                         slot, ptype, kind, phase, crc)
    return seal(record)


def model_header(vbr):
    binding = dict(disk_id=0x52425431, layout=struct.unpack_from('<I', model_record(), 24)[0],
                   admin_start=126, admin_sectors=128457)
    entry = dict(install_id=TEST_INSTALL_ID, start=131072, sectors=5073, slot=1, type=6, kind=1)
    vectors = {'rb_state_vector': encode(**binding, installations=[dict(entry, phase=6, vbr_crc=zlib.crc32(vbr))]),
               'rb_bound_config_vector': encode_config(**binding, media_id=FIXTURE_MEDIA_ID,
                    profiles=[dict(entry, id=1, name='Test VBR', installed=2, approved=1)])}
    return '/* Generated independent record-format vectors. */\n' + '\n'.join(
        'static const rb_u8 ' + name + '[512] = {\n'
        + '\n'.join('    ' + ','.join(str(c) for c in data[i:i + 16]) + ',' for i in range(0, 512, 16))
        + '\n};' for name, data in vectors.items()) + '\n'
