"""Publish a live BIOS metadata backup, then cold boot without the source disk."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import zlib

from backup_verify_vectors import alternatives, record, wire
from build_hdd import write_fixture
from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import CARRIER, ORIGIN, TARGET, WITNESS, Checkpoint, put
from prepare_mbr_target import WITNESS_START, prepare_pair, sealed
from rescue_plan_fixtures import disk
from rescue_text import load_catalog, output_name

MODEL = 'VBOX HARDDISK'
SOURCE = 'VB73737373-11111111'
RECOVERY = 'VB74747474-22222222'
CAPACITY = 10080
DATA = 16
PASS = 'RB BACKUP DISK PASS'
BLOCK = 'RB BACKUP DISK BLOCKED'


def provision(template, capacity=2048):
    """New owned fixture. Independent witness and carrier start with approved revision 2."""
    data = wire()
    disk_bytes, _ = disk()
    count = disk_bytes // 512
    boot, label = prepare_pair(template, MODEL, SOURCE, count, TARGET, CARRIER, WITNESS,
                               recovery=(MODEL, RECOVERY, CAPACITY))
    start = bytearray(boot)
    recovery = bytearray(CAPACITY * 512)
    put(recovery, 0, label)
    original, approved = data[5*512:6*512], data[6*512:7*512]
    point = Checkpoint(3, 2, 2)
    for index, block in enumerate((record(b'RBWIT001', point, count, original, approved), original, approved)):
        put(start, WITNESS_START//512 + index + 1, block)
    for index, block in enumerate((record(b'RBORG001', ORIGIN, count, original, approved), original,
                                   record(b'RBCMT001', point, count, original, approved), approved)):
        put(recovery, index + 1, block)
    put(recovery, 7, sealed(b'RBSTORE1' + TARGET + CARRIER + WITNESS + struct.pack('<I', capacity)))
    return bytes(start), bytes(recovery)


def commit(data):
    digest = [0, 0]
    for pos in range(len(data)//512):
        block = data[pos*512:(pos+1)*512]
        for i, section in enumerate((block[:508], block[508:])):
            digest[i] = zlib.crc32(struct.pack('<III', digest[i], pos, zlib.crc32(section)))
    return sealed(b'RBDONE01' + TARGET + CARRIER + WITNESS + struct.pack('<5I', len(data)//512, 3, 2, *digest))


def expected_recovery(blank, data, published=False):
    result = bytearray(blank)
    result[DATA*512:DATA*512+len(data)] = data
    if published:
        put(result, 8, commit(data))
    return bytes(result)


def boot_case(exe, bios, src, work, start, source, recovery, ui, name, key, lines,
              *, expected_writes=(), source_serial=SOURCE, recovery_serial=RECOVERY,
              failed_write=False, input_format='raw', recovery_format='raw',
              remove_recovery=False):
    manifest = json.loads((src / 'manifest.json').read_bytes())
    binary = (src / 'backup-disk.bin').read_bytes()
    fixture = dict(binary=binary, memory=manifest['memory']['backup-disk'])
    menu = ['RB BACKUP DISK', ui['STORE_MENU']]
    def check_io(bus, stats):
        source_io = stats.get('rb', {})
        rec = stats.get('recovery', {})
        if source_io.get('wr_bytes', 0) or stats['floppy']['wr_bytes']:
            raise ValueError(f'{name}: wrote outside the recovery disk')
        transfers = [(int(l), int(n)) for l, n in re.findall(r'ide_sector_write sector=(\d+) nsectors=(\d+)', bus)]
        commands = re.findall(r'ide_bus_exec_cmd[^\n]*state (0x[0-9a-f]+); cmd (0x30|0xe7)\b', bus)
        expected = ['0x30', '0xe7'] * len(expected_writes)
        if failed_write:
            expected = expected[:-1]
        writes = [(n, 1) for n in expected_writes]
        if remove_recovery and failed_write:
            # On resume QEMU retries the interrupted transfer to the now-empty backend.
            # The guest issued only one command for this LBA and never flushed it.
            writes.append(writes[-1])
        if (transfers != writes or [c for _, c in commands] != expected
                or len({dev for dev, _ in commands}) > 1):
            raise ValueError(f'{name}: unexpected IDE writes or flushes {transfers} {commands[-4:]}')
        if remove_recovery and rec['wr_bytes'] != expected.count('0xe7') * 512:
            raise ValueError(f'{name}: unexpected number of completed bytes at removal')
        if key != 's' and source_io.get('rd_bytes', 0):
            raise ValueError(f'{name}: read the system disk during verification')
        return dict(source_read_sectors=source_io.get('rd_bytes', 0)//512,
                    recovery_read_sectors=rec.get('rd_bytes', 0)//512,
                    recovery_write_lbas=list(expected_writes), flush_commands=expected.count('0xe7'))

    return boot_fixture(exe, bios, fixture, work, start, source, name, menu + lines,
                        [(ui['STORE_MENU'], key, None, False)], [], [], readonly_start=True,
                        ata_identity=(MODEL, source_serial), disk_format=input_format,
                        recovery_disk=recovery, recovery_identity=(MODEL, recovery_serial),
                        recovery_format=recovery_format, io_check=check_io, timeout=100, remove_recovery=remove_recovery)


def campaign(exe, bios, src, work, out, language):
    ui = load_catalog(language)
    start, system, rec = (work / n for n in ('backup-disk.img', 'system.raw', 'recovery.raw'))
    base, blank = provision((src / start.name).read_bytes())
    start.write_bytes(base)
    write_fixture(system, *disk())
    before = sha256(system)
    data = wire()
    size = len(data)//512
    lbas = list(range(DATA, DATA+size))
    full = expected_recovery(blank, data, True)
    count = [ui['VERIFY_COUNT'] + str(size), ui['STORE_REV'] + '2', PASS]
    cases = []

    def run(name, key, lines, initial, expected=None, *, source=system, path=None, **options):
        if initial is None:  # restart with the same backing file, byte for byte as left by the guest
            initial = rec.read_bytes()
        else:
            rec.write_bytes(initial)
        result = boot_case(exe, bios, src, work, start, source, rec if path is None else path,
                           ui, name, key, lines, **options)
        observed = rec.read_bytes()
        if observed != (initial if expected is None else expected) or start.read_bytes() != base or sha256(system) != before:
            raise ValueError(f'{name}: unexpected persistent bytes')
        cases.append(result)
        print(f'{name}: {lines[-1]}', flush=True)
        return observed

    verify = [ui['STORE_VERIFY'], ui['STORE_READ'], *count]
    save = [ui['STORE_SAVE'], ui['STORE_DONE'], *count]
    empty = [ui['STORE_EMPTY'], BLOCK]
    failure = [ui['STORE_SAVE'], ui['STORE_FAILED'], BLOCK]
    invalid = [ui['STORE_VERIFY'], ui['STORE_FAILED'], BLOCK]
    run('empty-restart', 'v', empty, blank, source=None)
    run('cancel', 'esc', [ui['STORE_CANCEL'], PASS], blank)
    run('foreign-recovery', 's', [ui['STORE_MEDIA'], BLOCK], blank, recovery_serial=SOURCE)
    run('missing-source', 's', [ui['STORE_SAVE'], ui['STORE_SOURCE'], ui['STORE_FAILED'], BLOCK], blank, source=None)
    run('foreign-source', 's', [ui['STORE_SAVE'], ui['STORE_SOURCE'], ui['STORE_FAILED'], BLOCK],
        blank, source_serial=RECOVERY)
    _, small = provision((src / start.name).read_bytes(), size - 1)
    run('too-small', 's', [ui['STORE_SAVE'], ui['STORE_MEDIA'], ui['STORE_FAILED'], BLOCK], small)
    broken = bytearray(blank)
    put(broken, 7, bytes(512))
    run('unprovisioned', 's', [ui['STORE_MEDIA'], BLOCK], broken)
    no_disk = boot_case(exe, bios, src, work, start, None, None, ui, 'missing-recovery', 'v', [ui['STORE_MEDIA'], BLOCK])
    cases.append(no_disk)

    def fault(event, sector=None):
        conf = work / 'fault.conf'
        operation = {'write_aio': 'write', 'read_aio': 'read', 'flush_to_disk': 'flush'}[event]
        rule = f'[inject-error]\nevent = "{event}"\niotype = "{operation}"\nerrno = "5"\nonce = "on"\n'
        if sector is not None:
            rule += f'sector = "{sector}"\n'
        conf.write_text(rule)
        return f'blkdebug:{conf}:{rec}'

    staged = expected_recovery(blank, data)
    run('last-write-error', 's', failure, blank, expected_recovery(blank, data[:-512]), path=fault('write_aio', lbas[-1]),
        expected_writes=lbas, failed_write=True)
    run('last-provisional-read-error', 's', failure, blank, staged, path=fault('read_aio', lbas[-1]),
        expected_writes=lbas)
    run('flush-error', 's', failure, blank, expected_recovery(blank, data[:512]), path=fault('flush_to_disk'),
        expected_writes=lbas[:1])
    unpublished = run('commit-write-error', 's', failure, blank, staged, path=fault('write_aio', 8),
                      expected_writes=lbas+[8], failed_write=True)
    run('unpublished-restart', 'v', empty, unpublished, source=None)
    published = run('retry-and-publish', 's', save, unpublished, full, expected_writes=lbas+[8])
    run('cold-without-source', 'v', verify, published, source=None)
    run('last-read-error', 'v', invalid, published, source=None, path=fault('read_aio', lbas[-1]))
    # Each restart below reopens the same file left on disk by the preceding boot.
    partial = expected_recovery(blank, data[:7 * 512])
    run('remove-during-write', 's', failure, blank, partial, path=fault('write_aio', lbas[7]),
        expected_writes=lbas[:8], failed_write=True, remove_recovery=True)
    run('reconnect-partial', 'v', empty, None, source=None)
    run('remove-before-publication', 's', failure, None, staged, path=fault('write_aio', 8),
        expected_writes=lbas + [8], failed_write=True, remove_recovery=True)
    run('reconnect-unpublished', 'v', empty, None, source=None)
    run('publish-after-reconnection', 's', save, None, full, expected_writes=lbas + [8])
    run('remove-during-cold-read', 'v', invalid, None, source=None, path=fault('read_aio', lbas[-1]),
        remove_recovery=True)
    run('reconnect-published', 'v', verify, None, source=None)
    run('occupied', 's', [ui['STORE_USED'], BLOCK], published)
    damaged = bytearray(full)
    damaged[(DATA+size)*512-1] ^= 1
    run('damaged-last-sector', 'v', invalid, damaged, source=None)
    replacement = alternatives(data)['sub_approved']
    run('substituted-approval', 'v', invalid, expected_recovery(blank, replacement, True), source=None)
    damaged = bytearray(full)
    damaged[8*512+507] ^= 1
    run('torn-publication', 'v', invalid, damaged, source=None)
    run('copied-recovery', 'v', [ui['STORE_MEDIA'], BLOCK], full, source=None, recovery_serial=SOURCE)
    (out / 'verified.rbb').write_bytes(published[DATA*512:(DATA+size)*512])
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=('de', 'en'), default='en')
    args = parser.parse_args()
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    src = ROOT / 'build' / output_name('rescue', args.language)
    manifest = json.loads((src / 'manifest.json').read_bytes())
    check_build_inputs(manifest, ROOT)
    for name in ('backup-disk.img', 'backup-disk.bin'):
        if sha256(src/name) != manifest['artifacts'][name]['sha256']:
            raise ValueError(f'Changed backup build: {name}')
    out = ROOT / 'build' / ('backup-disk-test-' + args.language)
    prepare_output(out)
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        work = Path(tmp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\n')
        try:
            cases = campaign(exe, bios, src, work, out, args.language)
        except Exception:
            for log in work.glob('*.log'):
                shutil.copyfile(log, out/log.name)
            raise
    result = dict(cases=cases, file_sha256=sha256(out/'verified.rbb'), build_inputs=manifest['build_inputs'],
                  ui=manifest['ui'], bios_sha256=sha256(bios), qemu_sha256=sha256(exe))
    (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
