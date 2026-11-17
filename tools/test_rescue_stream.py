"""Boot the normal F7 dry run and check the order of file, HDD and BIOS operations."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from .backup_payload_vectors import expected_reads as capture_reads, payload_reads
    from .build_inputs import check_build_inputs
    from .build_rescue import ROOT, prepare_output, sha256
    from .rescue_file_fixtures import expected_file_reads, file_chain
    from .rescue_text import LANGUAGES, load_catalog, output_name
    from .test_menu import Qmp, screen_rows, wait_marker
    from .test_rescue import check_memory, check_screen as check_home, trace_reads
except ImportError:
    from backup_payload_vectors import expected_reads as capture_reads, payload_reads
    from build_inputs import check_build_inputs
    from build_rescue import ROOT, prepare_output, sha256
    from rescue_file_fixtures import expected_file_reads, file_chain
    from rescue_text import LANGUAGES, load_catalog, output_name
    from test_menu import Qmp, screen_rows, wait_marker
    from test_rescue import check_memory, check_screen as check_home, trace_reads


# Each action selects a fresh reference diskette in the same running guest.
CASES = {
    'retry': (0, ('ok', 'resealed', 'ok', 'missing', 'ok')),
    'chs': (1, ('ok',)),
    'no-hdd': (0, ('absent',)),
    'stale-extents': (0, ('extent',)),
    'opening-probe': (6, ('opening',)),
    'changed-device': (14, ('changed',)),
    'closing-probe': (15, ('closing',)),
    'closing-file': (16, ('file',)),
}
CODES = {'ok': (0, 0, 0), 'missing': (1, 5, 0), 'resealed': (6, 6, 6),
         'absent': (3, 1, 0), 'opening': (3, 2, 0), 'changed': (5, 1, 0),
         'closing': (7, 2, 0), 'file': (2, 1, 1), 'extent': (6, 5, 3)}
REASONS = {'ok': 'S_OK', 'resealed': 'S_DIFFER', 'missing': 'B_MISSING', 'absent': 'NO_DISK',
           'opening': 'PARAMS', 'closing': 'S_REPROBE', 'changed': 'T_CHANGED', 'file': 'B_BAD',
           'extent': 'S_BAD'}


def expected_io(image, outcome, chs):
    """Interleave BIOS calls and physical floppy offsets, with separate HDD LBA evidence."""
    def floppy(lbas):
        return [f'%{lba:04X}' for lba in lbas]

    if outcome == 'missing':
        return floppy(range(33)), []
    validated = expected_file_reads(image, 'file-demo')
    events = floppy(validated)
    probe = ['@41', '@08' if chs else '@48']
    if outcome == 'absent':
        return events, []
    events += probe
    if outcome == 'opening':
        return events, []
    mapping = file_chain(image)
    live = payload_reads()[1:]
    capture = capture_reads()
    read = '@02' if chs else '@42'
    if outcome == 'extent':
        return events + [read] * len(capture), capture
    hdd = list(capture) + live
    events += [read] * len(capture) + floppy(mapping[5:7]) + [read] * len(live)
    events += floppy(mapping[:5] + [mapping[5]] * 2 + [mapping[6]] * 2)
    for pos, lba in enumerate(live, 7):
        hdd.append(lba)
        events.extend([read, f'%{mapping[pos]:04X}'])
        if outcome == 'resealed' and pos == 41:
            return events, hdd
    hdd += capture
    events += [read] * len(capture) + probe
    if outcome == 'ok':
        events += floppy(validated[33:])
    elif outcome == 'file':
        events += floppy(mapping[:1])
    return events, hdd


def check_screen(data, strings, outcome):
    rows = screen_rows(data)
    codes = ' / '.join(f'0x{value:04X}' for value in CODES[outcome])
    cells = ((2, 65, strings['READ_ONLY']), (5, 4, strings['S_SCOPE']),
             (6, 4, strings['S_LIMIT']), (8, 4, strings[REASONS[outcome]]),
             (9, 4, strings['T_CODES']), (9, 32, codes), (11, 4, strings['S_COUNT']),
             (21, 4, strings['S_HELP']))
    for row, col, value in cells:
        if rows[row][col:col + len(value)] != value:
            raise ValueError(f'{outcome}, VGA row {row}: expected {value!r}, got {rows[row]!r}')
    count = 45 if outcome == 'ok' else 0
    if rows[11][32:78].strip() != str(count) or data[(8 * 80 + 4) * 2 + 1] != (0x1A if count else 0x1E):
        raise ValueError(f'{outcome}: wrong verified count or result color')
    return rows, count


def main(work):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    parser.add_argument('--case', choices=CASES, action='append')
    args = parser.parse_args()
    exe = shutil.which(args.qemu)
    if not exe:
        raise ValueError('QEMU not found')
    bios = (args.bios or Path(exe).resolve().parents[1] / 'share/seabios/bios-256k.bin').resolve()
    source = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('rescue-stream-test' + ('-de' if args.language == 'de' else ''))
    prepare_output(out)
    report = out / 'stream-results.json'
    report.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    strings = load_catalog(args.language)
    payload = (source / 'retroboot-rescue.bin').read_bytes()
    memory = manifest['memory']['retroboot-rescue']
    images = {key: source / ('retroboot-rescue' + suffix + '.img') for key, suffix in (
        ('ok', '-stream'), ('chs', '-stream-chs'), ('resealed', '-stream-resealed'),
        ('missing', ''), ('extent', '-demo'), ('hdd', '-target-hdd'))}
    before = {key: sha256(path) for key, path in images.items()}
    if any(before[key] != manifest['artifacts'][p.name]['sha256'] for key, p in images.items()):
        raise ValueError('Stream fixture differs from build manifest')
    events = out / 'events.txt'
    events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    shutil.copyfile(images['hdd'], work)
    results = []
    for case in args.case or CASES:
        rom, actions = CASES[case]
        first = images['chs'] if rom == 1 else images.get(actions[0], images['ok'])
        log, trace, err = (out / (case + suffix) for suffix in ('.log', '.trace', '-stderr.log'))
        log.unlink(missing_ok=True)
        trace.unlink(missing_ok=True)
        cmd = [exe, '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
               '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'a', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot', '-qmp', 'stdio',
               '-global', 'isa-debugcon.iobase=0xe9', '-debugcon', 'file:' + str(log),
               '-trace', f'events={events},file={trace}', '-option-rom', str(source / f'int13-{rom}.rom'),
               '-drive', f'file={first},format=raw,if=floppy,id=bootfloppy,readonly=on']
        if case != 'no-hdd':
            cmd += ['-drive', f'file={work},format=raw,if=none,id=rb',
                    '-device', 'ide-hd,drive=rb,bus=ide.0,unit=0,cyls=260,heads=16,secs=63,lcyls=260,lheads=16,lsecs=63']
        all_lbas = []
        states = []
        with err.open('w') as errors, subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=errors, text=True, bufsize=1) as process:
            try:
                qmp = Qmp(process)
                wait_marker(process, log, 'RB RESCUE READY')
                for serial, outcome in enumerate(actions, 1):
                    floppy = images.get(outcome, first) if rom != 1 else first
                    if serial > 1:
                        qmp.call('blockdev-change-medium', {'device': 'bootfloppy', 'filename': str(floppy),
                                 'format': 'raw', 'read-only-mode': 'read-only'})
                    key = 'f7' if serial == 1 else 'ret'
                    qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
                    text = wait_marker(process, log, f'RB RESCUE KEY {serial:04X} view=0005', timeout=40)
                    qmp.call('stop')
                    paths = {}
                    for region, addr, size in (('ram', 0x10000, 65536), ('vga', 0xB8000, 4000)):
                        paths[region] = out / f'{case}-{serial}-{region}.bin'
                        qmp.call('pmemsave', {'val': addr, 'size': size, 'filename': str(paths[region])})
                    rows, count = check_screen(paths['vga'].read_bytes(), strings, outcome)
                    (out / f'{case}-{serial}.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')
                    ram = paths['ram'].read_bytes()
                    check_memory(ram, payload, memory, zero_bss=False)
                    start = memory['header']['stack_low'] + 2
                    stack = ram[start:memory['header']['stack_top']]
                    untouched = next((i for i, byte in enumerate(stack) if byte != 0xA5), len(stack))
                    if not 0 < untouched < len(stack):
                        raise ValueError('Invalid stack watermark')
                    expected, lbas = expected_io(floppy.read_bytes(), outcome, rom == 1)
                    actual = re.findall(r'^([@%][0-9A-F]+)$', text.rsplit('RB STREAM BEGIN', 1)[1], re.M)
                    all_lbas.extend(lbas)
                    if actual != expected or trace_reads(trace.read_text()) != all_lbas:
                        raise ValueError(f'{case}/{outcome}: BIOS, floppy or HDD sequence differs')
                    states.append(dict(outcome=outcome, codes=CODES[outcome], verified=count, hdd_reads=len(lbas),
                                       stack_untouched_bytes=untouched, vga_sha256=sha256(paths['vga'])))
                    qmp.call('cont')
                qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}], 'hold-time': 30})
                marker = f'RB RESCUE KEY {len(actions) + 1:04X} view=0000'
                text = wait_marker(process, log, marker)
                qmp.call('stop')
                home = out / f'{case}-home-vga.bin'
                qmp.call('pmemsave', {'val': 0xB8000, 'size': 4000, 'filename': str(home)})
                check_home(home.read_bytes(), strings, 0, {}, 'EDD', 0, (0, 0), bytes(512))
                tail = text.split(f'RB RESCUE KEY {len(actions):04X} view=0005')[-1]
                if re.search(r'^[@%]', tail, re.M) or trace_reads(trace.read_text()) != all_lbas:
                    raise ValueError('Leaving F7 unexpectedly used a disk')
                qmp.call('quit')
                if process.wait(timeout=5):
                    raise ValueError('QEMU exit failed')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        if '!W' in log.read_text() or re.search(r'ide_sector_write|blk_co_pwritev', trace.read_text()):
            raise ValueError(f'{case}: attempted write')
        if sha256(work) != before['hdd']:
            raise ValueError(f'{case}: guest changed the HDD copy')
        results.append(dict(name=case, rom=rom, states=states, block_writes=0))
        print(f'{case}: verified counts {[s["verified"] for s in states]}, exact I/O, no writes', flush=True)
    if any(sha256(p) != before[key] for key, p in images.items()):
        raise ValueError('Source medium changed')
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(ui=manifest['ui'], build_inputs=manifest['build_inputs'], cases=results,
        media_sha256=before, bios_sha256=sha256(bios), qemu_sha256=sha256(Path(exe))), indent=2) + '\n')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        main(Path(directory) / 'target.img')
