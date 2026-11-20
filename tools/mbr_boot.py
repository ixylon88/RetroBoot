"""Shared SeaBIOS boot harness for original-MBR and first-witness tests."""
from collections import Counter
import re
import subprocess
import time

from build_rescue import sha256
from test_menu import Qmp, screen_rows, wait_marker
from test_rescue import check_memory, trace_reads


def stop_at_transcript(q, vga, lines, name):
    # The debug port receives the final newline before INT 10h finishes scrolling.
    visible = lines[-24:]
    deadline = time.monotonic() + 3
    while True:
        q.call('stop')
        q.call('pmemsave', {'val': 0xb8000, 'size': 4000, 'filename': str(vga)})
        rows = [row.rstrip() for row in screen_rows(vga.read_bytes())]
        start = 0 if len(lines) > 24 else next((i for i, row in enumerate(rows) if row == visible[0]), len(rows))
        if rows[start:start + len(visible)] == visible and not any(rows[start + len(visible):]):
            return
        if time.monotonic() >= deadline:
            raise ValueError(f'{name}: unexpected VGA transcript')
        q.call('cont')
        time.sleep(0.01)


def boot_fixture(exe, bios, fixture, out, boot_disk, disk, name, lines, actions, write_lbas, reads,
                 *, rom=None, cut=False, readonly_start=False, ata_identity=None, disk_format='raw'):
    """Run ordered keyboard/media exchanges and verify VGA, memory and physical disk I/O."""
    log = out / (name + '.log')
    trace = out / (name + '.trace')
    log.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    access = 'readonly=on' if readonly_start else 'cache=writethrough'
    args = [str(exe), '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
            '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-boot', 'a', '-display', 'none',
            '-monitor', 'none', '-serial', 'none', '-nic', 'none', '-no-reboot', '-qmp', 'stdio',
            '-global', 'isa-debugcon.iobase=0xe9', '-debugcon', 'file:' + str(log),
            '-drive', f'if=floppy,id=floppy,format=raw,{access},file={boot_disk}',
            '-trace', f'events={out / "events.txt"},file={trace}']
    if disk is not None:
        device = 'ide-hd,drive=rb,bus=ide.0,unit=0,cyls=10,heads=16,secs=63,lcyls=10,lheads=16,lsecs=63'
        if ata_identity is not None:
            model, serial = ata_identity
            device += ',model=' + model.replace(',', ',,') + ',serial=' + serial.replace(',', ',,')
        args += ['-drive', f'file={disk},format={disk_format},if=none,id=rb', '-device', device]
    if rom:
        args += ['-option-rom', str(rom)]

    marker = '~' if cut else lines[-1]
    with (out / (name + '-stderr.log')).open('w') as err, subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1) as proc:
        try:
            q = Qmp(proc)
            visits = Counter()
            for prompt, key, medium, readonly in actions:
                visits[prompt] += 1
                wait_marker(proc, log, prompt + '\n', encoding='cp437', occurrence=visits[prompt])
                if medium is not None:
                    q.call('blockdev-change-medium', {'device': 'floppy', 'filename': str(medium), 'format': 'raw',
                           'read-only-mode': 'read-only' if readonly else 'read-write'})
                q.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
            wait_marker(proc, log, marker + '\n', encoding='cp437')
            ram, vga = out / (name + '-ram.bin'), out / (name + '-vga.bin')
            stop_at_transcript(q, vga, lines, name)
            q.call('pmemsave', {'val': 0x10000, 'size': 65536, 'filename': str(ram)})
            check_memory(ram.read_bytes(), fixture['binary'], fixture['memory'], zero_bss=False)
            if cut:
                proc.kill()
            else:
                q.call('quit')
            code = proc.wait(timeout=5)
            if (code != 0) != cut:
                raise ValueError(f'{name}: unexpected QEMU exit {code}')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    actual = [s for s in log.read_text(encoding='cp437').splitlines() if not re.fullmatch('@[0-9A-F]{2}', s)]
    if actual != lines + (['~'] if cut else []):
        raise ValueError(f'{name}: unexpected debug transcript {actual}')
    bus = trace.read_text()
    if trace_reads(bus) != reads or 'ide_sector_write' in bus:
        raise ValueError(f'{name}: unexpected HDD I/O {trace_reads(bus)}')
    spans = re.findall(r'blk_co_pwritev[^\n]*offset[ =]+(\d+)[, ]+bytes[ =]+(\d+)', bus)
    if bus.count('blk_co_pwritev') != len(spans) or [(int(a), int(b)) for a, b in spans] != [
            (n * 512, 512) for n in write_lbas]:
        raise ValueError(f'{name}: unexpected physical writes {spans}')
    return dict(name=name, transcript=lines, hdd_read_lbas=reads, floppy_write_lbas=write_lbas,
                power_cut=cut, vga_sha256=sha256(vga))
