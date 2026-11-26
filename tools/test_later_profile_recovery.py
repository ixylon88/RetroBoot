"""Boot external rescue against interrupted later HDD profile switches and qualify the VirtualBox kit."""
from functools import partial
from pathlib import Path
import shutil
import struct
import zlib
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, write_fixture
from handoff_fixtures import IMAGE_BYTES
from mbr_boot import boot_fixture
from package_mbr_recovery import LANGS
from package_mbr_restore import (capture_and_publish, checked_build, compare_image, primary_write_check,
                                 repair_kit, write_at)
from prepare_mbr_target import WITNESS_START, prepare_pair
from rescue_text import load_catalog as rescue_text
from setup_toolchain import sha256
from test_backup_disk import CAPACITY
from test_dos_countdown import boot
from test_mbr_target import MODEL
from test_profile_menu import make_fixture, put
from test_profile_switch import change, cold, confirm, review, verify_raw
from test_profile_switch_recovery import profile_backup
from ui_text import load_catalog

PROGRAM = 'profile-recovery'
KIT = 'RetroBoot-Profilwechsel-Rettung.zip'
PRIMARY = ('RB91-System.vdi', '52429101-9810-42aa-8111-000011111111', 'VB52429101-11111111')
SECONDARY = ('RB91-Sicherung.vdi', '52429102-9810-42aa-8222-000022222222', 'VB52429102-22222222')
IDS = tuple(b'RB91-TEST-PAIR-' + bytes([i]) for i in (1, 2, 3))
WRITE_FLUSH = ('0x30', '0xe7')


