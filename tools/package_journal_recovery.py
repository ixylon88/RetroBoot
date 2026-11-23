"""Exercise the first interrupted visibility switch and package the checked VDIs."""
import json
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile

from build_hdd import write_fixture
from build_rescue import ROOT, prepare_output, sha256
from config_records import FIXTURE_MEDIA_ID, layout_crc
from journal_records import COMMITTED, EMPTY, PREPARED, encode, seal
from mbr_boot import boot_fixture
from package_mbr_recovery import LANGS
from package_mbr_restore import (capture_and_publish, checked_build, compare_image, primary_write_check,
                                 repair_kit, write_at)
from prepare_mbr_target import WITNESS_START
from rescue_match_fixtures import ADMIN, CHAINS, DATA, ROOT as ROOT_LBA
from rescue_plan_fixtures import disk
from rescue_text import load_catalog
from test_mbr_target import MODEL

PROGRAM = 'journal-recovery'
FLOPPY = PROGRAM + '.img'
KIT = 'RetroBoot-Partitionswechsel-Reparatur.zip'
PRIMARY = ('RB78-System.vdi', '46460505-d413-4b6c-a346-000011111111', 'VB46460505-11111111')
SECONDARY = ('RB78-Sicherung.vdi', '46460606-d413-4b6c-a346-000022222222', 'VB46460606-22222222')
IDS = tuple(b'RB78-TEST-PAIR-' + bytes([i]) for i in (1, 2, 3))
PASS, BLOCK = 'RB JOURNAL RECOVERY PASS', 'RB JOURNAL RECOVERY BLOCKED'


def slot_lbas(extents):
    spc = extents[ADMIN * 512][13]
    return [[DATA + (cluster - 2) * spc + i for cluster in chain for i in range(spc)][:3]
            for chain in CHAINS[-2:]]


