"""Exercise actual FAT file reads and A/B selection through the BIOS F5 page."""
import argparse
import json
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_hdd import ROOT, prepare_output, sha256
    from .config_fixtures import BASE_READS, FILE_LBAS
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, screen_rows, wait_marker
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from config_fixtures import BASE_READS, FILE_LBAS
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from ui_text import LANGUAGES, checked_catalog, output_name

STATUS_KEYS = ('CONFIG_OK', 'CONFIG_MISSING', 'ERROR_IO', 'CONFIG_FORMAT', 'CONFIG_CRC',
               'CONFIG_IDENTITY', 'CONFIG_PROFILE', 'CONFIG_CONFLICT', 'SCAN_FAILED',
               'CONFIG_ADMIN', 'CONFIG_DIRECTORY', 'CONFIG_FAT')


def expected_location(fixture, spec):
    locations = {'config-duplicate': (380, 0), 'config-alias': (379, 2),
                 'config-size': (380, 0), 'config-directory': (380, 0),
                 'config-cluster-range': (380, 0), 'config-fat-mismatch': (263, 0),
                 'config-fat-long': (137, 0), 'config-fat-io': (137, 0),
                 'config-ebr': (63, 2), 'config-admin-type': (126, 0)}
    lba, detail = locations.get(fixture, (FILE_LBAS[0] if spec.get('status') in (3, 4, 5, 6) else 0, 0))
    return dict(spec, error_lba=lba, detail=detail)


