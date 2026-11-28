"""Describe the owned installer layout and its allowed visibility changes."""
import json

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
