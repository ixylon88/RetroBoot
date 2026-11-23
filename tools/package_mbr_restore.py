"""Boot, damage and repair an owned MBR fixture; package the tested VirtualBox media."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from build_hdd import write_fixture
from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from package_backup_disk import make_vdi
from package_backup_handoff import START, expected_file, history_boot
from package_mbr_recovery import LANGS
from prepare_mbr_target import STORE_DATA, WITNESS_START, prepare_pair
from rescue_plan_fixtures import disk
from rescue_text import load_catalog
from test_backup_disk import (CAPACITY, PASS as STORE_PASS, RECOVERY as OTHER_BACKUP,
                              SOURCE as OTHER_SOURCE, boot_case, commit, expected_recovery, provision, wire)
from test_mbr_target import MODEL

FLOPPY = 'mbr-restore.img'
SYSTEM, RECOVERY = 'RB46-System.vdi', 'RB46-Sicherung.vdi'
PRIMARY, SECONDARY = 'VB46460101-11111111', 'VB46460202-22222222'
IDS = tuple(b'RB46-TEST-PAIR-' + bytes([i]) for i in (1, 2, 3))
KIT = 'RetroBoot-Startcode-Reparatur.zip'
CODE = 432
PASS, BLOCK = 'RB MBR RESTORE PASS', 'RB MBR RESTORE BLOCKED'


def checked_build(directory, program='mbr-restore'):
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    check_build_inputs(manifest, ROOT)
    for name in (START, program + '.img', program + '.bin', 'mbr-target.bin', 'backup-disk.bin', 'restore-stage1.bin'):
        if sha256(directory / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError(f'Build artifact changed: {name}')
    return manifest


def write_at(path, offset, data):
    with path.open('r+b') as out:
        out.seek(offset)
        out.write(data)


def capture_and_publish(exe, bios, src, work, source, carrier, size, extents, approved, *,
                        primary=PRIMARY, secondary=SECONDARY, ids=IDS):
    """Use the guest's capture, approval and publication paths before injecting damage."""
    count = size // 512
    start = work / START
    template, prefix = prepare_pair((src / START).read_bytes(), MODEL, primary, count, *ids,
                                    recovery=(MODEL, secondary, CAPACITY))
    start.write_bytes(template)
    blank = prefix.ljust(CAPACITY * 512, b'\0')
    carrier.write_bytes(blank)
    original = approved[:432] + bytes(4) + approved[436:]
    write_fixture(source, size, {**extents, 0: original})
    ui = load_catalog('en')
    args = exe, bios, src, work, start, source, carrier, ui
    serials = dict(source_serial=primary, recovery_serial=secondary)
    expected, first = history_boot(*args, 'restore-capture', original, approved, count, blank, ids,
                                   capture=True, **serials)
    if carrier.read_bytes() != expected:
        raise ValueError('Original capture differs from the expected carrier')
    stale_witness = start.read_bytes()[WITNESS_START:]
    write_at(source, 0, approved)
    expected, review = history_boot(*args, 'restore-approve', original, approved, count, expected, ids, **serials)
    if carrier.read_bytes() != expected:
        raise ValueError('Approval differs from the expected carrier')
    witness = start.read_bytes()[WITNESS_START:]
    data = expected_file(original, approved)
    sectors = len(data) // 512
    record = commit(data, ids)
    published = bytearray(expected)
    published[8 * 512:9 * 512] = record
    published[STORE_DATA * 512:STORE_DATA * 512 + len(data)] = data
    lines = [ui['STORE_SAVE'], ui['STORE_DONE'], ui['VERIFY_COUNT'] + str(sectors), ui['STORE_REV'] + '2', STORE_PASS]
    save = boot_case(*args, 'restore-publish', 's', lines, combined=True,
                     expected_writes=[*range(STORE_DATA, STORE_DATA + sectors), 8], **serials)
    if carrier.read_bytes() != published or start.read_bytes()[WITNESS_START:] != witness:
        raise ValueError('Publication differs from the expected bytes')
    return witness, stale_witness, [first, review, save]