def check_config_screen(data, strings, spec, record, index):
    rows = screen_rows(data)
    status, copies = spec.get('status', 0), spec.get('copies', [0, 0])

    def at(row, column, value):
        if rows[row][column:column + len(value)] != value:
            raise ValueError(f'Wrong configuration VGA text at {row},{column}: {value!r}; {rows[row]!r}')

    for row, column, key in ((2, 65, 'READ_ONLY'), (5, 4, 'CONFIG_TITLE'), (6, 4, 'CONFIG_SCOPE'),
                             (8, 4, 'CONFIG_COPIES'), (9, 4, STATUS_KEYS[status]),
                             (19, 4, 'CONFIG_HELP'), (21, 4, 'KEY_HELP'), (22, 4, 'FUNCTION_HELP')):
        at(row, column, strings[key])
    at(8, 29, f'{copies[0]:04X} / {copies[1]:04X}')
    if not status and any(copies): at(7, 4, strings['CONFIG_DEGRADED'])
    elif rows[7][4:78].strip(): raise ValueError('Unexpected degraded configuration warning')
    if status:
        at(11, 4, strings['LBA_HEX']); at(12, 4, strings['CONFIG_DETAIL'])
        at(11, 23, f'{spec.get("error_lba", 0):08X}'); at(12, 29, f'{spec.get("detail", 0):04X}')
        if any(row[4:78].strip() for row in rows[13:19]):
            raise ValueError('Failed configuration displays stale profile data')
    else:
        generation, disk_id, fingerprint = struct.unpack_from('<III', record, 16)
        at(10, 4, strings['CONFIG_GENERATION']); at(10, 29, f'{generation:08X}')
        at(10, 39, 'B' if spec.get('source', 1) else 'A')
        at(11, 4, strings['CONFIG_IDENTITY_LABEL']); at(11, 29, f'{disk_id:08X}'); at(11, 40, f'{fingerprint:08X}')
        count = struct.unpack_from('<H', record, 36)[0]
        if not count:
            at(14, 4, strings['CONFIG_EMPTY'])
            if any(rows[r][4:78].strip() for r in (13, 15, 16, 17, 18)):
                raise ValueError('Empty configuration displays stale profiles')
        else:
            p = record[64 + index * 48:112 + index * 48]
            entry_id, start, sectors = struct.unpack_from('<III', p)
            at(13, 4, p[20:20 + p[18]].decode('cp437'))
            for row, key in ((14, 'CONFIG_ENTRY'), (15, 'CONFIG_EXTENT'), (18, 'PAGE')): at(row, 4, strings[key])
            at(14, 29, f'{entry_id:08X}'); at(14, 40, f'P{p[12]}'); at(14, 46, f'{p[13]:02X}')
            at(15, 29, f'{start:08X}'); at(15, 40, f'{sectors:08X}')
            at(16, 4, 'dos9x_isolated' if p[14] == 1 else 'nt_chain')
            at(16, 29, strings['CONFIG_FLAGS']); at(16, 57, str(p[15])); at(16, 61, str(p[16])); at(16, 65, f'{p[17]:02X}')
            at(18, 10, str(index + 1)); at(18, 14, str(count))
    for row in range(2, 23):
        if data[(row * 80 + 1) * 2] != 0xB3 or data[(row * 80 + 78) * 2] != 0xB3:
            raise ValueError('Configuration text overwrote its frame')
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
    output = ROOT / 'build' / output_name('config', args.language)
    prepare_output(output)
    result_file = output / 'config-results.json'; result_file.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    strings = checked_catalog(manifest, args.language)
    for name, info in manifest['artifacts'].items():
        if name.startswith(('stage2', 'int13-')) and sha256(source / name) != info['sha256']:
            raise ValueError('Changed configuration test component: ' + name)
    events = output / 'ide-events.txt'
    events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n', encoding='ascii')
    command = [str(qemu), '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
               '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'c', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot',
               '-global', 'isa-debugcon.iobase=0xe9', '-qmp', 'stdio']
    fixtures = {**manifest['config_cases'], 'retroboot-hdd': {'source': 0}, 'retroboot-handoff': {'source': 0}}
    scenarios = [(fixture, spec, mode, rom) for fixture, spec in fixtures.items()
                 for mode, rom in (('EDD', 0), ('CHS', 1))]
    scenarios.append(('config-newer', {}, 'EDD', None))
    results, pairs = [], {}
    for fixture, spec, mode, rom in scenarios:
        spec = expected_location(fixture, spec)
        name = fixture + '-' + (mode.lower() if rom is not None else 'bare')
        status, copies = spec.get('status', 0), spec.get('copies', [0, 0])
        chosen = spec.get('source', 1) if not status else 0xFFFF
        variant = 'handoff' if fixture == 'retroboot-handoff' else 'normal'
        payload = (source / ('stage2' + ('-handoff' if variant == 'handoff' else '') + '.bin')).read_bytes()
        memory = manifest['memory'][variant]
        image = source / (fixture + '.img'); image_hash = sha256(image)
        if image_hash != manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed configuration fixture')
        with image.open('rb') as stream:
            mbr = stream.read(512)
            stream.seek(FILE_LBAS[0 if status else chosen] * 512); record = stream.read(512)
        count = 0 if status else struct.unpack_from('<H', record, 36)[0]
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
        actions = [(None, 0), ('f5', 6), ('left', 6), ('right', 6), ('ret', 6), ('f4', 6),
                   ('esc', 0), ('f8', 3), ('f5', 6), ('esc', 0)]
        if fixture == 'config-newer': actions[3:3] = [('left', 6)] * 7 + [('right', 6)] * 9
        screens, expected_reads, before_low = [], [], None
        selected, index, attempts = 0, 0, 0
        with error.open('w', encoding='utf-8') as errors, subprocess.Popen(
                invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process); wait_marker(process, log, 'RB MENU READY')
                for serial, (key, view) in enumerate(actions):
                    if key == 'f8': selected = 2
                    if key == 'f5':
                        reads = list(spec.get('reads', BASE_READS))
                        if attempts and spec.get('fault_once'): reads = list(BASE_READS)
                        expected_reads += reads; attempts += 1; index = 0
                    elif key in ('left', 'right') and count:
                        index = (index + (1 if key == 'right' else -1)) % count
                    if key:
                        qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
                        time.sleep(0.05)
                        wait_marker(process, log, f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                        if fixture == 'config-declared-ready' and serial == 1: time.sleep(1.2)
                    qmp.call('stop')
                    paths = {kind: output / f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga', 'ram', 'low')}
                    for kind, address, length in (('vga', 0xB8000, 4000), ('ram', 0x10000, 0x10000), ('low', 0, 0x8000)):
                        qmp.call('pmemsave', {'val': address, 'size': length, 'filename': str(paths[kind])})
                    ram, low, vga = (paths[k].read_bytes() for k in ('ram', 'low', 'vga'))
                    check_runtime_memory(ram, payload, memory, mode)
                    if before_low is None: before_low = low
                    if low[0x7C00:0x7E00] != before_low[0x7C00:0x7E00] or low[0x800:0x840] != before_low[0x800:0x840]:
                        raise ValueError('Configuration diagnosis staged a target or executed its VBR')
                    boot = ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot'] + 12]
                    rows = check_config_screen(vga, strings, spec, record, index) if view == 6 else check_screen(
                        vga, view, selected, mode, mbr, boot, strings)
                    (output / f'{name}-{serial:02d}.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
                    if serial == 1: qmp.call('screendump', {'filename': str(output / f'{name}.png'), 'format': 'png'})
                    screens.append({'key': key, 'view': view, 'entry': index, 'vga_sha256': sha256(paths['vga'])})
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5) != 0: raise ValueError('QEMU did not exit cleanly')
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
        text = log.read_text(encoding='utf-8'); check_c_status(text, mode)
        marker = f'RB CONFIG status={status:04X} copies={copies[0]:04X}{copies[1]:04X} source={chosen:04X} count={count:04X}'
        if text.count(marker) != attempts or text.count(f'RB UI {args.language} CP437') != 1:
            raise ValueError('Missing configuration diagnostics: ' + name)
        if 'RB HANDOFF BEGIN' in text or 'RB HANDOFF PASS' in text: raise ValueError('Configuration started a target')
        trace_text = trace.read_text(encoding='utf-8'); check_trace(trace_text); lbas = read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text, mode)
            boot_calls = check_bios_route(text.split('RB MENU READY', 1)[0], mode)
            boot_reads = 1 + boot_calls.count('42' if mode == 'EDD' else '02')
            if lbas[boot_reads:] != expected_reads:
                raise ValueError(f'Unexpected configuration reads: {name}: {lbas[boot_reads:]} != {expected_reads}')
            pairs.setdefault(fixture, {})[mode] = lbas
        elif lbas != pairs[fixture]['EDD']: raise ValueError('Uninstrumented configuration reads differ')
        if sha256(image) != image_hash: raise ValueError('Configuration diagnosis changed its image')
        results.append({'name': name, 'mode': mode, 'status': status, 'copies': copies, 'source': chosen,
                        'screens': screens, 'read_lbas': lbas, 'post_menu_reads': expected_reads,
                        'image_unchanged': True, 'block_writes': 0})
        print(f'{name}: {len(screens)} states, configuration/FAT/identity checked; no writes', flush=True)
    if any(p['EDD'] != p['CHS'] for p in pairs.values()): raise ValueError('Configuration EDD/CHS reads differ')
    result_file.write_text(json.dumps({'ui': manifest['ui'], 'qemu_version': subprocess.check_output(
        [str(qemu), '--version'], text=True).splitlines()[0], 'qemu_sha256': sha256(qemu),
        'bios_sha256': sha256(bios), 'vga_bios_sha256': sha256(bios.with_name('vgabios-stdvga.bin')),
        'machine': 'pc-i440fx-8.2', 'cpu': '486', 'ram_mib': 16, 'cases': results}, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'Configuration test: {error}', file=sys.stderr); sys.exit(1)
