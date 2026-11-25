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
PRIMARY = ('RB82-System.vdi', '46461313-d413-4b6c-a346-000011111111', 'VB46461313-11111111')
SECONDARY = ('RB82-Sicherung.vdi', '46461414-d413-4b6c-a346-000022222222', 'VB46461414-22222222')
IDS = tuple(b'RB82-TEST-PAIR-' + bytes([i]) for i in (1, 2, 3))
MBR_CHANGES = ((446, 0, 0x80), (450, 0x1B, 0x0B))
WRITE_FLUSH = ('0x30', '0xe7')
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


def interrupted_prepare(seed, prepared, split=70):
    """The new snapshot reached disk before the prepare header was published."""
    return prepared[:split] + seed[split:512] + prepared[512:]


def record_extents(lbas, record):
    return {lba * 512: record[i * 512:(i + 1) * 512] for i, lba in enumerate(lbas)}


def set_journal_pair(system, lbas, live, first, second):
    write_at(system, 0, live)
    for mapping, record in zip(lbas, (first, second)):
        for offset, sector in record_extents(mapping, record).items():
            write_at(system, offset, sector)
    return sha256(system)


def run_boot(exe, bios, work, lang, start, system, carrier, name, outcome, lba, *, key=None,
             slot='B', fmt='raw', serial=PRIMARY[2], writes=(), stored=0, swap=None, before_key=None,
             snapshot_lba=None, snapshot_checked=False, mbr_changes=(), mbr_checked=False,
             partial_mbr=False, prepare_lba=None, prepare_checked=False, discard=False, cut_on_source_error=False):
    ui = load_catalog(lang)
    src = ROOT / 'build' / ('rescue' if lang == 'en' else 'rescue-' + lang)
    manifest = checked_build(src, PROGRAM)
    lines = ['RB JOURNAL RECOVERY', ui['RESTORE_CHECK']]
    actions = []
    if key:
        lines += [ui['D_SERIAL'] + ' ' + PRIMARY[2], ui['STORE_REV'] + '2']
    if key and discard:
        prompt = ui['JR_DISCARD']
        lines += [ui['JR_UNFINISHED'], ui['JR_SNAPSHOT'] + f' RBTXN.{slot}, LBA 0x{lba:08X}', prompt]
    elif key:
        scope = 'JR_PREPARED' if mbr_changes else 'JR_SCOPE'
        if prepare_lba is not None:
            scope = 'JR_INCOMPLETE'
        elif partial_mbr:
            scope = 'JR_PARTIAL'
        lines.append(ui[scope])
        if prepare_lba is not None:
            peer = 'A' if slot == 'B' else 'B'
            lines.append(ui['JR_PREPARE_HEADER'] + f' RBTXN.{peer}, LBA 0x{prepare_lba:08X}')
        if mbr_changes:
            lines += [ui['JR_MBR'], ui['JR_DELTA']]
            lines.extend(f'0x{offset:04X}     {old:02X} -> {new:02X}' for offset, old, new in mbr_changes)
        prompt = ui['JR_CONFIRM']
        if snapshot_lba is not None:
            lines.append(ui['JR_SNAPSHOT'] + f' RBTXN.{slot}, LBA 0x{snapshot_lba:08X}')
            prompt = ui['JR_APPLY' if mbr_changes else 'JR_CONFIRM_BOTH']
        if prepare_lba is not None:
            prompt = ui['JR_PREPARE_APPLY']
        lines += [ui['JR_HEADER'] + f' RBTXN.{slot}, LBA 0x{lba:08X}', prompt]
    if key:
        actions.append((prompt, key, swap, True))
    if prepare_checked:
        lines.append(ui['JR_PREPARE_DONE'])
    if mbr_checked:
        lines.append(ui['JR_MBR_DONE'])
    if snapshot_checked:
        lines.append(ui['JR_SNAPSHOT_DONE'])
    if not cut_on_source_error:
        successes = ('JR_DONE', 'JR_INTACT', 'JR_DISCARDED', 'JR_BASELINE', 'RESTORE_CANCEL')
        lines += [ui[outcome], PASS if outcome in successes else BLOCK]
    targets = [sector for sector in (prepare_lba, 0 if mbr_changes else None, snapshot_lba, lba) if sector is not None]
    fixture = dict(binary=(src / (PROGRAM + '.bin')).read_bytes(), memory=manifest['memory'][PROGRAM])
    return boot_fixture(exe, bios, fixture, work, start, system, name, lines, actions, [], [], readonly_start=True,
                        ata_identity=(MODEL, serial), disk_format=fmt, recovery_disk=carrier, recovery_format=fmt,
                        recovery_identity=(MODEL, SECONDARY[2]),
                        io_check=primary_write_check(name, targets[:writes.count('0x30')], writes, stored),
                        before_key=before_key, timeout=90, cut_on_source_error=cut_on_source_error)


