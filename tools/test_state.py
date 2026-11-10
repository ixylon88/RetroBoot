"""Exercise independent installation records and current target evidence through F6."""
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
    from .state_fixtures import BASE_READS, FILE_LBAS, PROOF_READS
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, screen_rows, wait_marker
    from .ui_text import LANGUAGES, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from config_fixtures import FILE_LBAS as CONFIG_LBAS
    from state_fixtures import BASE_READS, FILE_LBAS, PROOF_READS
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, screen_rows, wait_marker
    from ui_text import LANGUAGES, checked_catalog, output_name

PROOF_KEYS = ('STATE_MATCH', 'STATE_CONFIG', 'STATE_RECORD', 'STATE_DEGRADED', 'STATE_LEGACY',
              'STATE_IDENTITY', 'STATE_EMPTY', 'STATE_PENDING', 'STATE_INSTALLATION', 'STATE_TARGET',
              'STATE_NOT_READY', 'STATE_APPROVAL', 'STATE_SCAN', 'STATE_LAYOUT', 'STATE_VOLUME', 'STATE_VBR')


def check_state_screen(data, strings, spec, record, config, index):
    rows = screen_rows(data)
    status, proof = spec.get('status', 0), spec.get('proof', 0)
    def at(row, column, value):
        if rows[row][column:column + len(value)] != value:
            raise ValueError(f'Wrong state VGA text at {row},{column}: {value!r}; {rows[row]!r}')
    for row, key in ((5, 'STATE_TITLE'), (6, 'STATE_SCOPE'), (7, 'STATE_CONFIG_COPIES'),
                     (8, 'STATE_COPIES'), (13, 'STATE_REASON'), (19, 'STATE_HELP'),
                     (21, 'KEY_HELP'), (22, 'FUNCTION_HELP')): at(row, 4, strings[key])
    at(2, 65, strings['READ_ONLY']); at(12, 4, strings[PROOF_KEYS[proof]])
    for row, pair in ((7, spec.get('config_copies', [0, 0])), (8, spec.get('copies', [0, 0]))):
        at(row, 29, f'{pair[0]:04X} / {pair[1]:04X}')
    at(13, 29, f'{proof:04X} / {spec.get("detail", 0):04X}')
    if not status:
        at(9, 4, strings['CONFIG_GENERATION']); at(9, 29, f'{struct.unpack_from("<I", record, 16)[0]:08X}')
        at(9, 39, 'B' if spec.get('source', 1) else 'A'); at(10, 4, strings['STATE_MEDIA'])
        at(10, 29, record[48:64].hex().upper())
    elif any(rows[r][4:78].strip() for r in (9, 10)):
        raise ValueError('Failed state record displays stale identity')
    count = struct.unpack_from('<H', config, 36)[0] if not any(spec.get('config_copies', [0, 0])) else 0
    if count:
        version = struct.unpack_from('<H', config, 8)[0]; stride = 52 if version == 2 else 48
        p = config[64 + index * stride:64 + (index + 1) * stride]
        at(14, 4, p[20:20 + p[18]].decode('cp437')); at(15, 4, strings['STATE_INSTALL_ID'])
        at(15, 29, f'{struct.unpack_from("<Q", p, 44)[0] if version == 2 else 0:016X}')
        at(18, 4, strings['PAGE']); at(18, 10, str(index + 1)); at(18, 14, str(count))
    elif any(rows[r][4:78].strip() for r in (14, 15, 18)):
        raise ValueError('Empty installation-state displays stale installation')
    if not proof:
        at(17, 4, strings['STATE_CRC']); at(17, 29, f'{struct.unpack_from("<I", record, 84)[0]:08X}')
    else:
        at(17, 4, strings['LBA_HEX']); at(17, 23, f'{spec.get("error_lba", 0):08X}')
        if strings['STATE_CRC'] in rows[17]: raise ValueError('Failed proof displays stale CRC')
    if data[(12 * 80 + 4) * 2 + 1] != (0x1E if proof else 0x1A): raise ValueError('Wrong proof color')
    for row in range(2, 23):
        if data[(row * 80 + 1) * 2] != 0xB3 or data[(row * 80 + 78) * 2] != 0xB3:
            raise ValueError('State text overwrote its frame')
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
    output = ROOT / 'build' / output_name('state', args.language)
    prepare_output(output)
    result_file = output / 'state-results.json'; result_file.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    strings = checked_catalog(manifest, args.language)
    for name, info in manifest['artifacts'].items():
        if name.startswith(('stage2', 'int13-')) and sha256(source / name) != info['sha256']:
            raise ValueError('Changed installation-state test component: ' + name)
    events = output / 'ide-events.txt'
    events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n', encoding='ascii')
    command = [str(qemu), '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
               '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'c', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot',
               '-global', 'isa-debugcon.iobase=0xe9', '-qmp', 'stdio']
    fixtures = {**manifest['state_cases'], 'retroboot-hdd': {'source': 0, 'proof': 6}, 'retroboot-handoff': {'source': 0}}
    scenarios = [(fixture, spec, mode, rom) for fixture, spec in fixtures.items()
                 for mode, rom in (('EDD', 0), ('CHS', 1))]
    scenarios.append(('state-match', {}, 'EDD', None))
    results, pairs = [], {}
    for fixture, spec, mode, rom in scenarios:
        name = fixture + '-' + (mode.lower() if rom is not None else 'bare')
        status, copies = spec.get('status', 0), spec.get('copies', [0, 0])
        chosen = spec.get('source', 1) if not status else 0xFFFF
        variant = 'handoff' if fixture == 'retroboot-handoff' else 'normal'
        payload = (source / ('stage2' + ('-handoff' if variant == 'handoff' else '') + '.bin')).read_bytes()
        memory = manifest['memory'][variant]
        image = source / (fixture + '.img'); image_hash = sha256(image)
        if image_hash != manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed installation-state fixture')
        with image.open('rb') as stream:
            mbr = stream.read(512)
            stream.seek(FILE_LBAS[0 if status else chosen] * 512); record = stream.read(512)
            stream.seek(CONFIG_LBAS[0] * 512); config = stream.read(512)
        count = 0 if any(spec.get('config_copies', [0, 0])) else struct.unpack_from('<H', config, 36)[0]
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
        actions = [(None, 0), ('f6', 7), ('left', 7), ('right', 7), ('ret', 7), ('f4', 7),
                   ('esc', 0), ('f8', 3), ('f6', 7), ('esc', 0)]
        screens, expected_reads, before_low = [], [], None
        proof_indices = []
        selected, index, attempts, proofs = 0, 0, 0, 0
        with error.open('w', encoding='utf-8') as errors, subprocess.Popen(
                invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process); wait_marker(process, log, 'RB MENU READY')
                for serial, (key, view) in enumerate(actions):
                    if key == 'f8': selected = 2
                    if key == 'f6':
                        reads = list(spec.get('reads', BASE_READS))
                        if attempts and spec.get('fault_once'): reads = list(BASE_READS)
                        expected_reads += reads; attempts += 1; index = 0
                    elif key in ('left', 'right') and count:
                        index = (index + (1 if key == 'right' else -1)) % count
                    if key == 'f6' or (key in ('left', 'right') and count):
                        if spec.get('proof', 0) in (0, 14, 15):
                            reads = list(spec.get('proof_reads', PROOF_READS))
                            if proofs and spec.get('fault_once'): reads = list(PROOF_READS)
                            expected_reads += reads
                        proofs += 1; proof_indices.append(index)
                    if key:
                        qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
                        time.sleep(0.05)
                        wait_marker(process, log, f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                        if fixture == 'state-match' and serial == 1: time.sleep(1.2)
                    qmp.call('stop')
                    paths = {kind: output / f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga', 'ram', 'low')}
                    for kind, address, length in (('vga', 0xB8000, 4000), ('ram', 0x10000, 0x10000), ('low', 0, 0x8000)):
                        qmp.call('pmemsave', {'val': address, 'size': length, 'filename': str(paths[kind])})
                    ram, low, vga = (paths[k].read_bytes() for k in ('ram', 'low', 'vga'))
                    check_runtime_memory(ram, payload, memory, mode)
                    if before_low is None: before_low = low
                    if low[0x7C00:0x7E00] != before_low[0x7C00:0x7E00] or low[0x800:0x840] != before_low[0x800:0x840]:
                        raise ValueError('Installation-state diagnosis staged a target or executed its VBR')
                    boot = ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot'] + 12]
                    rows = check_state_screen(vga, strings, spec, record, config, index) if view == 7 else check_screen(
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
        marker = f'RB STATE records={status:04X} copies={copies[0]:04X}{copies[1]:04X} source={chosen:04X}'
        proof_code = spec.get('proof', 0)
        proof_crc = struct.unpack_from('<I', record, 84)[0] if not proof_code else 0
        proof_markers = re.findall(r'RB STATE proof=[^\r\n]+', text)
        expected_markers = [f'RB STATE proof={proof_code:04X} detail={spec.get("detail", 0):04X} index={index:04X} crc={proof_crc:08X}' for index in proof_indices]
        if proof_markers != expected_markers: raise ValueError('Missing state proof diagnostics: ' + name)
        if text.count(marker) != attempts or text.count(f'RB UI {args.language} CP437') != 1:
            raise ValueError('Missing installation-state diagnostics: ' + name)
        if 'RB HANDOFF BEGIN' in text or 'RB HANDOFF PASS' in text: raise ValueError('Installation-state started a target')
        trace_text = trace.read_text(encoding='utf-8'); check_trace(trace_text); lbas = read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text, mode)
            boot_calls = check_bios_route(text.split('RB MENU READY', 1)[0], mode)
            boot_reads = 1 + boot_calls.count('42' if mode == 'EDD' else '02')
            if lbas[boot_reads:] != expected_reads:
                raise ValueError(f'Unexpected installation-state reads: {name}: {lbas[boot_reads:]} != {expected_reads}')
            pairs.setdefault(fixture, {})[mode] = lbas
        elif lbas != pairs[fixture]['EDD']: raise ValueError('Uninstrumented installation-state reads differ')
        if sha256(image) != image_hash: raise ValueError('Installation-state diagnosis changed its image')
        results.append({'name': name, 'mode': mode, 'status': status, 'copies': copies, 'source': chosen,
                        'proof': proof_code, 'proofs': proofs, 'screens': screens, 'read_lbas': lbas, 'post_menu_reads': expected_reads,
                        'image_unchanged': True, 'block_writes': 0})
        print(f'{name}: {len(screens)} states, record pairs/current VBR checked; no writes', flush=True)
    if any(p['EDD'] != p['CHS'] for p in pairs.values()): raise ValueError('Installation-state EDD/CHS reads differ')
    result_file.write_text(json.dumps({'ui': manifest['ui'], 'qemu_version': subprocess.check_output(
        [str(qemu), '--version'], text=True).splitlines()[0], 'qemu_sha256': sha256(qemu),
        'bios_sha256': sha256(bios), 'vga_bios_sha256': sha256(bios.with_name('vgabios-stdvga.bin')),
        'machine': 'pc-i440fx-8.2', 'cpu': '486', 'ram_mib': 16, 'cases': results}, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'Installation-state test: {error}', file=sys.stderr); sys.exit(1)
