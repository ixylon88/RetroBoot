"""Boot the operator MBR capture and approval, then save and cold-read the same pair."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from backup_container import Chunk, encode, inspect
from backup_verify_vectors import record, wire
from build_hdd import write_fixture
from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import Checkpoint, EMPTY, ORIGIN, put
from package_backup_disk import make_vdi
from package_mbr_recovery import LANGS
from prepare_mbr_target import STORE_DATA, WITNESS_START, prepare_pair
from rescue_plan_fixtures import disk
from rescue_text import load_catalog
from test_backup_disk import BLOCK, CAPACITY, PASS, boot_case, commit
from test_mbr_recovery_disk import recovery_fields
from test_mbr_target import MODEL, disk_fields

START = 'mbr-backup.img'
SYSTEM = 'RB75-System.vdi'
RECOVERY = 'RB75-Sicherung.vdi'
SOURCE_SERIAL = 'VB75757575-11111111'
RECOVERY_SERIAL = 'VB76767676-22222222'
IDS = tuple(b'RB75-TEST-PAIR-' + bytes([i]) for i in (1, 2, 3))
WITNESS_HEADER = WITNESS_START // 512 + 1
KIT = 'RetroBoot-MBR-Sicherung.zip'


def expected_file(original, approved):
    reference = wire()
    identity, entries = inspect(reference)
    chunks = []
    for e in entries:
        pos = e['file_sector'] * 512
        data = reference[pos:pos + e['sectors'] * 512]
        if e['kind'] == 1:
            data = original
        elif e['kind'] == 2:
            data = approved
        chunks.append(Chunk(e['kind'], e['index'], e['lba'], data, e['owner_start'], e['owner_sectors']))
    return encode(identity, chunks)


def history_boot(exe, bios, src, work, start, system, recovery, ui, name, original, approved, sectors,
                 carrier_bytes, ids, *, capture=False, fmt='raw', source_serial=SOURCE_SERIAL,
                 recovery_serial=RECOVERY_SERIAL):
    """Predict both media from their prior contents and boot the actual E or R action."""
    manifest = json.loads((src / 'manifest.json').read_bytes())
    fixture = dict(binary=(src / 'mbr-target.bin').read_bytes(), memory=manifest['memory']['mbr-target'])
    screen = [ui['PAIR_MENU'], 'RB ATA TARGET', ui['D_BOTH'], ui['D_FIRST']]
    screen += disk_fields(ui, 'D_EXPECT', MODEL, source_serial, sectors)
    screen += disk_fields(ui, 'D_LIVE', MODEL, source_serial, sectors) + ['TARGET MATCH']
    for title in ('D_REC_EXPECT', 'D_REC_LIVE'):
        screen += recovery_fields(ui, title, MODEL, recovery_serial, CAPACITY)
    screen.append('RECOVERY MATCH')
    prompt = ui['D_REC_FIRST'] if capture else ui['D_REC_REVIEW']
    key = 'e' if capture else 'r'
    screen.append(prompt)
    keys = [(ui['PAIR_MENU'], '1'), (ui['D_FIRST'], key), (prompt, key)]

    def header(tag, point):
        return record(tag, point, sectors, original, approved, target_id=ids[0], carrier_id=ids[1])

    if capture:
        changes = [(2, original), (1, header(b'RBORG001', ORIGIN)), (3, header(b'RBCMT001', ORIGIN)),
                   (WITNESS_HEADER + 1, original), (WITNESS_HEADER, header(b'RBWIT001', ORIGIN))]
        screen.append('INITIAL WITNESS PUBLISHED')
    else:
        diff = [(i, a, b) for i, (a, b) in enumerate(zip(original, approved)) if a != b]
        screen += [ui['A_TARGET'] + ' ' + ids[0].hex(' ').upper(), ui['A_CARRIER'] + ' ' + ids[1].hex(' ').upper(),
                   ui['A_SECTORS'] + f' 0x{sectors:016X}', 'REVIEW 2', 'BASE REV 1',
                   f'CHANGED BYTES {len(diff)}', ui['A_DIFF']]
        screen += [f'0x{i:04X}     {a:02X} -> {b:02X}' for i, a, b in diff]
        screen += [ui['A_DECIDE'], 'APPROVED REV 2']
        keys.append((ui['A_DECIDE'], ui['A_YES'].lower()))
        reserved, accepted = Checkpoint(2, 2), Checkpoint(3, 2, 2)
        changes = [(6, EMPTY), (5, header(b'RBCMT001', reserved)), (WITNESS_HEADER, header(b'RBWIT001', reserved)),
                   (4, approved), (3, header(b'RBCMT001', accepted)), (WITNESS_HEADER + 3, approved),
                   (WITNESS_HEADER, header(b'RBWIT002', accepted))]
    expected_start, expected_disk = bytearray(start.read_bytes()), bytearray(carrier_bytes)
    for lba, data in changes:
        put(expected_start if lba >= WITNESS_HEADER else expected_disk, lba, data)
    source_hash = sha256(system)
    report = boot_fixture(exe, bios, fixture, work, start, system, name, screen + ['RB ATA TARGET PASS'],
                          [(p, k, None, False) for p, k in keys], [n for n, _ in changes],
                          [0] * (6 if capture else 3), ata_identity=(MODEL, source_serial), disk_format=fmt,
                          recovery_disk=recovery, recovery_identity=(MODEL, recovery_serial), recovery_format=fmt,
                          recovery_writes=[n for n, _ in changes if n < WITNESS_HEADER])
    if start.read_bytes() != expected_start or sha256(system) != source_hash:
        raise ValueError(f'{name}: unexpected change to the start diskette or system disk')
    return bytes(expected_disk), report


def compare_disk(work, expected, disk_path, fmt):
    raw = work / 'expected.raw'
    raw.write_bytes(expected)
    subprocess.run(['qemu-img', 'compare', '-f', 'raw', '-F', fmt, raw, disk_path], check=True)


def qualify_pair(exe, bios, src, work, start, source, carrier, ui, name, original, approved, sectors,
                 captured_carrier, ids, fmt):
    """Qualify a captured-only pair through refusal, approval, publication and independent cold boots."""
    reports = []
    first_start, source_hash = start.read_bytes(), sha256(source)
    data = expected_file(original, approved)

    def backup(step, key, lines, *, disk=source, floppy=start, writes=(), image_format=fmt, recovery=carrier):
        report = boot_case(exe, bios, src, work, floppy, disk, recovery, ui, name + '-' + step, key, lines,
                           expected_writes=writes, source_serial=SOURCE_SERIAL, recovery_serial=RECOVERY_SERIAL,
                           input_format=image_format, recovery_format=image_format, combined=True)
        reports.append(report)

    backup('approval-required', 's', [ui['STORE_SAVE'], ui['STORE_HISTORY'], BLOCK])
    compare_disk(work, captured_carrier, carrier, fmt)
    if start.read_bytes() != first_start:
        raise ValueError('Failed save changed the original witness')

    history, decision = history_boot(exe, bios, src, work, start, source, carrier, ui, name + '-approve',
                                     original, approved, sectors, captured_carrier, ids, fmt=fmt)
    reports.append(decision)
    compare_disk(work, history, carrier, fmt)
    approved_start = start.read_bytes()
    complete = bytearray(history)
    complete[STORE_DATA * 512:STORE_DATA * 512 + len(data)] = data
    put(complete, 8, commit(data, ids))

    total = len(data) // 512
    trailer = [ui['VERIFY_COUNT'] + str(total), ui['STORE_REV'] + '2', PASS]
    writes = [*range(STORE_DATA, STORE_DATA + total), 8]
    saved = [ui['STORE_SAVE'], ui['STORE_DONE'], *trailer]
    backup('publish', 's', saved, writes=writes)
    backup('cold', 'v', [ui['STORE_VERIFY'], ui['STORE_READ'], *trailer], disk=None)
    stale = work / 'first-capture.img'
    stale.write_bytes(first_start)
    backup('stale-witness', 'v', [ui['STORE_VERIFY'], ui['STORE_FAILED'], BLOCK], disk=None, floppy=stale)
    compare_disk(work, complete, carrier, fmt)
    if sha256(source) != source_hash:
        raise ValueError('Publication or verification changed the system disk')

    # An unreviewed boot-code change on a separate live fixture must never become its approved MBR.
    size, managed = disk()
    drift = bytearray(approved)
    drift[77] ^= 1
    live, copy = work / 'later-source.raw', work / 'later-recovery.raw'
    write_fixture(live, size, {**managed, 0: bytes(drift)})
    offline = sha256(live)
    copy.write_bytes(history)
    backup('later-live-mbr', 's', saved, disk=live, recovery=copy, writes=writes, image_format='raw')
    observed = copy.read_bytes()
    if observed != complete or sha256(live) != offline or start.read_bytes() != approved_start:
        raise ValueError('The backup disagrees with the separately approved MBR history')
    return reports, observed[STORE_DATA * 512:STORE_DATA * 512 + len(data)]


def operator_pair(exe, bios, src, work, original, approved):
    """Use the command-line preparer with fresh identities and start from an empty history."""
    ui = load_catalog('en')
    size, initial = disk('unknown-mbr')
    sectors = size // 512
    dest = work / 'operator'
    subprocess.run([sys.executable, ROOT / 'tools/prepare_mbr_target.py', src / START,
                    '--model', MODEL, '--serial', SOURCE_SERIAL, '--sectors', str(sectors),
                    '--recovery-model', MODEL, '--recovery-serial', RECOVERY_SERIAL,
                    '--recovery-sectors', str(CAPACITY), '--output', dest], check=True)
    start, carrier, source = dest / START, dest / 'mbr-recovery.img', dest / 'system.raw'
    profile = start.read_bytes()[-512:]
    ids = profile[8:24], profile[32:48], profile[108:124]
    write_fixture(source, size, initial)
    captured, first = history_boot(exe, bios, src, work, start, source, carrier, ui, 'operator-capture',
                                  original, approved, sectors, carrier.read_bytes(), ids, capture=True)
    if carrier.read_bytes() != captured:
        raise ValueError('Capture changed unexpected bytes on the newly prepared disk')
    with source.open('r+b') as disk_file:
        disk_file.write(approved)
    steps, saved = qualify_pair(exe, bios, src, work, start, source, carrier, ui, 'operator', original, approved,
                               sectors, captured, ids, 'raw')
    # The identities appear in the review screen and vary on each invocation.
    return [r['name'] for r in [first, *steps]], saved


def main():
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    out = ROOT / 'build/backup-handoff'
    prepare_output(out)
    size, initial = disk('unknown-mbr')
    _, managed = disk()
    original, approved = initial[0], managed[0]
    sectors = size // 512
    reports = {}
    with tempfile.TemporaryDirectory(dir=out) as directory:
        work = Path(directory)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        system, rec = work / 'system.raw', work / 'recovery.raw'
        write_fixture(system, size, initial)
        instructions = (ROOT / 'docs/BackupHandoff.txt').read_text(encoding='utf-8')
        files = {'Anleitung.txt': instructions.replace('\n', '\r\n').encode('utf-8-sig')}
        captured_carrier = None
        for lang, suffix, folder in LANGS:
            src = ROOT / 'build' / ('rescue' + suffix)
            manifest = json.loads((src / 'manifest.json').read_bytes())
            check_build_inputs(manifest, ROOT)
            for artifact in (START, 'mbr-target.bin', 'backup-disk.bin'):
                if sha256(src / artifact) != manifest['artifacts'][artifact]['sha256']:
                    raise ValueError(f'Changed {lang} handoff artifact: {artifact}')
            start = work / START
            boot, prefix = prepare_pair((src / START).read_bytes(), MODEL, SOURCE_SERIAL, sectors, *IDS,
                                        recovery=(MODEL, RECOVERY_SERIAL, CAPACITY))
            start.write_bytes(boot)
            blank = prefix.ljust(CAPACITY * 512, b'\0')
            rec.write_bytes(blank)
            captured, first = history_boot(exe, bios, src, work, start, system, rec, load_catalog(lang),
                                          lang + '-capture', original, approved, sectors, blank, IDS, capture=True)
            if rec.read_bytes() != captured or (captured_carrier is not None and captured != captured_carrier):
                raise ValueError('First capture disagrees with the expected recovery disk')
            captured_carrier = captured
            files[folder + '/' + START] = start.read_bytes()
            reports[lang] = [first]
        # The external change is made only to the offline, disposable system fixture.
        write_fixture(system, size, managed)
        for raw, name, guid, serial, count in (
                (system, SYSTEM, '75757575-d413-4b6c-a375-146111111111', SOURCE_SERIAL, sectors),
                (rec, RECOVERY, '76767676-d413-4b6c-a375-146122222222', RECOVERY_SERIAL, CAPACITY)):
            make_vdi('qemu-img', raw, work / name, guid, count, serial)
            files[name] = (work / name).read_bytes()
        bundle = work / KIT
        with zipfile.ZipFile(bundle, 'x') as z:
            for name, content in files.items():
                z.writestr(zipfile.ZipInfo(name), content, compress_type=zipfile.ZIP_DEFLATED)

        verified = {}
        for lang, suffix, folder in LANGS:
            dest = work / lang
            with zipfile.ZipFile(bundle) as z:
                z.extractall(dest)
            src = ROOT / 'build' / ('rescue' + suffix)
            steps, verified[lang] = qualify_pair(exe, bios, src, work, dest / folder / START, dest / SYSTEM,
                                                 dest / RECOVERY, load_catalog(lang), lang, original, approved,
                                                 sectors, captured_carrier, IDS, 'vdi')
            reports[lang].extend(steps)
        reports['operator_pair'], saved = operator_pair(exe, bios, ROOT / 'build/rescue', work, original, approved)
        if any(saved != payload for payload in verified.values()):
            raise ValueError('The operator-prepared pair and packaged pair produced different backup files')
        (out / 'verified.rbb').write_bytes(saved)
        (out / 'results.json').write_text(json.dumps(reports, indent=2) + '\n')
        bundle.replace(out / KIT)
    print(f'MBR capture, explicit approval, publication and cold verification passed in both languages: {out / KIT}')


if __name__ == '__main__':
    main()
