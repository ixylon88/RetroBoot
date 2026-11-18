"""Cold-boot the witness, exchange A:, and verify the independent recovery read."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zlib

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


TITLE = 'RB MBR RESTART'
PROMPT = 'INSERT RECOVERY FLOPPY AND PRESS ENTER'
WITNESS = [0, 1, 2] * 2
EVEN = [0, 1, 4, 5] * 2
ODD = [0, 1, 2, 3] * 2


def fixture_cases(boot, current, older):
    """Expected messages and read order are specified independently of the guest."""
    def edit(image, sector, offset, replacement, reseal=False):
        image = bytearray(image)
        base = sector * 512
        image[base + offset:base + offset + len(replacement)] = replacement
        if reseal:
            f.put(image, sector, f.seal(image[base:base + 512]))
        return bytes(image)

    def passed(issued, approved):
        role = f'APPROVED REV {approved}' if approved else 'APPROVED NONE'
        return ('ORIGINAL REV 1', role, f'LAST ISSUED {issued}', 'PENDING NONE', 'RB MBR RESTART PASS')

    def blocked(reason):
        return (reason, 'RB MBR RESTART BLOCKED')

    staged = f.carrier_images()['staged']
    new_boot = f.witness_floppy(boot, f.NEXT)
    ok = passed(5, 3)
    stale = blocked('STALE CHECKPOINT')
    changed = blocked('EVIDENCE CHANGED')
    binding = blocked('WRONG ENDPOINT')
    form = blocked('INVALID RECORD')
    yield 'current', boot, current, ok, WITNESS, EVEN
    yield 'bare-current', boot, current, ok, WITNESS, EVEN
    yield 'older', boot, older, stale, WITNESS, EVEN[:3]
    yield 'bare-older', boot, older, stale, WITNESS, EVEN[:3]
    yield 'replayed-issued', boot, edit(current, 5, 52, struct.pack('<I', 3), True), stale, WITNESS, EVEN[:3]
    yield 'earlier-authority', f.witness_floppy(boot, f.EARLIER), older, passed(3, 3), WITNESS, EVEN
    yield 'staged', boot, staged, ok, WITNESS, EVEN
    yield 'torn-inactive', boot, edit(staged, 3, 0, b'!'), ok, WITNESS, EVEN
    yield 'published', new_boot, staged, passed(5, 5), WITNESS, ODD
    yield 'missing-publication', new_boot, current, stale, WITNESS, ODD[:3]
    yield 'torn-active', new_boot, edit(staged, 3, 508, bytes(4)), blocked('INVALID CRC'), WITNESS, ODD[:3]
    yield 'wrong-parent', new_boot, edit(staged, 3, 60, bytes(4), True), stale, WITNESS, ODD[:3]
    yield 'old-active-payload', new_boot, edit(staged, 4, 0, f.sector_body(3)), changed, WITNESS, ODD[:4]
    yield 'wrong-carrier', boot, edit(current, 0, 0, f.label(f.WITNESS)), binding, WITNESS, EVEN[:1]
    yield 'wrong-target', boot, edit(current, 1, 8, b'X', True), binding, WITNESS, EVEN[:1]
    yield 'wrong-capacity', boot, edit(current, 5, 28, bytes(4), True), binding, WITNESS, EVEN[:3]
    yield 'resealed-original', boot, edit(current, 2, 0, f.sector_body(9)), changed, WITNESS, EVEN[:2]
    yield 'resealed-approved', boot, edit(current, 6, 0, f.sector_body(9)), changed, WITNESS, EVEN[:4]
    yield 'original-only', f.witness_floppy(boot, f.ORIGIN), f.carrier_images()['original-only'], passed(1, 0), WITNESS, ODD
    for name, point in [('cross-16-bit', f.Checkpoint(65536, 65535, 3)),
                        ('exhausted', f.Checkpoint(0xffffffff, 0xffffffff, 3))]:
        carrier = bytearray(current)
        f.stage(carrier, point)
        yield name, f.witness_floppy(boot, point), bytes(carrier), passed(point.issued, 3), WITNESS, (
            ODD if point.generation % 2 else EVEN)
    wh = f.WITNESS_LBA + 1
    yield 'missing-witness', edit(boot, wh, 0, bytes(512)), None, form, WITNESS[:1], []
    yield 'wrong-witness-endpoint', edit(boot, wh - 1, 0, f.label(f.CARRIER)), None, binding, WITNESS[:1], []
    yield 'future-approval', edit(boot, wh, 56, struct.pack('<I', 6), True), None, form, WITNESS[:1], []
    yield 'reserved-header', edit(boot, wh, 72, b'X', True), None, form, WITNESS[:1], []
    managed = edit(boot, wh + 1, 432, b'RBM1')
    crc = zlib.crc32(managed[(wh + 1) * 512:(wh + 2) * 512])
    yield 'installed-original', edit(managed, wh, 64, struct.pack('<I', crc), True), None, form, WITNESS[:2], []


def physical(base, records):
    return [lba for n in records for lba in (base, base + 1 + n, base)]


def boot_case(exe, bios, source, out, name, boot, carrier, lines, witness_reads, carrier_reads, memory):
    log, trace = out / (name + '.log'), out / (name + '.trace')
    log.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    bare = name.startswith('bare-')
    args = [exe, '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
            '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'a', '-display', 'none',
            '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot', '-qmp', 'stdio',
            '-global', 'isa-debugcon.iobase=0xe9', '-debugcon', 'file:' + str(log),
            '-drive', f'if=floppy,id=floppy,format=raw,readonly=on,file={boot}',
            '-trace', f'events={out / "events.txt"},file={trace}']
    if not bare:
        args += ['-option-rom', str(source / 'int13-0.rom')]
    with (out / (name + '-stderr.log')).open('w') as err, subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1) as proc:
        try:
            q = Qmp(proc)
            expected = [TITLE]
            if carrier:
                wait_marker(proc, log, PROMPT + '\n')
                expected += ['WITNESS READY', PROMPT]
                q.call('blockdev-change-medium', {'device': 'floppy', 'filename': str(carrier),
                       'format': 'raw', 'read-only-mode': 'read-only'})
                q.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 30})
            expected.extend(lines)
            wait_marker(proc, log, lines[-1] + '\n')
            q.call('stop')
            ram, vga = out / (name + '-ram.bin'), out / (name + '-vga.bin')
            q.call('pmemsave', {'val': 0x10000, 'size': 65536, 'filename': str(ram)})
            q.call('pmemsave', {'val': 0xb8000, 'size': 4000, 'filename': str(vga)})
            check_memory(ram.read_bytes(), (source / 'mbr-restart.bin').read_bytes(), memory, zero_bss=False)
            rows = [row.rstrip() for row in screen_rows(vga.read_bytes())]
            first = rows.index(TITLE) if TITLE in rows else len(rows)
            if rows[first:first + len(expected)] != expected or any(rows[first + len(expected):]):
                raise ValueError(f'{name}: incorrect VGA transcript')
            q.call('quit')
            if proc.wait(timeout=5):
                raise ValueError(f'{name}: emulator reported failure')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    expected_io = physical(f.WITNESS_LBA, witness_reads) + physical(0, carrier_reads)
    debug = log.read_text().splitlines()
    reads = [int(row[1:], 16) for row in debug if re.fullmatch(r'%[0-9A-F]{4}', row)]
    if ([row for row in debug if not re.fullmatch(r'%[0-9A-F]{4}', row)] != expected
            or reads != ([] if bare else expected_io)):
        raise ValueError(f'{name}: incorrect debug transcript or physical sector order')
    trace_text = trace.read_text()
    if trace_reads(trace_text) or 'ide_sector_write' in trace_text or 'blk_co_pwritev' in trace_text:
        raise ValueError(f'{name}: unexpected HDD read or guest write')
    return dict(name=name, bare=bare, transcript=expected, floppy_lbas=reads, block_writes=0,
                hdd_reads=0, vga_sha256=sha256(vga))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--language', choices=LANGUAGES, default='en')
    p.add_argument('--qemu', default='qemu-system-i386')
    p.add_argument('--bios', type=Path)
    p.add_argument('--case', action='append')
    args = p.parse_args()
    binary = shutil.which(args.qemu)
    if not binary:
        raise ValueError('QEMU not found')
    exe = Path(binary).resolve()
    bios = (args.bios or exe.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    source = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-restart-test-de' if args.language == 'de' else 'mbr-restart-test')
    prepare_output(out)
    report = out / 'restart-results.json'
    report.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    (out / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    paths = [source / ('mbr-restart' + s + '.img') for s in ('', '-current', '-older')]
    hashes = {p.name: sha256(p) for p in paths}
    if any(hashes[p.name] != manifest['artifacts'][p.name]['sha256'] for p in paths):
        raise ValueError('Changed distributed restart image')
    results = []
    trusted, current, older = (p.read_bytes() for p in paths)
    with tempfile.TemporaryDirectory() as tmp:
        for name, boot, carrier, lines, wr, cr in fixture_cases(trusted, current, older):
            if args.case and name not in args.case:
                continue
            a, b = paths[0], None
            if boot != trusted:
                a = Path(tmp) / 'boot.img'
                a.write_bytes(boot)
            if carrier == current:
                b = paths[1]
            elif carrier == older:
                b = paths[2]
            elif carrier is not None:
                b = Path(tmp) / 'carrier.img'
                b.write_bytes(carrier)
            result = boot_case(exe, bios, source, out, name, a, b,
                               lines, wr, cr, manifest['memory']['mbr-restart'])
            if a.read_bytes() != boot or (carrier is not None and b.read_bytes() != carrier):
                raise ValueError(f'{name}: test medium changed')
            result['source_unchanged'] = True
            results.append(result)
            print(f'{name}: {lines[-1]}', flush=True)
    if args.case and set(args.case) != {r['name'] for r in results}:
        raise ValueError('Unknown restart test case')
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(ui=manifest['ui'], build_inputs=manifest['build_inputs'],
        cases=results, media_sha256=hashes, qemu_sha256=sha256(exe), bios_sha256=sha256(bios)),
        indent=2) + '\n')


if __name__ == '__main__':
    main()