def primary_write_check(name, lba, writes, stored):
    """Verify the exact ATA commands, physical LBA and per-device write counts."""
    def check_io(trace, devices):
        commands = re.findall(r'ide_bus_exec_cmd[^\n]*state (0x[0-9a-f]+); cmd (0x30|0xe7)\b', trace)
        transfers = re.findall(r'ide_sector_write sector=(\d+) nsectors=(\d+)', trace)
        if (devices['floppy']['wr_bytes'] or devices.get('recovery', {}).get('wr_bytes', 0)
                or devices.get('rb', {}).get('wr_bytes', 0) != stored
                or [op for _, op in commands] != list(writes) or len({dev for dev, _ in commands}) > 1
                or transfers != [(str(lba), '1')] * writes.count('0x30')):
            raise ValueError(f'{name}: unexpected disk writes {transfers}, commands {commands}')
        return dict(source_write_lbas=[lba] * len(transfers), source_written_bytes=stored,
                    flush_commands=writes.count('0xe7'))

    return check_io


def restore_boot(exe, bios, src, manifest, work, start, system, recovery, ui, name, outcome, *,
                 key=None, change_floppy=None, before_key=None, fmt='raw', serial=PRIMARY,
                 recovery_serial=SECONDARY, writes=(), stored=0):
    lines = ['RB MBR RESTORE', ui['RESTORE_CHECK']]
    keys = []
    if key is not None:
        lines += [ui['D_SERIAL'] + ' ' + PRIMARY, ui['STORE_REV'] + '2', ui['RESTORE_SCOPE'],
                  ui['RESTORE_KEEP'], ui['RESTORE_CONFIRM']]
        keys.append((ui['RESTORE_CONFIRM'], key, change_floppy, True))
    lines += [ui[outcome], PASS if outcome in ('RESTORE_CANCEL', 'RESTORE_DONE', 'RESTORE_INTACT') else BLOCK]

    fixture = dict(binary=(src / 'mbr-restore.bin').read_bytes(), memory=manifest['memory']['mbr-restore'])
    return boot_fixture(exe, bios, fixture, work, start, system, name, lines, keys, [], [], readonly_start=True,
                        ata_identity=(MODEL, serial), disk_format=fmt, recovery_disk=recovery, recovery_format=fmt,
                        recovery_identity=(MODEL, recovery_serial), io_check=primary_write_check(name, 0, writes, stored),
                        before_key=before_key, timeout=90)


def qualify_kit(exe, bios, work, bundle, fixed, damaged):
    cases = []
    for lang, suffix, folder in LANGS:
        src = ROOT / 'build' / ('rescue' + suffix)
        manifest = checked_build(src)
        dest = work / lang
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(dest)
        floppy, system, recovery = dest / folder / FLOPPY, dest / SYSTEM, dest / RECOVERY
        media = sha256(floppy), sha256(recovery)
        ui = load_catalog(lang)
        args = exe, bios, src, manifest, work, floppy, system, recovery, ui
        cases.append(restore_boot(*args, lang + '-cancel', 'RESTORE_CANCEL', key='esc', fmt='vdi'))
        compare_image(damaged, system)
        cases.append(restore_boot(*args, lang + '-repair', 'RESTORE_DONE', key=ui['A_YES'].lower(),
                                  fmt='vdi', writes=('0x30', '0xe7'), stored=512))
        compare_image(fixed, system)
        cases.append(restore_boot(*args, lang + '-restart', 'RESTORE_INTACT', fmt='vdi'))
        compare_image(fixed, system)
        if media != (sha256(floppy), sha256(recovery)):
            raise ValueError(f'{lang}: external media changed')
    return cases


def compare_image(raw, vdi):
    subprocess.run(['qemu-img', 'compare', '-f', 'raw', '-F', 'vdi', raw, vdi], check=True)


