"""Reserve review numbers on disposable copies, cut power and boot the same media again."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

try:
    from . import mbr_restart_fixtures as f
    from .build_inputs import check_build_inputs
    from .build_rescue import ROOT, prepare_output, sha256
    from .rescue_text import LANGUAGES, output_name
    from .test_menu import Qmp, screen_rows, wait_marker
    from .test_rescue import check_memory, trace_reads
except ImportError:
    import mbr_restart_fixtures as f
    from build_inputs import check_build_inputs
    from build_rescue import ROOT, prepare_output, sha256
    from rescue_text import LANGUAGES, output_name
    from test_menu import Qmp, screen_rows, wait_marker
    from test_rescue import check_memory, trace_reads

TITLE = 'RB MBR RESERVATION'
INSERT = 'INSERT DATA DISK AND PRESS ENTER TO RESERVE'
STAGED = 'STAGED DATA VERIFIED'
RETURN = 'REINSERT START DISK AND PRESS ENTER'
PASS = 'RB MBR RESERVE PASS'
BLOCK = 'RB MBR RESERVE BLOCKED'
W, C = f.RESERVATION_WITNESS, f.RESERVATION_CARRIER


def plan(point):
    new = f.Checkpoint(point.generation + 1, point.issued + 1, point.approved, point.previous)
    writes = [('data', new.slot + 1, new.payload), ('data', new.slot, f.header(b'RBCMT001', new, C)),
              ('boot', f.WITNESS_LBA + 1, f.header(b'RBWIT001', new, C))]
    return new, writes


def fault_rom(template, path, ordinal, mode):
    image = bytearray(template.read_bytes())
    marker = b'RBCUTv1'
    if image.count(marker) != 1:
        raise ValueError('Missing reservation fault ROM controls')
    start = image.index(marker) + len(marker)
    image[start:start + 2] = bytes((ordinal, mode))
    image[-1] = (image[-1] - sum(image)) & 255
    path.write_bytes(image)
    return path


def change(qmp, disk, protected):
    qmp.call('blockdev-change-medium', {'device': 'floppy', 'filename': str(disk), 'format': 'raw',
             'read-only-mode': 'read-only' if protected else 'read-write'})
    qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 30})


def boot(exe, bios, source, out, manifest, name, disks, lines, expected_writes, rom=None,
         protect=None, return_disk=None, cut=False):
    log, trace = (out / (name + ext) for ext in ('.log', '.trace'))
    log.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    args = [exe, '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
            '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'a', '-display', 'none',
            '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot', '-qmp', 'stdio',
            '-global', 'isa-debugcon.iobase=0xe9', '-debugcon', 'file:' + str(log),
            '-drive', f"if=floppy,id=floppy,format=raw,cache=writethrough,file={disks['boot']}",
            '-trace', f"events={out / 'events.txt'},file={trace}"]
    if rom:
        args += ['-option-rom', str(rom)]
    with (out / (name + '-stderr.log')).open('w') as err, subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1) as proc:
        try:
            q = Qmp(proc)
            if INSERT in lines:
                wait_marker(proc, log, INSERT + '\n')
                change(q, disks['data'], protect == 'data')
            cut_at_exchange = cut and rom is None
            if RETURN in lines and not cut_at_exchange:
                wait_marker(proc, log, RETURN + '\n')
                change(q, return_disk or disks['boot'], protect == 'boot')
            cut_marker = cut and not cut_at_exchange
            wait_marker(proc, log, ('~' if cut_marker else lines[-1]) + '\n')
            q.call('stop')
            vga, ram = (out / (name + ext) for ext in ('-vga.bin', '-ram.bin'))
            q.call('pmemsave', {'val': 0xb8000, 'size': 4000, 'filename': str(vga)})
            q.call('pmemsave', {'val': 0x10000, 'size': 65536, 'filename': str(ram)})
            check_memory(ram.read_bytes(), (source / 'mbr-reserve.bin').read_bytes(),
                         manifest['memory']['mbr-reserve'], zero_bss=False)
            rows = [s.rstrip() for s in screen_rows(vga.read_bytes())]
            first = rows.index(TITLE)
            if rows[first:first + len(lines)] != lines or any(rows[first + len(lines):]):
                raise ValueError(f'{name}: unexpected VGA transcript: {rows[first:]}')
            if cut:
                proc.kill()    # abrupt QEMU exit, bypass guest shutdown and image close
            else:
                q.call('quit')
            status = proc.wait(timeout=5)
            if (cut and status == 0) or (not cut and status != 0):
                raise ValueError(f'{name}: emulator termination disagrees with test')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    if log.read_text().splitlines() != lines + (['~'] if cut_marker else []):
        raise ValueError(f'{name}: unexpected debug output')
    bus = trace.read_text()
    if trace_reads(bus) or 'ide_sector_write' in bus:
        raise ValueError(f'{name}: unexpected HDD I/O')
    spans = [(int(a), int(b)) for a, b in re.findall(r'blk_co_pwritev[^\n]*offset[ =]+(\d+)[, ]+bytes[ =]+(\d+)', bus)]
    if bus.count('blk_co_pwritev') != len(spans) or spans != [(lba * 512, 512) for lba in expected_writes]:
        raise ValueError(f'{name}: unexpected floppy writes: {bus[:1200]}, expected {expected_writes}')
    return dict(name=name, transcript=lines, cut=cut, fault_rom=bool(rom), hdd_reads=0, hdd_writes=0,
                floppy_write_lbas=expected_writes, vga_sha256=sha256(vga))


def campaign(exe, bios, source, out, manifest, temp):
    original = {'boot': (source / 'mbr-reserve.img').read_bytes(),
                'data': (source / 'mbr-reserve-data.img').read_bytes()}
    disks = {k: temp / (k + '.img') for k in original}
    states = [TITLE, INSERT, STAGED, RETURN]
    results = []
    def reset(point=f.CURRENT):
        disks['boot'].write_bytes(f.witness_floppy(original['boot'], point, W, C))
        data = bytearray(original['data'])
        f.stage(data, point, C)
        disks['data'].write_bytes(data)

    def step(name, lines, writes, *, partial=False, rom=None, cut=False, protect=None, return_disk=None):
        before = {k: p.read_bytes() for k, p in disks.items()}
        expected = {k: bytearray(v) for k, v in before.items()}
        for index, (k, lba, body) in enumerate(writes):
            if partial and index == len(writes) - 1:
                body = body[:128] + expected[k][lba*512+128:(lba+1)*512]
            f.put(expected[k], lba, body)
        result = boot(exe, bios, source, out, manifest, name, disks, lines, [lba for _, lba, _ in writes],
                      rom=rom, protect=protect, return_disk=return_disk, cut=cut)
        if any(disks[k].read_bytes() != expected[k] for k in disks):
            raise ValueError(f'{name}: unexpected persisted image bytes')
        result['before_sha256'] = {k: hashlib.sha256(v).hexdigest() for k, v in before.items()}
        result['after_sha256'] = {k: sha256(p) for k, p in disks.items()}
        results.append(result)
        print(name + ': ' + ('POWER CUT' if cut else lines[-1]), flush=True)

    def reserve(name, point):
        new, writes = plan(point)
        step(name, states + [f'RESERVED REVIEW {new.issued}', PASS], writes)
        return new

    reset()
    if any(disks[k].read_bytes() != original[k] for k in disks):
        raise ValueError('Regular test must start with exact distributed images')
    second = reserve('first', f.CURRENT)
    reserve('second-cold-boot', second)
    reset()
    step('power-off-at-exchange', states, plan(f.CURRENT)[1][:2], cut=True)
    second = reserve('exchange-retry', f.CURRENT)
    reserve('exchange-next', second)

    # Every cut or ambiguous completion is followed by a fresh unmodified BIOS
    # process using exactly the bytes left by its predecessor. A missing ticket
    # may cost one number. A torn witness must never select an older authority.
    new, writes = plan(f.CURRENT)
    for ordinal in range(1, 4):
        for mode, label in enumerate(('before', 'after', 'torn', 'lost', 'ambiguous'), 1):
            reset()
            name = f'{label}-write-{ordinal}'
            rom = fault_rom(source / 'int13-reserve.rom', temp / 'fault.rom', ordinal, mode)
            applied = ordinal - 1 if label in ('before', 'lost') else ordinal
            cut = mode <= 3
            prefix = states if ordinal == 3 else states[:2]
            step(name, prefix if cut else prefix + ['MEDIA CHECK FAILED', BLOCK], writes[:applied],
                 partial=label == 'torn', rom=rom, cut=cut)
            if ordinal == 3 and label == 'torn':
                step(name + '-cold', [TITLE, 'MEDIA CHECK FAILED', BLOCK], [])
            else:
                reserve(name + '-cold', new if ordinal == 3 and applied == 3 else f.CURRENT)

    reset()
    rom = fault_rom(source / 'int13-reserve.rom', temp / 'fault.rom', 3, 6)
    step('closing-witness-read', states + ['MEDIA CHECK FAILED', BLOCK], writes, rom=rom)
    reserve('closing-witness-read-cold', new)
    for medium in ('data', 'boot'):
        reset()
        end = medium == 'boot'
        step('protected-' + medium, (states if end else states[:2]) + ['MEDIA CHECK FAILED', BLOCK],
             writes[:2] if end else [], protect=medium)
    reset()
    disks['data'].write_bytes((source / 'mbr-restart-current.img').read_bytes())
    step('foreign-carrier', states[:2] + ['MEDIA CHECK FAILED', BLOCK], [])
    reset()
    disks['data'].write_bytes(f.carrier_images(C)['older'])
    step('stale-carrier', states[:2] + ['STALE CHECKPOINT', BLOCK], [])
    reset()
    foreign = temp / 'other-boot.img'
    changed = bytearray(original['boot'])
    f.put(changed, f.WITNESS_LBA + 2, f.sector_body(9))
    for name, image in [('stale-returned-witness', f.witness_floppy(original['boot'], f.EARLIER, W, C)),
                        ('equal-crc-returned-original', changed)]:
        reset()
        foreign.write_bytes(image)
        step(name, states + ['MEDIA CHECK FAILED', BLOCK], writes[:2], return_disk=foreign)
        if foreign.read_bytes() != image:
            raise ValueError('Returned foreign history was overwritten')
    for name, point in [('original-only', f.ORIGIN), ('preserve-predecessor', f.NEXT),
                        ('cross-16', f.Checkpoint(65535, 65535, 3)),
                        ('last-number', f.Checkpoint(0xfffffffe, 0xfffffffe, 3))]:
        reset(point)
        reserve(name, point)
    step('exhausted-cold', [TITLE, 'COUNTER EXHAUSTED', BLOCK], [])
    reset(f.Checkpoint(0xffffffff, 20, 3))
    step('generation-exhausted', [TITLE, 'COUNTER EXHAUSTED', BLOCK], [])
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--language', choices=LANGUAGES, default='en')
    p.add_argument('--qemu', default='qemu-system-i386')
    p.add_argument('--bios', type=Path)
    args = p.parse_args()
    exe = shutil.which(args.qemu)
    if not exe:
        raise ValueError('QEMU not found')
    exe = Path(exe).resolve()
    bios = (args.bios or exe.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    source = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-reservation-test-de' if args.language == 'de' else 'mbr-reservation-test')
    prepare_output(out)
    report = out / 'reservation-results.json'
    report.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-reserve.img', 'mbr-reserve-data.img', 'int13-reserve.rom'):
        if sha256(source / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed reservation fixture: ' + name)
    (out / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    with tempfile.TemporaryDirectory() as tmp:
        results = campaign(exe, bios, source, out, manifest, Path(tmp))
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(ui=manifest['ui'], build_inputs=manifest['build_inputs'], cases=results,
        qemu_sha256=sha256(exe), bios_sha256=sha256(bios)), indent=2) + '\n')


if __name__ == '__main__':
    main()