def journal_records(extents, size, new):
    old = bytearray(new)
    if (new[446], new[450]) != (0x80, 0x0B):
        raise ValueError('Expected one active FAT32 system primary in the fixture')
    old[446], old[450] = 0, 0x1B
    common = dict(disk_id=struct.unpack_from('<I', new, 440)[0], layout=layout_crc(extents),
                  admin_start=ADMIN, admin_sectors=struct.unpack_from('<I', extents[ADMIN * 512], 32)[0],
                  media_id=FIXTURE_MEDIA_ID, capacity=size // 512, before=bytes(old))
    return (encode(phase=EMPTY, sequence=1, after=bytes(old), **common),
            encode(phase=PREPARED, sequence=2, after=new, **common),
            encode(phase=COMMITTED, sequence=2, after=new, **common))


def torn_snapshot(prepared):
    old, new = prepared[512:1024], prepared[1024:]
    # The active flag reached disk before the partition type. Neither intact
    # snapshot has these bytes, but a single left-to-right partial write does.
    torn = new[:450] + old[450:]
    if torn in (old, new):
        raise ValueError('Expected distinct visibility bytes on both sides of the tear')
    return torn


def record_extents(lbas, record):
    return {lba * 512: record[i * 512:(i + 1) * 512] for i, lba in enumerate(lbas)}


def run_boot(exe, bios, work, lang, start, system, carrier, name, outcome, lba, *, key=None,
             slot='B', fmt='raw', serial=PRIMARY[2], writes=(), stored=0, swap=None, before_key=None,
             snapshot_lba=None, snapshot_checked=False, cut_on_source_error=False):
    ui = load_catalog(lang)
    src = ROOT / 'build' / ('rescue' if lang == 'en' else 'rescue-' + lang)
    manifest = checked_build(src, PROGRAM)
    lines = ['RB JOURNAL RECOVERY', ui['RESTORE_CHECK']]
    actions = []
    if key:
        lines += [ui['D_SERIAL'] + ' ' + PRIMARY[2], ui['STORE_REV'] + '2', ui['JR_SCOPE']]
        prompt = ui['JR_CONFIRM']
        if snapshot_lba is not None:
            lines.append(ui['JR_SNAPSHOT'] + f' RBTXN.{slot}, LBA 0x{snapshot_lba:08X}')
            prompt = ui['JR_CONFIRM_BOTH']
        lines += [ui['JR_HEADER'] + f' RBTXN.{slot}, LBA 0x{lba:08X}', prompt]
        actions.append((prompt, key, swap, True))
    if snapshot_checked:
        lines.append(ui['JR_SNAPSHOT_DONE'])
    if not cut_on_source_error:
        lines += [ui[outcome], PASS if outcome in ('JR_DONE', 'JR_INTACT', 'RESTORE_CANCEL') else BLOCK]
    targets = ([lba] if snapshot_lba is None else [snapshot_lba, lba])[:writes.count('0x30')]
    fixture = dict(binary=(src / (PROGRAM + '.bin')).read_bytes(), memory=manifest['memory'][PROGRAM])
    return boot_fixture(exe, bios, fixture, work, start, system, name, lines, actions, [], [], readonly_start=True,
                        ata_identity=(MODEL, serial), disk_format=fmt, recovery_disk=carrier, recovery_format=fmt,
                        recovery_identity=(MODEL, SECONDARY[2]), io_check=primary_write_check(name, targets, writes, stored),
                        before_key=before_key, timeout=90, cut_on_source_error=cut_on_source_error)


def qualify_kit(exe, bios, work, bundle, pending, fixed, dest_lbas):
    header_lba, _, snapshot_lba = dest_lbas
    cases = []
    for lang, _, folder in LANGS:
        dest = work / lang
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(dest)
        floppy, system, carrier = dest / folder / FLOPPY, dest / PRIMARY[0], dest / SECONDARY[0]
        external = sha256(floppy), sha256(carrier)
        args = exe, bios, work, lang, floppy, system, carrier
        ui = load_catalog(lang)
        cases.append(run_boot(*args, lang + '-cancel', 'RESTORE_CANCEL', header_lba, fmt='vdi', key='esc',
                              snapshot_lba=snapshot_lba))
        compare_image(pending, system)
        cases.append(run_boot(*args, lang + '-finish', 'JR_DONE', header_lba, fmt='vdi', key=ui['A_YES'].lower(),
                              snapshot_lba=snapshot_lba, snapshot_checked=True, writes=('0x30', '0xe7') * 2, stored=1024))
        compare_image(fixed, system)
        cases.append(run_boot(*args, lang + '-restart', 'JR_INTACT', header_lba, fmt='vdi'))
        compare_image(fixed, system)
        if external != (sha256(floppy), sha256(carrier)):
            raise ValueError(f'{lang}: external media changed')
    return cases


def fault_cases(exe, bios, work, start, stale, system, carrier, fixed, lbas, records):
    cases = []
    seed, prepared, done = records
    pending = seed[:512] + prepared[512:]
    dest = lbas[1][0]
    external = sha256(start), sha256(carrier)
    initial_hash, final_hash = sha256(system), sha256(fixed)

    def run(name, outcome, *, target=system, backup=carrier, floppy=start, lba=dest, **options):
        cases.append(run_boot(exe, bios, work, 'en', floppy, target, backup, name, outcome, lba, **options))

    def put_record(slot, data):
        for offset, sector in record_extents(lbas[slot], data).items():
            write_at(system, offset, sector)

    def refused_change(name, offset, data, outcome):
        with system.open('rb') as stream:
            stream.seek(offset)
            old = stream.read(len(data))
        if old == data:
            raise ValueError(f'{name}: ineffective fixture change')
        write_at(system, offset, data)
        expected = sha256(system)
        run(name, outcome)
        if sha256(system) != expected:
            raise ValueError(f'{name}: refusal changed the disk')
        write_at(system, offset, old)

    run('missing-backup', 'RESTORE_BACKUP', backup=None)
    run('wrong-primary', 'RESTORE_TARGET', serial=SECONDARY[2])
    run('stale-witness', 'RESTORE_BACKUP', floppy=stale)
    run('witness-replaced-at-prompt', 'RESTORE_CHANGED', key='y', swap=stale)
    refused_change('unapproved-live-mbr', 444, b'\xac', 'RESTORE_TARGET')
    refused_change('live-mbr-still-old', 0, prepared[512:1024], 'RESTORE_TARGET')
    refused_change('primary-gpt', 512, b'EFI PART', 'RESTORE_TARGET')
    refused_change('trailing-gpt', system.stat().st_size - 512, b'EFI PART', 'RESTORE_TARGET')
    refused_change('root-entry-alias', ROOT_LBA * 512 + 26 * 32 + 26, struct.pack('<H', CHAINS[-2][0]), 'RESTORE_TARGET')
    refused_change('unrelated-header-byte', dest * 512 + 300, b'\xff', 'JR_BAD')
    refused_change('duplicate-preparations', dest * 512, prepared[:512], 'JR_BAD')
    refused_change('unrelated-new-snapshot', lbas[1][2] * 512 + 444, b'\xac', 'JR_BAD')
    refused_change('changed-old-snapshot', lbas[0][1] * 512 + 17, b'\x5a', 'JR_BAD')
    wrong = bytearray(prepared)
    wrong[48] ^= 1
    refused_change('foreign-valid-header', lbas[0][0] * 512, seal(wrong)[:512], 'JR_BAD')
    wrong = bytearray(prepared)
    wrong[16] = 3
    refused_change('later-sequence', lbas[0][0] * 512, seal(wrong)[:512], 'JR_BAD')

    # Both directory mappings change at the prompt but the on-disk pair still validates.
    def exchange(q, _prompt):
        q.call('stop')
        for index, chain in enumerate(reversed(CHAINS[-2:])):
            write_at(system, ROOT_LBA * 512 + (25 + index) * 32 + 26, struct.pack('<H', chain[0]))
        q.call('cont')

    run('changed-mapping-at-prompt', 'RESTORE_CHANGED', key='y', before_key=exchange)
    for index, chain in enumerate(CHAINS[-2:]):
        write_at(system, ROOT_LBA * 512 + (25 + index) * 32 + 26, struct.pack('<H', chain[0]))
    if sha256(system) != initial_hash:
        raise ValueError('A refused recovery changed the fixture')

    for split in (17, 37, 70, 510):
        torn = done[:split] + seed[split:512]
        if torn in (seed[:512], done[:512]):
            raise ValueError('Expected a torn header')
        write_at(system, dest * 512, torn)
        run(f'torn-at-{split}', 'JR_DONE', key='y', writes=('0x30', '0xe7'), stored=512)
        if sha256(system) != final_hash:
            raise ValueError('Torn-header recovery changed unexpected bytes')
    # A new CRC suffix under a baseline prefix cannot result from the accepted tear.
    write_at(system, dest * 512, seed[:508] + done[508:512])
    run('reverse-tear', 'JR_BAD')
    write_at(system, dest * 512, seed[:512])

    put_record(0, pending)
    put_record(1, prepared)
    run('opposite-slot', 'JR_DONE', lba=lbas[0][0], slot='A', key='y', writes=('0x30', '0xe7'), stored=512)
    run('opposite-slot-restart', 'JR_INTACT', lba=lbas[0][0])
    put_record(0, prepared)
    put_record(1, pending)
    if sha256(system) != initial_hash:
        raise ValueError('Swapped-slot recovery changed data outside the journal')

    def fault(event, operation):
        conf = work / ('fault-' + operation + '.ini')
        conf.write_text(f'[inject-error]\nevent = "{event}"\niotype = "{operation}"\nerrno = "5"\nonce = "on"\n')
        return f'blkdebug:{conf}:{system}'

    run('write-error', 'RESTORE_IO', target=fault('write_aio', 'write'), key='y', writes=('0x30',))
    if sha256(system) != initial_hash:
        raise ValueError('Failed write changed the system disk')
    run('retry-after-write-error', 'JR_DONE', key='y', writes=('0x30', '0xe7'), stored=512)
    if sha256(system) != final_hash:
        raise ValueError('Write retry differs from expected image')
    write_at(system, dest * 512, seed[:512])
    run('flush-error', 'RESTORE_IO', target=fault('flush_to_disk', 'flush'), key='y', writes=('0x30', '0xe7'), stored=512)
    if sha256(system) != final_hash:
        raise ValueError('Unexpected disk contents after the injected flush error')
    run('restart-after-flush-error', 'JR_INTACT')
    write_at(system, dest * 512, seed[:512])
    conf = work / 'readback.ini'
    conf.write_text('[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
                    f'[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nsector = "{dest}"\nerrno = "5"\n')
    run('readback-error', 'RESTORE_IO', target=f'blkdebug:{conf}:{system}', key='y', writes=('0x30', '0xe7'), stored=512)
    run('restart-after-readback-error', 'JR_INTACT')
    if sha256(system) != final_hash or external != (sha256(start), sha256(carrier)):
        raise ValueError('Disk contents differ after the recovery campaign')
    return cases


def snapshot_cases(exe, bios, work, start, system, carrier, fixed, lbas, records):
    cases = []
    seed, prepared, done = records
    old, new = prepared[512:1024], prepared[1024:]
    torn = torn_snapshot(prepared)
    header_lba, _, snapshot_lba = lbas[1]
    pair = ('0x30', '0xe7')
    external = sha256(start), sha256(carrier)
    complete_hash = sha256(fixed)
    if sha256(system) != complete_hash:
        raise ValueError('Unexpected starting state of the snapshot campaign')

    def reset(snapshot, header=seed[:512]):
        write_at(system, header_lba * 512, header)
        write_at(system, snapshot_lba * 512, snapshot)

    def run(name, outcome, expected_hash, *, target=system, slot=1, **options):
        cases.append(run_boot(exe, bios, work, 'en', start, target, carrier, name, outcome, lbas[slot][0],
                              slot='AB'[slot], **options))
        if sha256(system) != expected_hash:
            raise ValueError(f'{name}: primary disk differs from the expected image')

    reset(new)
    header_only_hash = sha256(system)
    reset(old)
    empty_hash = sha256(system)
    run('snapshot-not-started', 'JR_DONE', complete_hash, key='y', snapshot_lba=snapshot_lba,
        snapshot_checked=True, writes=pair * 2, stored=1024)

    for label, snapshot, header in (
            ('snapshot-unrelated-bytes', bytes(512), seed[:512]),
            ('snapshot-reverse-tear', old[:450] + new[450:], seed[:512]),
            ('snapshot-after-header-tear', torn, done[:37] + seed[37:512]),
            ('snapshot-under-completed-header', torn, done[:512])):
        reset(snapshot, header)
        run(label, 'JR_BAD', sha256(system))

    def revert_at_prompt(q, _prompt):
        q.call('stop')
        write_at(system, snapshot_lba * 512, old)
        q.call('cont')

    reset(torn)
    torn_hash = sha256(system)
    run('snapshot-changed-at-prompt', 'RESTORE_CHANGED', empty_hash, key='y', snapshot_lba=snapshot_lba,
        before_key=revert_at_prompt)
    reset(torn)

    def inject(name, rules):
        conf = work / (name + '.ini')
        conf.write_text(rules)
        return f'blkdebug:{conf}:{system}'

    fail_write = '[inject-error]\nevent = "write_aio"\niotype = "write"\nerrno = "5"\nonce = "on"\n'
    run('snapshot-write-error', 'RESTORE_IO', torn_hash, key='y', snapshot_lba=snapshot_lba,
        target=inject('snapshot-write', fail_write + f'sector = "{snapshot_lba}"\n'), writes=('0x30',))
    run('retry-snapshot-write', 'JR_DONE', complete_hash, key='y', snapshot_lba=snapshot_lba,
        snapshot_checked=True, writes=pair * 2, stored=1024)

    after_flush = '[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
    fail_read = '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nerrno = "5"\n'
    for label, rules in (
            ('snapshot-flush', '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nerrno = "5"\nonce = "on"\n'),
            ('snapshot-readback', after_flush + fail_read + f'sector = "{snapshot_lba}"\n'),
            ('allocation-recheck', after_flush + fail_read + f'sector = "{ROOT_LBA}"\n')):
        reset(torn)
        run(label + '-error', 'RESTORE_IO', header_only_hash, key='y', snapshot_lba=snapshot_lba,
            target=inject(label, rules), writes=pair, stored=512)
        run(label + '-cold-retry', 'JR_DONE', complete_hash, key='y', writes=pair, stored=512)

    # Halt the real guest on the *second* write, then kill QEMU. Cold boot
    # the same disks and verify the first, flushed sector is never rewritten.
    reset(torn)
    run('power-cut-before-header', None, header_only_hash, key='y', snapshot_lba=snapshot_lba,
        snapshot_checked=True, cut_on_source_error=True, target=inject('cut-header', fail_write + f'sector = "{header_lba}"\n'),
        writes=(*pair, '0x30'), stored=512)
    run('cold-after-power-cut', 'JR_DONE', complete_hash, key='y', writes=pair, stored=512)
    run('second-cold-after-power-cut', 'JR_INTACT', complete_hash)

    def write_record(slot, data):
        for offset, sector in record_extents(lbas[slot], data).items():
            write_at(system, offset, sector)

    write_record(1, prepared)
    write_record(0, done)
    reversed_hash = sha256(system)
    write_record(0, seed[:1024] + torn)
    run('snapshot-in-slot-a', 'JR_DONE', reversed_hash, slot=0, key='y', snapshot_lba=lbas[0][2],
        snapshot_checked=True, writes=pair * 2, stored=1024)
    write_record(0, prepared)
    write_record(1, done)
    if sha256(system) != complete_hash or external != (sha256(start), sha256(carrier)):
        raise ValueError('Unexpected disk, witness or carrier contents after the snapshot tests')
    return cases


def main():
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    out = ROOT / 'build' / PROGRAM
    prepare_output(out)
    src = ROOT / 'build/rescue'
    checked_build(src, PROGRAM)
    size, extents = disk()
    new = (src / 'restore-stage1.bin').read_bytes()[:432] + extents[0][432:]
    lbas = slot_lbas(extents)
    seed, prepared, done = journal_records(extents, size, new)
    extents.update(record_extents(lbas[0], prepared))
    extents.update(record_extents(lbas[1], seed[:1024] + torn_snapshot(prepared)))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        work = Path(tmp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        system, carrier, fixed = work / 'system.raw', work / 'recovery.raw', work / 'complete.raw'
        witness, stale_witness, setup = capture_and_publish(exe, bios, src, work, system, carrier, size, extents,
                                                           new, primary=PRIMARY[2], secondary=SECONDARY[2], ids=IDS)
        write_fixture(fixed, size, {**extents, 0: new, **record_extents(lbas[1], done)})
        bundle = repair_kit(work, system, carrier, size, witness, program=PROGRAM, kit=KIT, guide='JournalRecovery.txt',
                            ids=IDS, primary=PRIMARY, secondary=SECONDARY)
        manual = qualify_kit(exe, bios, work, bundle, system, fixed, lbas[1])
        floppy = work / 'en/English' / FLOPPY
        stale = work / 'stale.img'
        stale.write_bytes(floppy.read_bytes()[:WITNESS_START] + stale_witness)
        # Exercise the previous one-sector path on the same enrolled hardware.
        write_at(system, lbas[1][2] * 512, new)
        faults = fault_cases(exe, bios, work, floppy, stale, system, carrier, fixed, lbas, (seed, prepared, done))
        snapshots = snapshot_cases(exe, bios, work, floppy, system, carrier, fixed, lbas, (seed, prepared, done))
        results = dict(setup=setup, kit=manual, failures=faults, snapshots=snapshots, kit_sha256=sha256(bundle))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        bundle.replace(out / KIT)
    print(f'{len(setup) + len(manual) + len(faults) + len(snapshots)} boots passed: {out / KIT}')


if __name__ == '__main__':
    main()