def qualify_kit(exe, bios, work, bundle, pending, baseline, snapshot_lba):
    cases = []
    for lang, _, folder in LANGS:
        dest = work / lang
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(dest)
        floppy, system, carrier = dest / folder / FLOPPY, dest / PRIMARY[0], dest / SECONDARY[0]
        external = sha256(floppy), sha256(carrier)
        args = exe, bios, work, lang, floppy, system, carrier
        ui = load_catalog(lang)
        plan = dict(fmt='vdi', discard=True, slot='A')
        cases.append(run_boot(*args, lang + '-cancel', 'RESTORE_CANCEL', snapshot_lba, key='esc', **plan))
        compare_image(pending, system)
        cases.append(run_boot(*args, lang + '-discard', 'JR_DISCARDED', snapshot_lba, key=ui['A_YES'].lower(),
                              writes=WRITE_FLUSH, stored=512, **plan))
        compare_image(baseline, system)
        cases.append(run_boot(*args, lang + '-restart', 'JR_BASELINE', snapshot_lba, fmt='vdi'))
        compare_image(baseline, system)
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
    refused_change('old-mbr-with-advanced-journal', 0, prepared[512:1024], 'JR_BAD')
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


def prepared_mbr_cases(exe, bios, work, start, stale, system, carrier, fixed, lbas, records):
    seed, prepared, done = records
    old, new = prepared[512:1024], prepared[1024:]
    header_lba, _, snapshot_lba = lbas[1]
    prompt = dict(key='y', mbr_changes=MBR_CHANGES, snapshot_lba=snapshot_lba)
    torn = torn_snapshot(prepared)
    partial_prompt = dict(key='y', mbr_changes=MBR_CHANGES[1:], snapshot_lba=snapshot_lba, partial_mbr=True)
    cases = []
    external = sha256(start), sha256(carrier)
    final_hash = sha256(fixed)
    if sha256(system) != final_hash:
        raise ValueError('Unexpected starting state for prepared-MBR recovery')

    def arrange(live, first=prepared, second=seed):
        return set_journal_pair(system, lbas, live, first, second)

    def run(name, outcome, expected, *, target=system, backup=carrier, slot=1, **options):
        cases.append(run_boot(exe, bios, work, 'en', start, target, backup, name, outcome, lbas[slot][0],
                              slot='AB'[slot], **options))
        if sha256(system) != expected:
            raise ValueError(f'{name}: unexpected changes to system disk')

    next_hash = arrange(new)
    partial_hash = arrange(torn)
    initial_hash = arrange(old)
    run('prepared-missing-backup', 'RESTORE_BACKUP', initial_hash, backup=None)
    run('prepared-wrong-target', 'RESTORE_TARGET', initial_hash, serial=SECONDARY[2])
    run('prepared-witness-replaced', 'RESTORE_CHANGED', initial_hash, swap=stale, **prompt)
    run('prepared-intact-mbr', 'JR_DONE', final_hash, mbr_checked=True, snapshot_checked=True,
        writes=WRITE_FLUSH * 3, stored=1536, **prompt)
    for name, live, peer, outcome in (
            ('live-reverse-tear', old[:450] + new[450:], seed, 'RESTORE_TARGET'),
            ('partial-with-damaged-code', bytes([torn[0] ^ 1]) + torn[1:], seed, 'RESTORE_TARGET'),
            ('partial-with-foreign-reserved-byte', torn[:444] + bytes([torn[444] ^ 1]) + torn[445:], seed, 'RESTORE_TARGET'),
            ('partial-with-advanced-snapshot', torn, seed[:1024] + new, 'JR_BAD'),
            ('partial-with-partial-journal', torn, seed[:1024] + torn, 'JR_BAD'),
            ('partial-with-committed-peer', torn, done, 'JR_BAD'),
            ('partial-with-duplicate-prepare', torn, prepared, 'JR_BAD'),
            ('old-with-partial-snapshot', old, seed[:1024] + torn_snapshot(prepared), 'JR_BAD'),
            ('old-with-committed-peer', old, done, 'JR_BAD')):
        run(name, outcome, arrange(live, second=peer))

    # Both journal copies and the live disk agree on the same protected byte,
    # but the published external MBR and independent witness do not authorize it.
    def other_disk_bytes(sector):
        return sector[:444] + bytes([sector[444] ^ 1]) + sector[445:]

    foreign_old, foreign_new = other_disk_bytes(old), other_disk_bytes(new)
    foreign = arrange(foreign_old, seal(prepared[:512] + foreign_old + foreign_new),
                      seal(seed[:512] + foreign_old * 2))
    run('internally-valid-unapproved-mbr', 'JR_BAD', foreign)

    def change_live_mbr(sector):
        def change(q, _prompt):
            q.call('stop')
            write_at(system, 0, sector)
            q.call('cont')
        return change

    arrange(old)
    run('live-mbr-changed-at-confirmation', 'RESTORE_CHANGED', next_hash,
        before_key=change_live_mbr(new), **prompt)

    # Both valid preimages would offer an MBR write, but authorize different bytes.
    arrange(old)
    run('old-to-partial-at-confirmation', 'RESTORE_CHANGED', partial_hash, before_key=change_live_mbr(torn), **prompt)
    run('partial-to-old-at-confirmation', 'RESTORE_CHANGED', initial_hash,
        before_key=change_live_mbr(old), **partial_prompt)
    arrange(torn)
    run('partial-witness-replaced', 'RESTORE_CHANGED', partial_hash, swap=stale, **partial_prompt)

    def inject(name, rules):
        conf = work / (name + '.ini')
        conf.write_text(rules)
        return f'blkdebug:{conf}:{system}'

    fail_write = '[inject-error]\nevent = "write_aio"\niotype = "write"\nerrno = "5"\nonce = "on"\n'
    arrange(old)
    run('prepared-mbr-write-error', 'RESTORE_IO', initial_hash,
        target=inject('write-mbr', fail_write + 'sector = "0"\n'), writes=('0x30',), **prompt)

    # QEMU traps the guest's sector write before committing it. After the hard
    # stop, model a torn sector by persisting exactly the intended prefix.
    run('cut-on-live-mbr-write', None, initial_hash, target=inject('cut-live-mbr', fail_write + 'sector = "0"\n'),
        cut_on_source_error=True, writes=('0x30',), **prompt)
    write_at(system, 0, new[:450])
    if sha256(system) != partial_hash:
        raise ValueError('Injected partial write differs from the exact expected disk')
    run('cold-recover-partial-mbr', 'JR_DONE', final_hash, mbr_checked=True, snapshot_checked=True,
        writes=WRITE_FLUSH * 3, stored=1536, **partial_prompt)
    run('cold-after-partial-mbr-repair', 'JR_INTACT', final_hash)

    after_flush = '[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
    fail_read = '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nerrno = "5"\n'
    for name, rules in (
            ('mbr-flush', '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nerrno = "5"\nonce = "on"\n'),
            ('mbr-readback', after_flush + fail_read + 'sector = "0"\n'),
            ('mbr-allocation-recheck', after_flush + fail_read + f'sector = "{ROOT_LBA}"\n')):
        arrange(old)
        run(name + '-error', 'RESTORE_IO', next_hash, target=inject(name, rules),
            writes=WRITE_FLUSH, stored=512, **prompt)
        run(name + '-cold-retry', 'JR_DONE', final_hash, key='y', snapshot_lba=snapshot_lba,
            snapshot_checked=True, writes=WRITE_FLUSH * 2, stored=1024)

    # Stop on the first journal write after the durable MBR change and kill the VM.
    arrange(old)
    run('power-cut-after-live-mbr', None, next_hash, target=inject('cut-first-journal-write',
        fail_write + f'sector = "{snapshot_lba}"\n'), cut_on_source_error=True, mbr_checked=True,
        writes=(*WRITE_FLUSH, '0x30'), stored=512, **prompt)
    run('cold-after-live-mbr', 'JR_DONE', final_hash, key='y', snapshot_lba=snapshot_lba,
        snapshot_checked=True, writes=WRITE_FLUSH * 2, stored=1024)
    run('second-cold-after-live-mbr', 'JR_INTACT', final_hash)

    arrange(torn)
    run('partial-mbr-readback-error', 'RESTORE_IO', next_hash, writes=WRITE_FLUSH, stored=512,
        target=inject('partial-readback', after_flush + fail_read + 'sector = "0"\n'), **partial_prompt)
    run('cold-after-partial-readback-error', 'JR_DONE', final_hash, key='y', snapshot_lba=snapshot_lba,
        snapshot_checked=True, writes=WRITE_FLUSH * 2, stored=1024)

    expected = arrange(new, done, prepared)
    arrange(torn, seed, prepared)
    run('partial-mbr-reversed-slots', 'JR_DONE', expected, key='y', slot=0, snapshot_lba=lbas[0][2],
        partial_mbr=True, mbr_changes=MBR_CHANGES[1:], mbr_checked=True, snapshot_checked=True,
        writes=WRITE_FLUSH * 3, stored=1536)

    # Reverse the physical slots and start with a visible but inactive primary.
    # Its confirmation may advertise only the one byte that will actually change.
    visible = old[:450] + new[450:]
    single = seal(prepared[:512] + visible + new)
    expected = arrange(new, seal(done[:512] + visible + new), single)
    arrange(visible, seal(seed[:512] + visible * 2), single)
    run('prepared-one-byte-reversed-slots', 'JR_DONE', expected, key='y', slot=0, snapshot_lba=lbas[0][2],
        mbr_changes=MBR_CHANGES[:1], mbr_checked=True, snapshot_checked=True, writes=WRITE_FLUSH * 3, stored=1536)
    if arrange(new, prepared, done) != final_hash or external != (sha256(start), sha256(carrier)):
        raise ValueError('Prepared-MBR recovery changed unrelated bytes or external media')
    return cases


