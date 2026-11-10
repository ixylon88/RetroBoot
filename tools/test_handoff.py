"""Prove T07 by executing an independent VBR and inspecting real guest memory."""
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
    from .handoff_fixtures import LBA, entry_bytes
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, expected_partitions, screen_rows, wait_marker
    from .ui_text import LANGUAGES, ERROR_KEYS, VOLUME_KEYS, checked_catalog, output_name
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from handoff_fixtures import LBA, entry_bytes
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, expected_partitions, screen_rows, wait_marker
    from ui_text import LANGUAGES, ERROR_KEYS, VOLUME_KEYS, checked_catalog, output_name


def check_receipt(low, before, vbr, fault=None):
    if low[0x7C00:0x7E00] != vbr:
        raise ValueError('Target VBR was not handed over byte-for-byte')
    if low[0x4C:0x50] != before[0x4C:0x50]:
        raise ValueError('INT 13h vector changed during handoff')
    if low[0x600:0x800] != before[0x600:0x800] or low[0x810:0x820] != before[0x810:0x820]:
        raise ValueError('Handoff entry copy damaged adjacent memory')
    expected_entry = bytearray(entry_bytes())
    if fault == 'entry': expected_entry[1] ^= 1
    if low[0x800:0x810] != expected_entry or low[0x820:0x824] != b'RBH1':
        raise ValueError('Wrong stable partition entry or missing VBR receipt')
    values = dict(zip(('flags', 'cs', 'ds', 'es', 'ss', 'sp', 'si', 'dx', 'fs', 'gs', 'ip', 'status'),
                      struct.unpack_from('<12H', low, 0x824)))
    expected = dict(cs=0, ds=0, es=0, ss=0, sp=0x7C00, si=0x800, dx=0x80, fs=0, gs=0)
    if fault in ('ds', 'es'): expected[fault] = 0x80
    elif fault == 'ss': expected['ss'] = 0x1000
    elif fault == 'sp': expected['sp'] = 0x7B00
    elif fault == 'si': expected['si'] = 0x801
    elif fault == 'dl': expected['dx'] = 0x81
    expected_flags = 0x600 if fault == 'df' else 0 if fault == 'if' else 0x200
    if (any(values[k] != v for k, v in expected.items()) or values['flags'] & 0x600 != expected_flags
            or values['status'] != bool(fault)):
        raise ValueError('Unexpected VBR entry state: ' + str(values))
    if not fault and not 0x7C3E < values['ip'] < 0x7DFE:
        raise ValueError('VBR did not confirm its execution address')
    return values


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
    if not bios.is_file() or not bios.with_name('vgabios-stdvga.bin').is_file():
        raise ValueError('SeaBIOS and VGA ROM are required; use --bios')
    source = ROOT / 'build' / output_name('hdd', args.language)
    output = ROOT / 'build' / output_name('handoff', args.language)
    prepare_output(output)
    result_file = output / 'handoff-results.json'
    result_file.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    strings = checked_catalog(manifest, args.language)
    for name, info in manifest['artifacts'].items():
        if name.startswith(('stage2', 'int13-', 'handoff-vbr')) and sha256(source / name) != info['sha256']:
            raise ValueError('Changed handoff test component: ' + name)
    vbr = (source / 'handoff-vbr.bin').read_bytes()
    events = output / 'ide-events.txt'
    events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n', encoding='ascii')
    command = [str(qemu), '-L', str(bios.parent), '-bios', str(bios),
               '-machine', 'pc-i440fx-8.2,accel=tcg', '-cpu', '486', '-m', '16',
               '-nodefaults', '-vga', 'std', '-boot', 'c', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot',
               '-global', 'isa-debugcon.iobase=0xe9', '-qmp', 'stdio']
    scenarios = [(fixture, spec, mode, rom) for fixture, spec in manifest['handoff_cases'].items()
                 for mode, rom in (('EDD', 0), ('CHS', 1))]
    scenarios += [('retroboot-hdd', {}, mode, rom) for mode, rom in (('EDD', 0), ('CHS', 1))]
    scenarios.append(('retroboot-handoff', {}, 'EDD', None))
    results, pairs = [], {}
    for fixture, spec, mode, rom in scenarios:
        name = fixture + '-' + (mode.lower() if rom is not None else 'bare')
        normal = fixture == 'retroboot-hdd'
        fault = spec.get('register_fault')
        variant = 'normal' if normal else 'handoff' + ('-' + fault if fault else '')
        payload = (source / ('stage2' + ('' if normal else '-' + variant) + '.bin')).read_bytes()
        memory = manifest['memory'][variant]
        image = source / (fixture + '.img')
        image_hash = sha256(image)
        if image_hash != manifest['artifacts'][image.name]['sha256']: raise ValueError('Changed fixture')
        with image.open('rb') as stream: mbr = stream.read(512)
        log, trace, error = (output / (name + suffix) for suffix in ('.log', '.trace', '-stderr.log'))
        log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
        drive = str(image)
        if 'fault_once' in spec:
            conf = output / (name + '.conf')
            conf.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                            f'sector = "{LBA}"\nonce = "' + ('on' if spec['fault_once'] else 'off') + '"\n', encoding='ascii')
            drive = f'blkdebug:{conf}:{image}'
        invocation = command + ['-drive', f'file={drive.replace(",", ",,")},format=raw,if=ide,snapshot=on,rerror=report',
                                '-debugcon', 'file:' + str(log), '-trace',
                                f'events={str(events).replace(",", ",,")},file={str(trace).replace(",", ",,")}']
        if rom is not None: invocation += ['-option-rom', str(source / f'int13-{rom}.rom')]
        if normal: actions = [(None, 0), ('f4', 0)]
        elif spec.get('status'): actions = [(None, 0), ('f4', 5), ('esc', 0), ('f8', 3), ('esc', 0), ('f4', 5), ('esc', 0)]
        elif fixture == 'retroboot-handoff': actions = [(None, 0), ('f3', 4), ('f4', 4), ('esc', 0), ('f4', 6)]
        else: actions = [(None, 0), ('f4', 6)]
        screens, expected_reads, before_low, receipt = [], [], None, None
        selected, attempts = 0, 0
        with error.open('w', encoding='utf-8') as errors, subprocess.Popen(
                invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process)
                wait_marker(process, log, 'RB MENU READY')
                for serial, (key, view) in enumerate(actions):
                    if key == 'f3': selected = 1; expected_reads += [0, 63, LBA]
                    if key == 'f8': selected = 2
                    if key == 'f4' and view in (5, 6):
                        attempts += 1
                        expected_reads += [0]
                        if fixture not in ('handoff-tables', 'handoff-identity'): expected_reads += [63]
                        if spec.get('status') not in (1, 2):
                            expected_reads += [LBA] * (3 if spec.get('fault_once') is False else 2 if spec.get('fault_once') is True else 1)
                    if key:
                        qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
                        time.sleep(0.05)
                        if view == 6:
                            wait_marker(process, log, 'Test VBR reached. Reboot to return.\n\n')
                        else:
                            wait_marker(process, log, f'RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000')
                    qmp.call('stop')
                    paths = {kind: output / f'{name}-{serial:02d}-{kind}.bin' for kind in ('vga', 'ram', 'low')}
                    for kind, address, length in (('vga', 0xB8000, 4000), ('ram', 0x10000, 0x10000), ('low', 0, 0x8000)):
                        qmp.call('pmemsave', {'val': address, 'size': length, 'filename': str(paths[kind])})
                    ram, low, vga = (paths[k].read_bytes() for k in ('ram', 'low', 'vga'))
                    check_runtime_memory(ram, payload, memory, mode)
                    if before_low is None: before_low = low
                    if view == 6:
                        receipt = check_receipt(low, before_low, vbr, fault)
                        rows = screen_rows(vga)
                        marker = 'RB HANDOFF FAIL' if fault else 'RB HANDOFF PASS'
                        if not rows[0].startswith(marker) or not rows[1].startswith('Test VBR reached. Reboot to return.'):
                            raise ValueError('Missing visible handoff result')
                    else:
                        if low[0x7C00:0x7E00] != before_low[0x7C00:0x7E00] or low[0x800:0x840] != before_low[0x800:0x840]:
                            raise ValueError('An unapproved target was staged/executed')
                        boot = ram[memory['symbols']['_rb_boot']:memory['symbols']['_rb_boot'] + 12]
                        if view == 5:
                            rows = screen_rows(vga)
                            reason = (ERROR_KEYS[spec['detail']] if spec['status'] == 2 else
                                      VOLUME_KEYS[spec['detail']] if spec['status'] == 3 else
                                      'HANDOFF_TARGET' if spec['status'] == 1 else 'HANDOFF_CODE')
                            for row, text in ((5, strings['HANDOFF_FAILED']), (6, strings[reason]), (8, strings['HANDOFF_REASON']),
                                              (10, f'{spec["status"]:04X} / {spec["detail"]:04X}'),
                                              (13, strings['NO_CHANGES']), (18, strings['HANDOFF_RETRY'])):
                                if rows[row][4:4 + len(text)] != text: raise ValueError('Wrong handoff rejection page')
                        elif view == 4:
                            partitions = expected_partitions(image)
                            volume = dict(partitions[0], logical=False, status=0, bits=16,
                                          cluster_bytes=512, total=5073, clusters=5000, data_lba=LBA + 73)
                            rows = check_screen(vga, view, selected, mode, mbr, boot, strings, volume=volume)
                        else:
                            rows = check_screen(vga, view, selected, mode, mbr, boot, strings)
                            if view == 0:
                                if normal and rows[19][4:78].strip(): raise ValueError('Normal image exposes test handoff')
                                if not normal and rows[19][4:4 + len(strings['HANDOFF_HELP'])] != strings['HANDOFF_HELP']:
                                    raise ValueError('Missing handoff test key hint')
                    (output / f'{name}-{serial:02d}.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
                    if serial == 0 or view in (5, 6):
                        qmp.call('screendump', {'filename': str(output / f'{name}-{serial:02d}.png'), 'format': 'png'})
                    screens.append({'key': key, 'view': view, 'vga_sha256': sha256(paths['vga'])})
                    qmp.call('cont')
                qmp.call('quit')
                if process.wait(timeout=5) != 0: raise ValueError('QEMU did not exit cleanly')
            finally:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
        text = log.read_text(encoding='utf-8')
        check_c_status(text, mode)
        if text.count(f'RB UI {args.language} CP437') != 1: raise ValueError('Wrong handoff test language')
        if spec.get('status'):
            if text.count(f'RB HANDOFF REJECT status={spec["status"]:04X} detail={spec["detail"]:04X}') != attempts:
                raise ValueError('Missing handoff rejection diagnostics')
        for marker, expected in (('RB HANDOFF PASS', int(not normal and not spec.get('status') and not fault)),
                                 ('RB HANDOFF FAIL', int(bool(fault)))):
            if text.count(marker) != expected: raise ValueError('Contradictory handoff outcome')
        trace_text = trace.read_text(encoding='utf-8'); check_trace(trace_text)
        lbas = read_lbas(trace_text)
        if rom is not None:
            check_bios_route(text, mode)
            boot_calls = check_bios_route(text.split('RB MENU READY', 1)[0], mode)
            boot_reads = 1 + boot_calls.count('42' if mode == 'EDD' else '02')
            if lbas[boot_reads:] != expected_reads: raise ValueError(f'Wrong handoff reads: {name}: {lbas[boot_reads:]} != {expected_reads}')
            pairs.setdefault(fixture, {})[mode] = lbas
        elif lbas != pairs[fixture]['EDD']:
            raise ValueError('Uninstrumented boot reads differ')
        if sha256(image) != image_hash: raise ValueError('Handoff changed its source image')
        results.append({'name': name, 'mode': mode, 'screens': screens, 'receipt': receipt, 'read_lbas': lbas,
                        'post_menu_reads': expected_reads, 'image_unchanged': True, 'block_writes': 0})
        print(f'{name}: {len(screens)} states, independent VBR/negative gate verified; no writes', flush=True)
    if any(p['EDD'] != p['CHS'] for p in pairs.values()): raise ValueError('Handoff EDD/CHS reads differ')
    report = {'ui': manifest['ui'], 'qemu_version': subprocess.check_output([str(qemu), '--version'], text=True).splitlines()[0],
              'qemu_sha256': sha256(qemu), 'bios_sha256': sha256(bios),
              'vga_bios_sha256': sha256(bios.with_name('vgabios-stdvga.bin')),
              'machine': 'pc-i440fx-8.2', 'cpu': '486', 'ram_mib': 16, 'cases': results}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f'Handoff test: {error}', file=sys.stderr); sys.exit(1)
