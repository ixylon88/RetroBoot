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


def remove_failed_recovery(q, timeout):
    """At a QEMU disk-error stop, remove the secondary backing disk and resume the same guest."""
    deadline = time.monotonic() + timeout
    while q.call('query-status')['status'] != 'io-error':
        if time.monotonic() >= deadline:
            raise ValueError('Recovery disk never reached the selected I/O error')
        time.sleep(0.05)

    def inserted(blocks):
        return {d['device']: d['inserted']['node-name'] for d in blocks if 'inserted' in d}

    blocks = q.call('query-block')
    drives = inserted(blocks)
    node = drives.pop('recovery')
    failed = [d['device'] for d in blocks if d.get('io-status') == 'failed']
    if failed != ['recovery']:
        raise ValueError(f'Unexpected failed drives before removal: {failed}')
    stats = next(d['stats'] for d in q.call('query-blockstats') if d.get('device') == 'recovery')
    reply = q.call('human-monitor-command', {'command-line': 'drive_del recovery'})
    if (reply or inserted(q.call('query-block')) != drives
            or any(d['node-name'] == node for d in q.call('query-named-block-nodes'))):
        raise ValueError(f'Recovery backing disk was not removed: {reply}')
    q.call('cont')
    return stats


def boot_fixture(exe, bios, fixture, out, boot_disk, disk, name, lines, actions, write_lbas, reads,
                 *, rom=None, cut=False, readonly_start=False, ata_identity=None, disk_format='raw',
                 recovery_disk=None, recovery_identity=None, recovery_format='raw', recovery_writes=(),
                 io_check=None, timeout=15, remove_recovery=False):
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
    for channel, path, fmt, identity, node in ((0, disk, disk_format, ata_identity, 'rb'),
            (1, recovery_disk, recovery_format, recovery_identity, 'recovery')):
        if path is None:
            continue
        device = f'ide-hd,drive={node},bus=ide.{channel},unit=0,cyls=10,heads=16,secs=63,lcyls=10,lheads=16,lsecs=63'
        if identity is not None:
            model, serial = identity
            device += ',model=' + model.replace(',', ',,') + ',serial=' + serial.replace(',', ',,')
        policy = ',rerror=stop,werror=stop' if remove_recovery and node == 'recovery' else ''
        args += ['-drive', f'file={path},format={fmt},if=none,id={node}{policy}', '-device', device]
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
            removed = remove_failed_recovery(q, timeout) if remove_recovery else None
            wait_marker(proc, log, marker + '\n', timeout=timeout, encoding='cp437')
            ram, vga = out / (name + '-ram.bin'), out / (name + '-vga.bin')
            stop_at_transcript(q, vga, lines, name)
            q.call('pmemsave', {'val': 0x10000, 'size': 65536, 'filename': str(ram)})
            check_memory(ram.read_bytes(), fixture['binary'], fixture['memory'], zero_bss=False)
            if recovery_disk is not None or io_check:
                devices = {d['device']: d['stats'] for d in q.call('query-blockstats') if d.get('device')}
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
    all_reads = trace_reads(bus)
    result = dict(name=name, transcript=lines, hdd_read_lbas=reads, power_cut=cut, vga_sha256=sha256(vga))
    if removed is not None:
        devices['recovery'] = removed
        result['writes_completed_before_removal'] = removed['wr_bytes'] // 512
    if io_check:
        result.update(io_check(bus, devices))
        return result
    if recovery_disk is None:
        if all_reads != reads or 'ide_sector_write' in bus:
            raise ValueError(f'{name}: unexpected HDD I/O {all_reads}')
        result['floppy_write_lbas'] = write_lbas
    else:
        source = devices.get('rb', {'rd_bytes': 0, 'wr_bytes': 0})
        backup = devices['recovery']
        if (source['rd_bytes'] != len(reads) * 512 or source['wr_bytes'] or any(reads)
                or backup['rd_bytes'] != (len(all_reads) - len(reads)) * 512 or any(n > 6 for n in all_reads)
                or backup['wr_bytes'] != len(recovery_writes) * 512):
            raise ValueError(f'{name}: unexpected per-drive physical I/O')
        transfers = re.findall(r'ide_sector_write sector=(\d+) nsectors=(\d+)', bus)
        commands = re.findall(r'ide_bus_exec_cmd[^\n]*state (0x[0-9a-f]+); cmd (0x30|0xe7)\b', bus)
        if ([(int(l), int(n)) for l, n in transfers] != [(l, 1) for l in recovery_writes]
                or [op for _, op in commands] != ['0x30', '0xe7'] * len(recovery_writes)
                or len({state for state, _ in commands}) > 1):
            raise ValueError(f'{name}: unexpected recovery writes or cache flushes')
        result.update(ide_read_lbas=all_reads, recovery_read_sectors=backup['rd_bytes']//512,
                      recovery_write_lbas=list(recovery_writes), floppy_write_lbas=[n for n in write_lbas if n > 6])
    spans = re.findall(r'blk_co_pwritev[^\n]*offset[ =]+(\d+)[, ]+bytes[ =]+(\d+)', bus)
    if bus.count('blk_co_pwritev') != len(spans) or [(int(a), int(b)) for a, b in spans] != [
            (n * 512, 512) for n in write_lbas]:
        raise ValueError(f'{name}: unexpected physical writes {spans}')
    return result