def system_cut(exe, bios, work, disk, step, count):
    """A real HDD boot reaches exactly this prefix before a reported write error."""
    lbas = [at // SECTOR for at, _ in step.rows]
    fault = f'[inject-error]\nevent = "write_aio"\niotype = "write"\nsector = "{lbas[count]}"\nerrno = "5"\n'
    with boot(str(exe), bios, work, disk.raw, f'hdd-{step.sequence}-{count}', lbas[:count + 1], fault) as menu:
        ui = load_catalog('de')
        review(menu, disk, step, ui)
        menu.key('ret', 18)
        menu.expect(ui['SWITCH_IO'])


def prefix_image(path, step, count, torn=None):
    write_fixture(path, IMAGE_BYTES, step.before)
    put(path, dict(step.rows[:count]))
    if torn is not None:
        write_at(path, step.rows[count][0], torn)


def sector_at(path, offset):
    with path.open('rb') as source:
        source.seek(offset)
        return source.read(SECTOR)


class Rescue:
    def __init__(self, exe, bios, work, disk, step):
        self.exe, self.bios, self.work = exe, bios, work
        self.disk, self.step = disk, step
        self.carrier = work / 'recovery.raw'
        self.floppy = work / 'profile.img'
        self.old_slot = next(i for i in range(1, 5) if step.before[0][446 + 16 * (i - 1)])
        self.lbas = [at // SECTOR for at, _ in step.rows]
        if len(self.lbas) != 7:
            raise ValueError('A later profile switch must change seven distinct sectors')
        src = ROOT / 'build/rescue'
        self.witness, self.stale, _ = capture_and_publish(exe, bios, src, work, work / 'enroll.raw', self.carrier,
                IMAGE_BYTES, disk.extents, step.after[0], primary=PRIMARY[2], secondary=SECONDARY[2], ids=IDS,
                backup_file=partial(profile_backup, disk))
        base, _ = prepare_pair((src / (PROGRAM + '.img')).read_bytes(), MODEL, PRIMARY[2],
                               IMAGE_BYTES // SECTOR, *IDS, recovery=(MODEL, SECONDARY[2], CAPACITY))
        self.floppy.write_bytes(base[:WITNESS_START] + self.witness)
        self.manifests = {lang: checked_build(ROOT / 'build' / ('rescue' + suffix), PROGRAM)
                          for lang, suffix, _ in LANGS}

    def run(self, name, outcome, *, rows=(), live=None, undo=False, key=None, lang='en',
            target=None, carrier=None, floppy=None, fmt='raw', serial=PRIMARY[2],
            swap=None, before_key=None, commands=None, stored=None):
        ui = rescue_text(lang)
        lines = ['RB PROFILE RECOVERY', ui['RESTORE_CHECK']]
        if rows:
            lines += [ui['D_SERIAL'] + ' ' + PRIMARY[2], ui['STORE_REV'] + '2',
                      ui['PR_SEQUENCE'] + f'{self.step.sequence:08X}',
                      ui['PR_PROFILE'] + str(self.old_slot if undo else self.step.target),
                      ui['PR_UNDO' if undo else 'PR_FINISH']]
            if 3 in rows:
                lines.append(ui['JR_DELTA'])
                lines.extend(f'0x{i:04X}     {a:02X} -> {b:02X}'
                             for i, (a, b) in enumerate(zip(live, self.step.after[0])) if a != b)
            lines += [ui['PR_SECTORS'], *(f'0x{self.lbas[i]:08X}' for i in rows), ui['PR_CONFIRM']]
        success = outcome in ('PR_IDLE', 'PR_UNDONE', 'JR_DONE', 'RESTORE_CANCEL')
        lines += [ui[outcome], 'RB PROFILE RECOVERY ' + ('PASS' if success else 'BLOCKED')]
        keys = [(ui['PR_CONFIRM'], key, swap, True)] if key else []
        if commands is None:
            commands = WRITE_FLUSH * len(rows) if outcome in ('PR_UNDONE', 'JR_DONE') else ()
        if stored is None:
            stored = commands.count('0xe7') * SECTOR
        src = ROOT / 'build' / ('rescue' if lang == 'en' else 'rescue-de')
        fixture = dict(binary=(src / (PROGRAM + '.bin')).read_bytes(), memory=self.manifests[lang]['memory'][PROGRAM])
        boot_fixture(self.exe, self.bios, fixture, self.work, floppy or self.floppy, target or self.disk.raw, name,
                     lines, keys, [], [], readonly_start=True, ata_identity=(MODEL, serial),
                     disk_format=fmt, recovery_disk=carrier or self.carrier, recovery_format=fmt,
                     recovery_identity=(MODEL, SECONDARY[2]), before_key=before_key,
                     io_check=primary_write_check(name, [self.lbas[i] for i in rows[:commands.count('0x30')]],
                                                  commands, stored))
        print(name + ': ' + outcome, flush=True)


def campaign(r, previous, *, torn=True):
    disk, step, work = r.disk, r.step, r.work
    expected, prior, control = [work / (s + '.raw') for s in ('expected', 'prior', 'cut')]
    write_fixture(expected, IMAGE_BYTES, step.after)
    write_fixture(prior, IMAGE_BYTES, step.before)
    external = sha256(r.floppy), sha256(r.carrier)
    for count in range(8):
        if count < 7:
            write_fixture(disk.raw, IMAGE_BYTES, step.before)
            system_cut(r.exe, r.bios, work, disk, step, count)
        else:
            write_fixture(disk.raw, IMAGE_BYTES, step.after)
        prefix_image(control, step, count)
        verify_raw(disk.raw, control)
        if count in (0, 7):
            r.run(f'clean-{count}', 'PR_IDLE')
        else:
            undo = count == 1
            rows = [0] if undo else list(range(count, 7))
            r.run(f'cut-{count}', 'PR_UNDONE' if undo else 'JR_DONE', rows=rows, undo=undo,
                  live=sector_at(disk.raw, 0), key='y')
        verify_raw(disk.raw, prior if count < 2 else expected)
        cold(str(r.exe), r.bios, work, disk.raw, disk, previous if count < 2 else step, f'cold-{count}')

    if torn:
        for row, (offset, target) in enumerate(step.rows):
            prefix_image(disk.raw, step, row)
            old = sector_at(disk.raw, offset)
            changed = [i for i in range(SECTOR) if old[i] != target[i]]
            split = changed[0] + 1
            interrupted = target[:split] + old[split:]
            if interrupted in (old, target):
                raise ValueError('Ineffective sector tear')
            write_at(disk.raw, offset, interrupted)
            undo = row < 2
            rows = list(range(row, -1, -1)) if undo else list(range(row, 7))
            r.run(f'torn-{row}', 'PR_UNDONE' if undo else 'JR_DONE', rows=rows, undo=undo,
                  live=sector_at(disk.raw, 0), key='y')
            verify_raw(disk.raw, prior if undo else expected)
    if external != (sha256(r.floppy), sha256(r.carrier)):
        raise ValueError('Recovery changed independent media')


def failure_cases(r):
    step, disk = r.step, r.disk
    rows = list(range(3, 7))
    live = step.before[0]
    pending = r.work / 'pending.raw'
    prefix_image(pending, step, 3)
    prefix_image(disk.raw, step, 3)
    r.run('cancel', 'RESTORE_CANCEL', rows=rows, key='esc', live=live)
    verify_raw(disk.raw, pending)
    r.run('foreign-disk', 'RESTORE_TARGET', serial=SECONDARY[2])
    verify_raw(disk.raw, pending)
    stale = r.work / 'stale.img'
    stale.write_bytes(r.floppy.read_bytes()[:WITNESS_START] + r.stale)
    r.run('stale-witness', 'RESTORE_BACKUP', floppy=stale)
    r.run('swapped-witness', 'RESTORE_CHANGED', rows=rows, live=live, key='y', swap=stale)
    verify_raw(disk.raw, pending)
    for label, offset, outcome in (
            ('loader', 10, 'PR_BAD'), ('journal-padding', step.rows[2][0] + 111, 'PR_BAD'),
            ('wrong-order', step.rows[5][0] + 446, 'PR_BAD'),
            ('changed-vbr', disk.profiles[0]['start'] * SECTOR + 400, 'RESTORE_TARGET')):
        prefix_image(disk.raw, step, 3)
        value = sector_at(disk.raw, offset)[0] ^ 1
        write_at(disk.raw, offset, bytes([value]))
        before = sha256(disk.raw)
        r.run(label, outcome)
        if before != sha256(disk.raw):
            raise ValueError('Refused repair changed a disk')
    def replace(q, _):
        q.call('stop')
        write_at(disk.raw, 0, step.after[0])
        q.call('cont')
    prefix_image(disk.raw, step, 3)
    r.run('changed-at-prompt', 'RESTORE_CHANGED', rows=rows, key='y', live=live, before_key=replace)
    prefix_image(pending, step, 4)
    verify_raw(disk.raw, pending)
    for row in range(2, 7):
        prefix_image(disk.raw, step, 2)
        conf = r.work / f'rescue-write-{row}.ini'
        conf.write_text('[inject-error]\nevent = "write_aio"\niotype = "write"\nonce = "on"\n'
                        f'sector = "{r.lbas[row]}"\nerrno = "5"\n')
        r.run(f'repair-write-error-{row}', 'RESTORE_IO', rows=list(range(2, 7)), key='y', live=live,
              target=f'blkdebug:{conf}:{disk.raw}', commands=WRITE_FLUSH * (row - 2) + ('0x30',))
        prefix_image(pending, step, row)
        verify_raw(disk.raw, pending)
        r.run(f'repair-restart-{row}', 'JR_DONE', rows=list(range(row, 7)), key='y', live=sector_at(disk.raw, 0))
        prefix_image(pending, step, 7)
        verify_raw(disk.raw, pending)


    # The disk may already contain the requested MBR when its flush or
    # readback fails. A separate boot must recognize precisely that prefix.
    for label, rule in (
            ('flush', '[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nonce = "on"\nerrno = "5"\n'),
            ('readback', '[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
                         '[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nsector = "0"\nerrno = "5"\n')):
        prefix_image(disk.raw, step, 3)
        conf = r.work / (label + '.ini')
        conf.write_text(rule)
        r.run('repair-' + label, 'RESTORE_IO', rows=rows, live=live, key='y',
              target=f'blkdebug:{conf}:{disk.raw}', commands=WRITE_FLUSH, stored=SECTOR)
        prefix_image(pending, step, 4)
        verify_raw(disk.raw, pending)
        r.run('restart-' + label, 'JR_DONE', rows=[4, 5, 6], key='y')
        prefix_image(pending, step, 7)
        verify_raw(disk.raw, pending)

    # A power loss during the rollback can leave old/new/old bytes in
    # the unfinished snapshot, or an old prefix and new suffix in row 0.
    for row in (1, 0):
        prefix_image(disk.raw, step, row)
        offset, new = step.rows[row]
        old = sector_at(disk.raw, offset)
        differences = [i for i in range(SECTOR) if old[i] != new[i]]
        lower = differences[0] + 1
        upper = differences[-1] if row else SECTOR
        actual = old[:lower] + new[lower:upper] + old[upper:]
        if actual in (old, new):
            raise ValueError('Ineffective interrupted rollback')
        write_at(disk.raw, offset, actual)
        r.run(f'rollback-restart-{row}', 'PR_UNDONE', rows=list(range(row, -1, -1)),
              undo=True, key='y')
        prefix_image(pending, step, 0)
        verify_raw(disk.raw, pending)

    prefix_image(disk.raw, step, 3)
    offset = step.rows[-1][0]
    header = bytearray(sector_at(disk.raw, offset))
    struct.pack_into('<I', header, 16, step.sequence + 1)
    struct.pack_into('<I', header, 508, zlib.crc32(header[:508]))
    write_at(disk.raw, offset, header)
    before = sha256(disk.raw)
    r.run('sequence-gap', 'PR_BAD')
    if before != sha256(disk.raw):
        raise ValueError('Incompatible generations changed the disk')


def manual_kit(r):
    step, disk, work = r.step, r.disk, r.work
    prefix_image(disk.raw, step, 3)
    bundle = repair_kit(work, disk.raw, r.carrier, IMAGE_BYTES, r.witness, program=PROGRAM, kit=KIT,
                        guide='LaterProfileRecovery.txt', ids=IDS, primary=PRIMARY, secondary=SECONDARY)
    fixed = work / 'fixed.raw'
    write_fixture(fixed, IMAGE_BYTES, step.after)
    for lang, _, directory in LANGS:
        dest = work / ('unpacked-' + lang)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(dest)
        floppy, system, backup = dest / directory / (PROGRAM + '.img'), dest / PRIMARY[0], dest / SECONDARY[0]
        external = sha256(floppy), sha256(backup)
        args = dict(lang=lang, floppy=floppy, target=system, carrier=backup, fmt='vdi')
        r.run(lang + '-kit-cancel', 'RESTORE_CANCEL', rows=list(range(3, 7)), live=step.before[0], key='esc', **args)
        compare_image(disk.raw, system)
        r.run(lang + '-kit-repair', 'JR_DONE', rows=list(range(3, 7)), live=step.before[0],
              key=rescue_text(lang)['A_YES'].lower(), **args)
        compare_image(fixed, system)
        r.run(lang + '-kit-restart', 'PR_IDLE', **args)
        compare_image(fixed, system)
        cold(str(r.exe), r.bios, work, system, disk, step, lang + '-kit-hdd-p1')
        if external != (sha256(floppy), sha256(backup)):
            raise ValueError('Packaged recovery media changed')
    return bundle


def run():
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    destination = ROOT / 'build/profile-recovery'
    destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        disk = make_fixture(work, ROOT / 'build/hdd-de', 'de', 1)
        previous = change(disk, disk.extents, 2, 2, 1)
        with boot(str(exe), bios, work, disk.raw, 'normal-first-switch', [at // SECTOR for at, _ in previous.rows]) as menu:
            review(menu, disk, previous, load_catalog('de'))
            confirm(menu, disk, previous)
        expected = work / 'first.raw'
        write_fixture(expected, IMAGE_BYTES, previous.after)
        verify_raw(disk.raw, expected)
        step = change(disk, previous.after, 1, 3, 1)
        rescue = Rescue(exe, bios, work, disk, step)
        campaign(rescue, previous)
        failure_cases(rescue)
        bundle = manual_kit(rescue)
        # The other committed slot, a third target, and the last usable
        # 32-bit sequence exercise the same firmware against a different history.
        three = make_fixture(work, ROOT / 'build/hdd-de', 'de', 1, 3)
        prior = change(three, three.extents, 2, 0xfffffffe, 0)
        last = change(three, prior.after, 3, 0xffffffff, 0)
        other = Rescue(exe, bios, work, three, last)
        campaign(other, prior)
        unapproved = change(three, prior.after, 1, 0xffffffff, 0)
        prefix_image(three.raw, unapproved, 3)
        before = sha256(three.raw)
        other.run('different-intended-profile', 'PR_BAD')
        if sha256(three.raw) != before:
            raise ValueError('A different intended MBR authorized a write')
        prefix_image(three.raw, last, 7)
        write_at(three.raw, last.rows[0][0], last.after[0])
        before = sha256(three.raw)
        other.run('exhausted-sequence', 'PR_BAD')
        if sha256(three.raw) != before:
            raise ValueError('Exhausted journal sequence authorized a write')
        bundle.replace(destination / KIT)
        print(f'{KIT} {sha256(destination / KIT)}', flush=True)


if __name__ == '__main__':
    run()