def fault_cases(exe, bios, work, start, stale, system, carrier, damaged, fixed):
    src = ROOT / 'build/rescue'
    manifest = checked_build(src)
    ui = load_catalog('en')
    pristine = sha256(start), sha256(carrier)
    before = sha256(system)
    cases = []

    def run(label, outcome, *, boot=start, target=system, backup=carrier, **opts):
        cases.append(restore_boot(exe, bios, src, manifest, work, boot, target, backup, ui, label, outcome, **opts))

    run('missing-target', 'RESTORE_TARGET', target=None)
    run('wrong-target', 'RESTORE_TARGET', serial=SECONDARY)
    # The older backup fixture carries internally consistent, approved synthetic
    # MBR bytes. Its code must fail the assembled Stage 1 comparison.
    other_start, other_disk = work / 'other-build.img', work / 'other-build.raw'
    other_floppy, blank = provision((src / FLOPPY).read_bytes())
    other_start.write_bytes(other_floppy)
    other_disk.write_bytes(expected_recovery(blank, wire(), published=True))
    run('different-approved-code', 'RESTORE_SCOPE_BAD', boot=other_start, backup=other_disk,
        serial=OTHER_SOURCE, recovery_serial=OTHER_BACKUP)
    run('missing-backup', 'RESTORE_BACKUP', backup=None)
    bad = work / 'unpublished.raw'
    shutil.copyfile(carrier, bad)
    write_at(bad, 8 * 512, bytes(512))
    run('unpublished-backup', 'RESTORE_BACKUP', backup=bad)
    shutil.copyfile(carrier, bad)
    write_at(bad, (STORE_DATA + 45) * 512 - 1, b'\xa5')
    run('damaged-backup-tail', 'RESTORE_BACKUP', backup=bad)
    run('stale-witness', 'RESTORE_BACKUP', boot=stale)
    run('witness-swapped-at-confirmation', 'RESTORE_BACKUP', key='y', change_floppy=stale)
    if sha256(system) != before:
        raise ValueError('An identity, backup or approval refusal changed the primary disk')

    def blocked_change(label, offset, value, reason):
        with system.open('rb') as f:
            f.seek(offset)
            old = f.read(len(value))
        if old == value:
            raise ValueError(f'{label}: fixture already has the injected bytes')
        write_at(system, offset, value)
        expected = sha256(system)
        run(label, reason)
        if sha256(system) != expected:
            raise ValueError(f'{label}: refusal changed the target')
        write_at(system, offset, old)

    blocked_change('foreign-code', 7, b'\x7e', 'RESTORE_SCOPE_BAD')
    blocked_change('different-disk-id', 440, b'\x7e', 'RESTORE_SCOPE_BAD')
    blocked_change('invalid-live-table', 446, b'\x27', 'RESTORE_TARGET')
    blocked_change('primary-gpt', 512, b'EFI PART', 'RESTORE_TARGET')
    blocked_change('trailing-gpt', system.stat().st_size - 512, b'EFI PART', 'RESTORE_TARGET')

    # Change a protected byte while paused at the prompt. The new sector is
    # still a valid target, but the displayed plan no longer names these bytes.
    def change_target(q, prompt):
        q.call('stop')
        write_at(system, 444, b'\x38')
        q.call('cont')

    run('target-changed-at-confirmation', 'RESTORE_CHANGED', key='y', before_key=change_target)
    write_at(system, 444, damaged[444:445])
    if sha256(system) != before:
        raise ValueError('A refused or cancelled repair changed the fixture')

    def fault(event, operation):
        conf = work / ('fault-' + operation + '.ini')
        conf.write_text(f'[inject-error]\nevent = "{event}"\niotype = "{operation}"\nerrno = "5"\nonce = "on"\n')
        return f'blkdebug:{conf}:{system}'

    run('source-write-error', 'RESTORE_IO', key='y', target=fault('write_aio', 'write'), writes=('0x30',))
    if sha256(system) != before:
        raise ValueError('A failed write changed the fixture')
    run('retry-after-write-error', 'RESTORE_DONE', key='y', writes=('0x30', '0xe7'), stored=512)
    if sha256(system) != sha256(fixed):
        raise ValueError('Retry changed bytes outside the approved code')
    write_at(system, 0, damaged)
    run('source-flush-error', 'RESTORE_IO', key='y', target=fault('flush_to_disk', 'flush'),
        writes=('0x30', '0xe7'), stored=512)
    if sha256(system) != sha256(fixed):
        raise ValueError('Unexpected bytes persisted after the injected flush error')
    run('restart-after-flush-error', 'RESTORE_INTACT')
    write_at(system, 0, damaged)
    conf = work / 'fault-readback.ini'
    conf.write_text('[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
                    '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\n'
                    'sector = "0"\nerrno = "5"\n')
    run('source-readback-error', 'RESTORE_IO', key='y', target=f'blkdebug:{conf}:{system}',
        writes=('0x30', '0xe7'), stored=512)
    if sha256(system) != sha256(fixed):
        raise ValueError('Unexpected bytes persisted after the injected readback error')
    run('restart-after-readback-error', 'RESTORE_INTACT')
    if pristine != (sha256(start), sha256(carrier)):
        raise ValueError('The negative campaign changed external media')
    return cases


