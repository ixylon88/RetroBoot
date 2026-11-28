"""Describe the owned installer layout and its allowed visibility changes."""
import json
import struct

try:
    from .build_hdd import ROOT, SECTOR, layout
except ImportError:
    from build_hdd import ROOT, SECTOR, layout

DISK_ID = 0x52424931
DISK_UUID = '52429901-d413-4b6c-a399-000011111111'


def reference_header():
    plan = json.loads((ROOT / 'profiles/rb-8g-chs255.json').read_bytes())
    size, _, extents = layout(True)
    roles = {'system': 'SYSTEM', 'extended': 'KEEP', 'retroboot': 'ADMIN', 'shared': 'SHARED'}
    tables = [(0, [roles[p['role']] for p in plan['primary']])]
    tables.extend((p['ebr_lba'], [roles[p['role']], 'KEEP', 'KEEP', 'KEEP']) for p in plan['logical'])
    end = max(p['start_lba'] + p['sectors'] for p in plan['primary'])
    rows = []
    for lba, group in tables:
        entries = extents[lba * SECTOR][446:510]
        rows.append('    {' + f'{lba}UL, ' + '{' + ', '.join(group) + '}, {' +
                    ','.join(f'0x{b:02x}' for b in entries) + '}}')
    return (f'#define INSTALL_DISK_ID 0x{DISK_ID:08X}UL\n'
            f'#define INSTALL_CAPACITY {size // SECTOR}UL\n#define INSTALL_END {end}UL\n'
            f'#define INSTALL_HEADS {plan["geometry"]["heads"]}U\n'
            f'#define INSTALL_SPT {plan["geometry"]["sectors_per_track"]}U\n'
            'static const install_table reference[] = {\n' + ',\n'.join(rows) + '\n};\n')


def initial_mbr(sector):
    """Start with P1 active and visible and the other two system slots hidden."""
    mbr = bytearray(sector)
    struct.pack_into('<I', mbr, 440, DISK_ID)
    mbr[446], mbr[466], mbr[482] = 0x80, 0x1b, 0x1b
    return bytes(mbr)


def visibility_tables():
    plan = json.loads((ROOT / 'profiles/rb-8g-chs255.json').read_bytes())
    _, _, raw = layout(True)
    tables = {}
    for index, lba in enumerate([0, *(v['ebr_lba'] for v in plan['logical'])]):
        table = bytearray(initial_mbr(raw[0]) if index == 0 else raw[lba * SECTOR])
        if index == 0:
            table[:4] = b'\xcd\x18\xeb\xfe'  # No installed OS; ask BIOS for another boot device.
        table[400:408] = b'RBVIEW1' + bytes([48 + index])
        tables[lba] = bytes(table)
    return tables


def write_visibility_reference(output):
    plan = json.loads((ROOT / 'profiles/rb-8g-chs255.json').read_bytes())
    tables = visibility_tables()
    # Hide the shared volumes before activating the new primary system slot.
    order = [p['ebr_lba'] for p in plan['logical'] if p['role'] == 'shared'] + [0]
    indices = [list(tables).index(lba) for lba in order]
    rows = [','.join(str(b) for b in sector) for sector in tables.values()]
    (output / 'install_approval.h').write_text(
        'static const rb_install_tables approved = {\n{' + '},\n{'.join(rows) + '}\n};\n' +
        'static const rb_u16 write_order[] = {' + ','.join(map(str, indices)) + '};\n', encoding='ascii')
    (output / 'install_view_lbas.inc').write_text(
        'dd ' + ','.join(map(str, order)) + '\n', encoding='ascii')