def prepare_header_cases(exe, bios, work, start, stale, system, carrier, fixed, lbas, records):
    seed, prepared, done = records
    old, new = prepared[512:1024], prepared[1024:]
    torn = interrupted_prepare(seed, prepared)
    cases = []
    external = sha256(start), sha256(carrier)
    final_hash = sha256(fixed)
    if sha256(system) != final_hash:
        raise ValueError('Unexpected starting disk for prepare-header recovery')

    def arrange(live=old, first=torn, second=seed):
        return set_journal_pair(system, lbas, live, first, second)

    def run(name, outcome, expected, *, target=system, slot=1, **options):
        cases.append(run_boot(exe, bios, work, 'en', start, target, carrier, name, outcome, lbas[slot][0],
                              slot='AB'[slot], **options))
        if sha256(system) != expected:
            raise ValueError(f'{name}: unexpected system disk contents')

    def plan(slot):
        return dict(key='y', prepare_lba=lbas[1 - slot][0], mbr_changes=MBR_CHANGES, snapshot_lba=lbas[slot][2])

    finish = dict(prepare_checked=True, mbr_checked=True, snapshot_checked=True, writes=WRITE_FLUSH * 4, stored=2048)
    for split in (0, 17, 37, 510):
        arrange(first=interrupted_prepare(seed, prepared, split))
        run(f'prepare-header-prefix-{split}', 'JR_DONE', final_hash, **plan(1), **finish)
    reversed_hash = arrange(new, done, prepared)
    arrange(old, seed, torn)
    run('prepare-header-opposite-slot', 'JR_DONE', reversed_hash, slot=0, **plan(0), **finish)

    run('no-switch-evidence', 'JR_BASELINE', arrange(old, seed, seed))
    for name, live, first, second in (
            ('prepare-with-partial-live-mbr', torn_snapshot(prepared), torn, seed),
            ('prepare-with-new-live-mbr', new, torn, seed),
            ('prepare-without-baseline', old, torn, torn),
            ('prepare-with-damaged-old-snapshot', old, torn[:512] + new + new, seed),
            ('prepare-with-unfinished-new-snapshot', old, torn[:1024] + torn_snapshot(prepared), seed),
            ('prepare-with-reversed-header-tear', old, seed[:37] + prepared[37:], seed),
            ('prepare-with-foreign-header-byte', old, torn[:300] + b'\xff' + torn[301:], seed)):
        run(name, 'JR_BAD', arrange(live, first, second))

    # Even a self-consistent baseline and matching live disk cannot authorize
    # a change to boot code when constructing a synthetic prepared pair.
    bad_old = bytes([old[0] ^ 1]) + old[1:]
    bad_seed = seal(seed[:512] + bad_old * 2)
    bad_prepare = seal(prepared[:512] + bad_old + new)
    run('prepare-protected-mbr-delta', 'JR_BAD',
        arrange(bad_old, interrupted_prepare(bad_seed, bad_prepare), bad_seed))

    def change_header(data):
        def change(q, _prompt):
            q.call('stop')
            write_at(system, lbas[0][0] * 512, data[:512])
            q.call('cont')
        return change

    valid = arrange(first=prepared)
    earlier = interrupted_prepare(seed, prepared, 17)
    earlier_hash = arrange(first=earlier)
    pending = arrange()
    run('prepare-witness-replaced', 'RESTORE_CHANGED', pending, swap=stale, **plan(1))
    run('prepare-prefix-changed-at-prompt', 'RESTORE_CHANGED', earlier_hash, before_key=change_header(earlier), **plan(1))
    arrange()
    run('prepare-completed-at-prompt', 'RESTORE_CHANGED', valid, before_key=change_header(prepared), **plan(1))

    def inject(name, rules):
        conf = work / (name + '.ini')
        conf.write_text(rules)
        return f'blkdebug:{conf}:{system}'

    fail_write = '[inject-error]\nevent = "write_aio"\niotype = "write"\nerrno = "5"\nonce = "on"\n'
    after_flush = '[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
    fail_read = '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nerrno = "5"\n'
    arrange()
    run('prepare-write-error', 'RESTORE_IO', pending, target=inject('prepare-write', fail_write),
        writes=('0x30',), **plan(1))
    for name, rules in (
            ('prepare-flush', '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nerrno = "5"\nonce = "on"\n'),
            ('prepare-readback', after_flush + fail_read + f'sector = "{lbas[0][0]}"\n'),
            ('prepare-allocation-recheck', after_flush + fail_read + f'sector = "{ROOT_LBA}"\n')):
        arrange()
        run(name + '-error', 'RESTORE_IO', valid, target=inject(name, rules), writes=WRITE_FLUSH, stored=512, **plan(1))

    # Kill the VM on LBA 0 after the preceding prepare header has reached disk.
    arrange()
    run('cut-after-durable-prepare', None, valid, target=inject('cut-after-prepare', fail_write + 'sector = "0"\n'),
        cut_on_source_error=True, prepare_checked=True, writes=(*WRITE_FLUSH, '0x30'), stored=512, **plan(1))
    run('cold-resume-after-prepare', 'JR_DONE', final_hash, key='y', mbr_changes=MBR_CHANGES,
        snapshot_lba=lbas[1][2], mbr_checked=True, snapshot_checked=True, writes=WRITE_FLUSH * 3, stored=1536)
    run('cold-after-prepare-repair', 'JR_INTACT', final_hash)
    if external != (sha256(start), sha256(carrier)):
        raise ValueError('Prepare-header recovery changed external media')
    return cases