def repair_kit(work, system, carrier, size, witness, *, program, kit, guide, ids, primary, secondary):
    """Package new VDIs and localized boot programs with the retained independent witness."""
    floppy = program + '.img'
    for path, (name, guid, serial), count in ((system, primary, size // 512), (carrier, secondary, CAPACITY)):
        make_vdi('qemu-img', path, work / name, guid, count, serial)
    docs = (ROOT / 'docs' / guide).read_text(encoding='utf-8')
    files = {'Anleitung.txt': docs.replace('\n', '\r\n').encode('utf-8-sig'),
             primary[0]: (work / primary[0]).read_bytes(), secondary[0]: (work / secondary[0]).read_bytes()}
    for lang, suffix, folder in LANGS:
        directory = ROOT / 'build' / ('rescue' + suffix)
        checked_build(directory, program)
        base, _ = prepare_pair((directory / floppy).read_bytes(), MODEL, primary[2], size // 512, *ids,
                               recovery=(MODEL, secondary[2], CAPACITY))
        if base[-512:] != witness[-512:] or base[WITNESS_START:WITNESS_START+512] != witness[:512]:
            raise ValueError('Recovery diskette and retained witness enrollment differ')
        files[folder + '/' + floppy] = base[:WITNESS_START] + witness
    bundle = work / kit
    with zipfile.ZipFile(bundle, 'x') as archive:
        for name, data in files.items():
            archive.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_DEFLATED)
    return bundle


def main():
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    out = ROOT / 'build/mbr-restore'
    prepare_output(out)
    src = ROOT / 'build/rescue'
    checked_build(src)
    size, extents = disk()
    approved = (src / 'restore-stage1.bin').read_bytes()[:CODE] + extents[0][CODE:]
    live = bytearray(approved)
    live[:CODE] = bytes(CODE)
    live[444:446] = b'\x76\x46'  # Reserved bytes on the current disk.
    assert live[446] == 0x80
    live[446] = 0                 # A valid, newer partition-table flag.
    damaged = bytes(live)
    repaired = approved[:CODE] + damaged[CODE:]
    with tempfile.TemporaryDirectory(dir=out) as directory:
        work = Path(directory)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        system, carrier = work / 'system.raw', work / 'recovery.raw'
        witness, stale_witness, setup = capture_and_publish(exe, bios, src, work, system, carrier,
                                                           size, extents, approved)
        write_at(system, 0, damaged)
        fixed = work / 'fixed.raw'
        write_fixture(fixed, size, {**extents, 0: repaired})
        bundle = repair_kit(work, system, carrier, size, witness, program='mbr-restore', kit=KIT,
                            guide='MBRRestore.txt', ids=IDS,
                            primary=(SYSTEM, '46460101-d413-4b6c-a346-000011111111', PRIMARY),
                            secondary=(RECOVERY, '46460202-d413-4b6c-a346-000022222222', SECONDARY))
        manual = qualify_kit(exe, bios, work, bundle, fixed, system)
        floppy = work / 'en/English' / FLOPPY
        stale = work / 'stale.img'
        stale.write_bytes(floppy.read_bytes()[:WITNESS_START] + stale_witness)
        faults = fault_cases(exe, bios, work, floppy, stale, system, carrier, damaged, fixed)
        results = dict(setup=setup, kit=manual, failures=faults, kit_sha256=sha256(bundle))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        bundle.replace(out / KIT)
    print(f'{len(setup) + len(manual) + len(faults)} boots passed: {out / KIT}')


if __name__ == '__main__':
    main()
