"""Apply the reviewed visibility change from the HDD menu and verify every guest sector write."""
import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import uuid
import zipfile

import config_records
import journal_records
from build_hdd import ROOT, SECTOR, write_fixture
from handoff_fixtures import IMAGE_BYTES
from package_mbr_recovery import set_fixture_identity
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from test_profile_menu import install_view, make_fixture, preview, put
from ui_text import LANGUAGES, load_catalog, output_name


@dataclass
class Switch:
    rows: list
    before: dict
    after: dict
    target: int
    sequence: int


def change(disk, before, active, sequence, prepare):
    """Independent journal encoder and sector-by-sector expected disk state."""
    after = dict(before)
    mbr = install_view(before[0], len(disk.profiles), active)
    record = dict(**disk.binding, before=before[0], after=mbr, sequence=sequence, capacity=IMAGE_BYTES // SECTOR)
    rows = []
    for slot, phase in ((prepare, journal_records.PREPARED), (1 - prepare, journal_records.COMMITTED)):
        if phase == journal_records.COMMITTED:
            rows.append((0, mbr))
            after[0] = mbr
        offset = disk.journal_at[slot]
        new = journal_records.encode(**record, phase=phase)
        for index in (1, 2, 0):
            sector = slice(index * SECTOR, (index + 1) * SECTOR)
            if before[offset][sector] != new[sector]:
                rows.append((offset + index * SECTOR, new[sector]))
        after[offset] = new
    return Switch(rows, before, after, active, sequence)


def package(work, language, disk, *, mixed=False):
    names = ('RetroBoot-Umschaltung-DE.zip', 'RetroBoot-Wechsel.vdi') if language == 'de' else (
             'RetroBoot-Partition-Switch-EN.zip', 'RetroBoot-Switch.vdi')
    fixture_id = 'switch-' + language
    if mixed:
        names = (f'RetroBoot-FAT16-FAT32-{language.upper()}.zip', 'RetroBoot-FAT16-FAT32.vdi')
        fixture_id = 'mixed-fat-' + language
    image = work / names[1]
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', disk.raw, image], check=True)
    identity = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/ixylon88/RetroBoot/fixtures/' + fixture_id)
    set_fixture_identity(image, str(identity), IMAGE_BYTES // SECTOR)
    archive = work / names[0]
    with zipfile.ZipFile(archive, 'x') as bundle:
        bundle.writestr(zipfile.ZipInfo(image.name), image.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(archive) as bundle:
        delivered = Path(bundle.extract(image.name, work / 'delivered'))
    compare(delivered, disk.raw)
    return archive, delivered


def select(menu, target):
    for _ in range(target - 1):  # Both supplied records initially highlight P1.
        menu.key('down', 0)


def review(menu, disk, step, ui):
    active = next(i for i in range(1, len(disk.profiles) + 1) if step.before[0][446 + (i - 1) * 16])
    select(menu, step.target)
    menu.key('ret', 8)
    preview(menu, ui, active, step.target, disk)
    menu.expect(ui['SWITCH_HELP'])
    menu.key('s', 17)
    menu.expect(ui['SWITCH_CONFIRM'])
    menu.expect(f'0x{step.sequence:08X}')
    preview(menu, ui, active, step.target, disk)


def confirm(menu, disk, step):
    menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 20})
    menu.wait(f'Test VBR P{step.target} OK.')
    menu.expect('RB HANDOFF PASS')
    offset = 446 + (step.target - 1) * 16
    vbr = disk.extents[disk.profiles[step.target - 1]['start'] * SECTOR]
    if menu.memory(0x800, 16) != step.after[0][offset:offset + 16] or menu.memory(0x7c00, 512) != vbr:
        raise ValueError('Handoff differs from the checked target boot sector or new primary entry')


def cold(qemu, bios, work, image, disk, step, name):
    with boot(qemu, bios, work, image, name) as menu:
        select(menu, step.target)
        confirm(menu, disk, step)


def verify_raw(actual, expected):
    subprocess.run(['qemu-img', 'compare', '-q', '-f', 'raw', '-F', 'raw', actual, expected], check=True)


def blocked_cold(qemu, bios, work, raw, name, target, ui):
    with boot(qemu, bios, work, raw, name) as menu:
        if any('DOS-Test P' in row for row in menu.screen()):
            select(menu, target)
            menu.key('ret', 12)
            menu.expect(ui['DOS_BASELINE'])
        else:
            # A torn table may already fail partition/configuration validation.
            menu.expect(ui['NO_PROFILES'])
            menu.key('ret', 1)
        if 'RB HANDOFF' in menu.log.read_text():
            raise ValueError(name + ': ambiguous cold handoff')


def readback_fault(n, lba):
    # Advance the block driver's state once per physical write. Only the
    # readback of write n fails, so the actual bytes have already changed.
    states = ''.join(f'[set-state]\nevent = "write_aio"\nstate = "{i}"\nnew_state = "{i+1}"\n'
                     for i in range(1, n + 1))
    return states + (f'[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "{n + 1}"\n'
                     f'sector = "{lba}"\nerrno = "5"\n')


def fault_campaign(qemu, bios, work, disk, step, ui):
    raw, expected, backup, restored = [work / name for name in ('fault.img', 'expected.img', 'backup.vdi', 'restored.img')]
    write_fixture(raw, IMAGE_BYTES, step.before)
    # Keep an independent, powered-off backup for the currently settled generation.
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, backup], check=True)
    backup_hash = sha256(backup)
    lbas = [at // SECTOR for at, data in step.rows]
    for index, lba in enumerate(lbas):
        write_fixture(raw, IMAGE_BYTES, step.before)
        fault = f'[inject-error]\nevent = "write_aio"\niotype = "write"\nsector = "{lba}"\nerrno = "5"\n'
        case = f'seq{step.sequence}-cut-{index + 1}'
        with boot(qemu, bios, work, raw, case, lbas[:index + 1], fault) as menu:
            review(menu, disk, step, ui)
            menu.key('ret', 18)
            menu.expect(ui['SWITCH_IO'])
            if 'RB HANDOFF' in menu.log.read_text():
                raise ValueError(case + ': boot after failed write')
        write_fixture(expected, IMAGE_BYTES, step.before)
        put(expected, dict(step.rows[:index]))
        verify_raw(raw, expected)
        if index:
            blocked_cold(qemu, bios, work, raw, case + '-cold', step.target, ui)

        write_fixture(raw, IMAGE_BYTES, step.before)
        with boot(qemu, bios, work, raw, case + '-readback', lbas[:index + 1],
                  readback_fault(index + 1, lba)) as menu:
            review(menu, disk, step, ui)
            menu.key('ret', 18)
            menu.expect(ui['SWITCH_IO'])
            if 'RB HANDOFF' in menu.log.read_text():
                raise ValueError(case + ': boot after failed readback')
        at, new = step.rows[index]
        with expected.open('rb') as stream:
            stream.seek(at)
            old = stream.read(SECTOR)
        put(expected, {at: new})
        verify_raw(raw, expected)
        if index + 1 == len(lbas):
            cold(qemu, bios, work, raw, disk, step, case + '-committed-cold')

        # Synthesize a distinct prefix tear from the observed complete sector.
        split = next(i for i in range(1, SECTOR) if old[:i] != new[:i] and old[i:] != new[i:])
        put(raw, {at: new[:split] + old[split:]})
        blocked_cold(qemu, bios, work, raw, case + '-torn', step.target, ui)
        # The recovery source is independent of the damaged MBR and journals.
        subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', backup, restored], check=True)
        write_fixture(expected, IMAGE_BYTES, step.before)
        verify_raw(restored, expected)
        previous = next(p['slot'] for p in disk.profiles if step.before[0][446 + 16 * (p['slot'] - 1)])
        cold(qemu, bios, work, restored, disk, Switch([], {}, step.before, previous, 0), case + '-restored')
    if sha256(backup) != backup_hash:
        raise ValueError('External backup changed during recovery')


def run(language, qemu, bios):
    directory = ROOT / 'build' / output_name('hdd', language)
    ui = load_catalog(language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        disk = make_fixture(work, directory, language, 1)
        bundle, image = package(work, language, disk)
        forward = change(disk, disk.extents, 2, 2, 1)
        backward = change(disk, forward.after, 1, 3, 1)
        if [len(step.rows) for step in (forward, backward)] != [5, 7]:
            raise ValueError('Unexpected reference sector schedule')
        with boot(qemu, bios, work, image, 'preview-and-cancel') as menu:
            menu.key('f7', 8)
            menu.key('right', 8)
            menu.key('s', 8)
            menu.key('ret', 8)
            menu.key('esc', 0)
            review(menu, disk, forward, ui)
            menu.key('esc', 0)
        compare(image, disk.raw)
        expected = work / 'expected.img'
        for step in (forward, backward):
            with boot(qemu, bios, work, image, f'switch-{step.sequence}', [at // SECTOR for at, _ in step.rows]) as menu:
                review(menu, disk, step, ui)
                confirm(menu, disk, step)
            write_fixture(expected, IMAGE_BYTES, step.after)
            compare(image, expected)
            cold(qemu, bios, work, image, disk, step, f'seq{step.sequence}-cold-start')
            compare(image, expected)

        # A completed transaction can reside in either slot.
        three = make_fixture(work, directory, language, 2, 3)
        third = change(three, three.extents, 3, 3, 0)
        with boot(qemu, bios, work, three.raw, 'other-slot-p3', [at // SECTOR for at, _ in third.rows]) as menu:
            review(menu, three, third, ui)
            confirm(menu, three, third)
        write_fixture(expected, IMAGE_BYTES, third.after)
        verify_raw(three.raw, expected)

        cfg = config_records.encode(**disk.binding, profiles=disk.profiles, language=language,
                                    generation=2, default_id=disk.profiles[0]['id'], countdown=1)
        admin = disk.binding['admin_start']
        spf = struct.unpack_from('<H', disk.extents[admin * SECTOR], 22)[0]
        root = (admin + 1 + 2 * spf) * SECTOR
        vbr = disk.profiles[1]['start'] * SECTOR
        for case, changes in (
            ('config', {at: cfg for at in disk.config_at}),
            ('directory', {root + 22: b'\x01'}),
            ('vbr', {vbr + 509: bytes([disk.extents[vbr][509] ^ 1])}),
            ('journal', {disk.journal_at[1] + 508: bytes([disk.extents[disk.journal_at[1]][508] ^ 1])}),
            ('mbr', {440: b'\x10'}),
        ):
            write_fixture(disk.raw, IMAGE_BYTES, disk.extents)
            with boot(qemu, bios, work, disk.raw, 'stale-' + case) as menu:
                review(menu, disk, forward, ui)
                menu.qmp.call('stop')
                put(disk.raw, changes)
                menu.qmp.call('cont')
                menu.key('ret', 18)
                menu.expect(ui['SWITCH_CHANGED'])
        # A valid previous transaction at the maximum sequence can still boot its own profile.
        maximum = change(disk, disk.extents, 2, 0xffffffff, 1)
        write_fixture(disk.raw, IMAGE_BYTES, maximum.after)
        with boot(qemu, bios, work, disk.raw, 'sequence-exhausted') as menu:
            menu.key('ret', 8)
            menu.key('s', 18)
            menu.expect(ui['SWITCH_FULL'])

        for step in (forward, backward):
            fault_campaign(qemu, bios, work, disk, step, ui)
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