def discard_cases(exe, bios, work, start, stale, system, carrier, lbas, records):
    seed, prepared, done = records
    old, new = prepared[512:1024], prepared[1024:]
    partial = torn_snapshot(prepared)
    pending = seed[:1024] + partial
    external = sha256(start), sha256(carrier)
    cases = []

    def arrange(first=pending, second=seed, live=old):
        return set_journal_pair(system, lbas, live, first, second)

    def run(name, outcome, expected, *, target=system, backup=carrier, slot=0, **options):
        cases.append(run_boot(exe, bios, work, 'en', start, target, backup, name, outcome, lbas[slot][2],
                              discard=True, slot='AB'[slot], **options))
        if sha256(system) != expected:
            raise ValueError(f'{name}: unexpected system disk contents')

    clean = arrange(seed)
    original = arrange()
    run('discard-missing-backup', 'RESTORE_BACKUP', original, backup=None)
    run('discard-different-system-disk', 'RESTORE_TARGET', original, serial=SECONDARY[2])
    run('discard-stale-witness-at-prompt', 'RESTORE_CHANGED', original, key='y', swap=stale)
    for name, first, second, live in (
            ('baseline-beside-new-live-mbr', seed, seed, new),
            ('discard-partly-updated-live', pending, seed, partial),
            ('discard-missing-peer', pending, bytes(1536), old),
            ('discard-damaged-seed-header', bytes(512) + pending[512:], seed, old),
            ('discard-advanced-peer', pending, done, old),
            ('discard-wrong-old-copy', seed[:512] + new + partial, seed, old),
            ('discard-reverse-snapshot', seed[:1024] + old[:450] + new[450:], seed, old),
            ('discard-unrelated-snapshot-byte', pending[:1024 + 100] + b'\xff' + pending[1024 + 101:], seed, old)):
        run(name, 'JR_BAD', arrange(first, second, live))

    # A formally valid baseline with different boot code would imply a
    # forbidden delta to the independently approved new MBR.
    foreign = bytes([old[0] ^ 1]) + old[1:]
    foreign_seed = seal(seed[:512] + foreign * 2)
    run('discard-protected-delta', 'JR_BAD', arrange(foreign_seed[:1024] + partial, foreign_seed, foreign))

    def finish_copy(q, _prompt):
        q.call('stop')
        write_at(system, lbas[0][2] * 512, new)
        q.call('cont')

    complete_copy = arrange(seed[:1024] + new)
    arrange()
    run('discard-snapshot-changed-at-prompt', 'RESTORE_CHANGED', complete_copy, key='y', before_key=finish_copy)
    arrange(seed, pending)
    run('discard-opposite-slot', 'JR_DISCARDED', clean, key='y', slot=1, writes=WRITE_FLUSH, stored=512)
    run('restart-after-opposite-discard', 'JR_BASELINE', clean)

    def inject(name, rules):
        conf = work / (name + '.ini')
        conf.write_text(rules)
        return f'blkdebug:{conf}:{system}'

    after_flush = '[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
    fail_read = '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nerrno = "5"\n'
    fail_write = ('[inject-error]\nevent = "write_aio"\niotype = "write"\nerrno = "5"\nonce = "on"\n'
                  f'sector = "{lbas[0][2]}"\n')
    arrange()
    run('discard-write-failed', 'RESTORE_IO', original, key='y', target=inject('discard-write', fail_write), writes=('0x30',))
    run('cut-during-discard', None, original, key='y', target=inject('cut-discard', fail_write),
        writes=('0x30',), cut_on_source_error=True)
    run('cold-retry-discard', 'JR_DISCARDED', clean, key='y', writes=WRITE_FLUSH, stored=512)
    run('cold-after-discard', 'JR_BASELINE', clean)
    for name, rules in (
            ('discard-flush', '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nerrno = "5"\nonce = "on"\n'),
            ('discard-readback', after_flush + fail_read + f'sector = "{lbas[0][2]}"\n'),
            ('discard-peer-recheck', after_flush + fail_read + f'sector = "{lbas[1][0]}"\n')):
        arrange()
        run(name + '-error', 'RESTORE_IO', clean, key='y', target=inject(name, rules), writes=WRITE_FLUSH, stored=512)
        run(name + '-restart', 'JR_BASELINE', clean)
    if external != (sha256(start), sha256(carrier)):
        raise ValueError('Discard changed the witness or the recovery disk')
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
    extents.update(record_extents(lbas[1], seed))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        work = Path(tmp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        system, carrier, fixed = work / 'system.raw', work / 'recovery.raw', work / 'complete.raw'
        witness, stale_witness, setup = capture_and_publish(exe, bios, src, work, system, carrier, size, extents,
                                                           new, primary=PRIMARY[2], secondary=SECONDARY[2], ids=IDS)
        old = prepared[512:1024]
        write_at(system, 0, old)
        write_at(system, lbas[0][0] * 512, seed[:512])
        write_at(system, lbas[0][2] * 512, torn_snapshot(prepared))
        baseline = work / 'baseline.raw'
        write_fixture(baseline, size, {**extents, 0: old, **record_extents(lbas[0], seed)})
        write_fixture(fixed, size, {**extents, 0: new, **record_extents(lbas[1], done)})
        bundle = repair_kit(work, system, carrier, size, witness, program=PROGRAM, kit=KIT, guide='JournalRecovery.txt',
                            ids=IDS, primary=PRIMARY, secondary=SECONDARY)
        manual = qualify_kit(exe, bios, work, bundle, system, baseline, lbas[0][2])
        floppy = work / 'en/English' / FLOPPY
        stale = work / 'stale.img'
        stale.write_bytes(floppy.read_bytes()[:WITNESS_START] + stale_witness)
        # Exercise the previous one-sector path on the same enrolled hardware.
        write_at(system, lbas[0][0] * 512, prepared[:512])
        write_at(system, lbas[0][2] * 512, new)
        write_at(system, 0, new)
        write_at(system, lbas[1][2] * 512, new)
        faults = fault_cases(exe, bios, work, floppy, stale, system, carrier, fixed, lbas, (seed, prepared, done))
        snapshots = snapshot_cases(exe, bios, work, floppy, system, carrier, fixed, lbas, (seed, prepared, done))
        prepared_cases = prepared_mbr_cases(exe, bios, work, floppy, stale, system, carrier, fixed,
                                            lbas, (seed, prepared, done))
        headers = prepare_header_cases(exe, bios, work, floppy, stale, system, carrier, fixed,
                                       lbas, (seed, prepared, done))
        unpublished = discard_cases(exe, bios, work, floppy, stale, system, carrier, lbas, (seed, prepared, done))
        results = dict(setup=setup, kit=manual, failures=faults, snapshots=snapshots, prepared=prepared_cases,
                       prepare_headers=headers, unpublished=unpublished, kit_sha256=sha256(bundle))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        bundle.replace(out / KIT)
    total = sum(map(len, (setup, manual, faults, snapshots, prepared_cases, headers, unpublished)))
    print(f'{total} boots passed: {out / KIT}')


if __name__ == '__main__':
    main()
