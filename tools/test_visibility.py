"""Check F7 primary-table previews, failure gates and read-only execution."""
import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_hdd import ROOT, prepare_output, sha256
    from .config_fixtures import FILE_LBAS as CONFIG_LBAS
    from .visibility_fixtures import BASE_READS, blocked, plan
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, screen_rows, wait_marker
    from .test_state import PROOF_KEYS
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from config_fixtures import FILE_LBAS as CONFIG_LBAS
    from visibility_fixtures import BASE_READS, blocked, plan
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from test_state import PROOF_KEYS
    from ui_text import LANGUAGES, checked_catalog, output_name

VIS_KEYS = ('VIS_MATCH', 'VIS_CHANGE', 'VIS_BLOCKED', 'VIS_ADMIN')


def check_visibility_screen(data, strings, spec, expected, mbr, config, index, count):
    rows = screen_rows(data)

    def at(row, column, value):
        if rows[row][column:column + len(value)] != value:
            raise ValueError(f'Wrong visibility VGA text at {row},{column}: {value!r}; {rows[row]!r}')

    for row, key in ((5, 'VIS_TITLE'), (6, 'VIS_SCOPE'), (9, 'VIS_CODES'),
                     (19, 'VIS_HELP'), (21, 'KEY_HELP'), (22, 'FUNCTION_HELP')):
        at(row, 4, strings[key])
    at(2, 65, strings['READ_ONLY'])
    at(8, 4, strings[VIS_KEYS[expected['status']]])
    at(9, 30, f'0x{expected["status"]:04X} / 0x{expected.get("proof", 0):04X} / 0x{expected.get("detail", 0):04X}')

    if count:
        entry = config[64 + index * 52:116 + index * 52]
        at(7, 4, entry[20:20 + entry[18]].decode('cp437'))
        at(18, 4, strings['PAGE']); at(18, 10, str(index + 1)); at(18, 12, '/'); at(18, 14, str(count))
    elif any(rows[r][4:78].strip() for r in (7, 18)):
        raise ValueError('Empty visibility view displays a stale profile')

    if expected['status'] <= 1:
        at(10, 4, strings['VIS_COLUMNS'])
        for i in range(4):
            at(11 + i, 4, f'P{i + 1}')
            at(11 + i, 17, f'0x{mbr[450 + 16 * i]:02X} /  0x{mbr[446 + 16 * i]:02X}')
            at(11 + i, 45, f'0x{expected["types"][i]:02X} /  0x{expected["flags"][i]:02X}')
        for row, key, current, wanted in (
                (15, 'VIS_VISIBLE', spec.get('current_visible', 3), expected['visible']),
                (16, 'VIS_ACTIVE', spec.get('current_active', 1), expected['active'])):
            at(row, 4, strings[key]); at(row, 30, f'0x{current:02X} /  0x{wanted:02X}')
        at(17, 4, strings['VIS_CHANGED']); at(17, 30, f'0x{expected["changed"]:02X}')
    else:
        if expected['status'] == 2: at(11, 4, strings[PROOF_KEYS[expected['proof']]])
        at(13, 4, strings['LBA_HEX']); at(13, 23, f'0x{expected.get("error_lba", 0):08X}')
        # Failure text uses rows 11 and 13; every other former plan row is empty.
        if any(rows[r][4:78].strip() for r in (10, 12, 14, 15, 16, 17)):
            raise ValueError('Blocked visibility view displays a stale plan')
        reason = strings[PROOF_KEYS[expected['proof']]] if expected['status'] == 2 else ''
        if rows[13][33:78].strip() or rows[11][4 + len(reason):78].strip():
            raise ValueError('Blocked visibility view retains stale table fields')

    if data[(8 * 80 + 4) * 2 + 1] != (0x1E if expected['status'] else 0x1A):
        raise ValueError('Wrong visibility status color')
    for row in range(2, 23):
        if data[(row * 80 + 1) * 2] != 0xB3 or data[(row * 80 + 78) * 2] != 0xB3:
            raise ValueError('Visibility text overwrote its frame')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable: raise ValueError('qemu-system-i386 not found')
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    if not bios.is_file() or not bios.with_name('vgabios-stdvga.bin').is_file(): raise ValueError('Missing BIOS ROMs')
    source = ROOT / 'build' / output_name('hdd', args.language)
    output = ROOT / 'build' / output_name('visibility', args.language)
    prepare_output(output)
    result_file = output / 'visibility-results.json'; result_file.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    strings = checked_catalog(manifest, args.language)
    for name, info in manifest['artifacts'].items():
        if name.startswith(('stage2', 'int13-')) and sha256(source / name) != info['sha256']:
            raise ValueError('Changed visibility test component: ' + name)
    events = output / 'ide-events.txt'
    events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n', encoding='ascii')
    command = [str(qemu), '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
               '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'c', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot',
               '-global', 'isa-debugcon.iobase=0xe9', '-qmp', 'stdio']
    fixtures = {**manifest['visibility_cases'],
                'retroboot-hdd': {'have_profiles': False, 'plans': [blocked(6)]},
                'retroboot-handoff': {'current_visible': 1, 'plans': [plan(0, 0, 1, 1, [6, 0, 0, 5], [0x80, 0, 0, 0])]}}
    scenarios = [(fixture, spec, mode, rom) for fixture, spec in fixtures.items()
                 for mode, rom in (('EDD', 0), ('CHS', 1))]
    scenarios.append(('visibility-dos', fixtures['visibility-dos'], 'EDD', None))
    results, pairs = [], {}

    for fixture, spec, mode, rom in scenarios:
        name = fixture + '-' + (mode.lower() if rom is not None else 'bare')
        status, copies = spec.get('record_status', 0), spec.get('copies', [0, 0])
        chosen = spec.get('source', 0)
        variant = 'handoff' if fixture == 'retroboot-handoff' else 'normal'
        payload = (source / ('stage2' + ('-handoff' if variant == 'handoff' else '') + '.bin')).read_bytes()
        memory = manifest['memory'][variant]
        image = source / (fixture + '.img'); image_hash = sha256(image)
        if image_hash != manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed visibility fixture')
        with image.open('rb') as stream:
            mbr = stream.read(512)
            stream.seek(CONFIG_LBAS[0] * 512); config = stream.read(512)
        count = struct.unpack_from('<H', config, 36)[0] if spec.get('have_profiles', True) else 0
        log, trace, error = (output / (name + suffix) for suffix in ('.log', '.trace', '-stderr.log'))
        log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
        drive = str(image)
        if 'fault_lba' in spec:
            conf = output / (name + '.conf')
            conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                            f'sector = "{spec["fault_lba"]}"\nonce = "' + ('on' if spec['fault_once'] else 'off') + '"\n', encoding='ascii')
            drive = f'blkdebug:{conf}:{image}'
        invocation = command + ['-drive', f'file={drive.replace(",", ",,")},format=raw,if=ide,snapshot=on,rerror=report',
                                '-debugcon', 'file:' + str(log), '-trace',
                                f'events={str(events).replace(",", ",,")},file={str(trace).replace(",", ",,")}']
        if rom is not None: invocation += ['-option-rom', str(source / f'int13-{rom}.rom')]
        actions = [(None, 0), ('f7', 8), ('left', 8), ('right', 8), ('ret', 8), ('f4', 8),
                   ('esc', 0), ('f8', 3), ('f7', 8), ('esc', 0)]
        screens, expected_reads, expected_markers, before_low = [], [], [], None
        selected, index, attempts, proofs = 0, 0, 0, 0
        with error.open('w', encoding='utf-8') as errors, subprocess.Popen(
                invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process); wait_marker(process, log, 'RB MENU READY')
                for serial, (key, view) in enumerate(actions):
                    if key == 'f8': selected = 2
                    if key == 'f7':
                        expected_reads += spec.get('reads', BASE_READS); attempts += 1; index = 0
                    elif key in ('left', 'right') and count:
                        index = (index + (1 if key == 'right' else -1)) % count
                    expected = spec['plans'][index]
                    if key == 'f7' or (key in ('left', 'right') and count):
                        if expected.get('proof', 0) in (0, 14, 15):
                            target = struct.unpack_from('<I', config, 68 + index * 52)[0]
                            reads = expected.get('proof_reads', [0, 63, target])
                            if proofs and spec.get('fault_once'): reads = [0, 63, target]
                            expected_reads += reads
                        proofs += 1
                        expected_markers.append(f'RB VISIBILITY status={expected["status"]:04X} '
                            f'proof={expected.get("proof", 0):04X} detail={expected.get("detail", 0):04X} '
                            f'index={index:04X} changed={expected.get("changed", 0):04X}')
                    if key:
                        qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
                        time.sleep(0.05)
                        wait_marker(process, log, f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                    qmp.call('stop')
                    paths = {kind: output / f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga', 'ram', 'low')}
                    for kind, address, length in (('vga', 0xB8000, 4000), ('ram', 0x10000, 0x10000), ('low', 0, 0x8000)):
                        qmp.call('pmemsave', {'val': address, 'size': length, 'filename': str(paths[kind])})
                    ram, low, vga = (paths[k].read_bytes() for k in ('ram', 'low', 'vga'))
                    check_runtime_memory(ram, payload, memory, mode)
                    if before_low is None: before_low = low
                    if low[0x7C00:0x7E00] != before_low[0x7C00:0x7E00] or low[0x800:0x840] != before_low[0x800:0x840]:
                        raise ValueError('Visibility preview staged a target or executed its VBR')
                    boot = ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot'] + 12]
                    rows = check_visibility_screen(vga, strings, spec, expected, mbr, config, index, count) if view == 8 else check_screen(
                        vga, view, selected, mode, mbr, boot, strings)
                    (output / f'{name}-{serial:02d}.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
                    if serial == 1: qmp.call('screendump', {'filename': str(output / f'{name}.png'), 'format': 'png'})
                    screens.append({'key': key, 'view': view, 'entry': index, 'status': expected['status'], 'vga_sha256': sha256(paths['vga'])})
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5) != 0: raise ValueError('QEMU did not exit cleanly')
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
        text = log.read_text(encoding='utf-8'); check_c_status(text, mode)
        marker = f'RB VISIBILITY records={status:04X} copies={copies[0]:04X}{copies[1]:04X} source={chosen:04X}'
        if re.findall(r'RB VISIBILITY status=[^\r\n]+', text) != expected_markers:
            raise ValueError('Incorrect visibility proof/plan diagnostics: ' + name)
        if text.count(marker) != attempts or text.count(f'RB UI {args.language} CP437') != 1:
            raise ValueError('Missing visibility record diagnostics: ' + name)
        if 'RB HANDOFF BEGIN' in text or 'RB HANDOFF PASS' in text: raise ValueError('Visibility preview started a target')
        trace_text = trace.read_text(encoding='utf-8'); check_trace(trace_text); lbas = read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text, mode)
            boot_calls = check_bios_route(text.split('RB MENU READY', 1)[0], mode)
            boot_reads = 1 + boot_calls.count('42' if mode == 'EDD' else '02')
            if lbas[boot_reads:] != expected_reads:
                raise ValueError(f'Unexpected visibility reads: {name}: {lbas[boot_reads:]} != {expected_reads}')
            pairs.setdefault(fixture, {})[mode] = lbas
        elif lbas != pairs[fixture]['EDD']: raise ValueError('Uninstrumented visibility reads differ')
        if sha256(image) != image_hash: raise ValueError('Visibility preview changed its image')
        results.append({'name': name, 'mode': mode, 'status': status, 'copies': copies, 'source': chosen,
                        'proofs': proofs, 'screens': screens, 'read_lbas': lbas, 'post_menu_reads': expected_reads,
                        'image_unchanged': True, 'block_writes': 0})
        print(f'{name}: {len(screens)} states, current/intended primary table checked; no writes', flush=True)

    if any(p['EDD'] != p['CHS'] for p in pairs.values()): raise ValueError('Visibility EDD/CHS reads differ')
    result_file.write_text(json.dumps({'ui': manifest['ui'], 'qemu_version': subprocess.check_output(
        [str(qemu), '--version'], text=True).splitlines()[0], 'qemu_sha256': sha256(qemu),
        'bios_sha256': sha256(bios), 'vga_bios_sha256': sha256(bios.with_name('vgabios-stdvga.bin')),
        'machine': 'pc-i440fx-8.2', 'cpu': '486', 'ram_mib': 16, 'cases': results}, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'Visibility test: {error}', file=sys.stderr); sys.exit(1)
