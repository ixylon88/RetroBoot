"""Cold-boot the released multi-profile disks and check each read-only Enter action."""
import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import uuid
import zipfile
import zlib

import config_records
import journal_records
import state_records
from build_hdd import ROOT, SECTOR, fixture, write_fixture
from handoff_fixtures import DISK_ID, IMAGE_BYTES, entry_bytes
from package_mbr_recovery import set_fixture_identity
from prepare_dos_disk import partition
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from ui_text import LANGUAGES, load_catalog, output_name
from volume_fixtures import header


def install_view(mbr, count, active):
    table = bytearray(mbr)
    for index in range(count):
        offset = 446 + index * 16
        table[offset] = 0x80 if index + 1 == active else 0
        base = mbr[offset + 4] & ~0x10
        table[offset + 4] = base if index + 1 == active else base | 0x10
    return bytes(table)


@dataclass
class Disk:
    raw: Path
    extents: dict
    profiles: list
    binding: dict
    config_at: list
    state_at: list
    journal_at: list


def empty_filesystem(extents, start, vbr, bits, label):
    """Initialize both FATs and the root label on the owned mixed-volume fixture."""
    reserved = struct.unpack_from('<H', vbr, 14)[0]
    if bits == 32:
        fat_size = struct.unpack_from('<I', vbr, 36)[0]
        fat = struct.pack('<III', 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)
        info = bytearray(SECTOR)
        struct.pack_into('<I', info, 0, 0x41615252)
        struct.pack_into('<III', info, 484, 0x61417272, 0xFFFFFFFF, 0xFFFFFFFF)
        struct.pack_into('<I', info, 508, 0xAA550000)
        continuation = bytes(510) + b'\x55\xaa'
        for offset, sector in ((1, info), (2, continuation), (6, vbr), (7, info), (8, continuation)):
            extents[(start + offset) * SECTOR] = bytes(sector)
    else:
        fat_size = struct.unpack_from('<H', vbr, 22)[0]
        fat = struct.pack('<HH', 0xFFF8, 0xFFFF)
    for copy in range(2):
        extents[(start + reserved + copy * fat_size) * SECTOR] = fat.ljust(SECTOR, b'\0')
    extents[(start + reserved + 2 * fat_size) * SECTOR] = (label + b'\x08').ljust(SECTOR, b'\0')


def make_fixture(work, directory, language, active, count=2, *, mixed=False):
    parts = {name: (directory / (name + '.bin')).read_bytes() for name in ('mbr', 'vbr', 'bootstrap')}
    parts['stage2'] = (directory / 'stage2-dos.bin').read_bytes()
    _, extents = fixture(parts, 'mixed-profiles' if mixed else 'retroboot-hdd', language)
    message = b'Test VBR reached.'
    profiles, installations = [], []
    table = bytearray(extents[0])
    starts = (100800, 108864, 181440) if mixed else (131072, 140000, 150000)
    for slot, start in enumerate(starts[:count], 1):
        bits = 32 if mixed and slot > 1 else 16
        base = 0x0B if bits == 32 else 0x06
        name = 'handoff-fat32-vbr.bin' if bits == 32 else 'handoff-vbr.bin'
        template = (directory / name).read_bytes()
        if len(template) != SECTOR or template.count(entry_bytes()) != 1 or template.count(message) != 1:
            raise ValueError('Unexpected handoff test sector')
        vbr = bytearray(template)
        if bits == 32:
            vbr[3:90] = header(32, start)[3:90]
        sectors = struct.unpack_from('<I', vbr, 32)[0]
        offset = 446 + (slot - 1) * 16
        entry = bytearray(partition(base, start, sectors, start, 16, 63))
        entry[0] = 0x80
        table[offset:offset + 16] = entry
        banner = f'Test VBR P{slot} OK.'.encode('ascii').ljust(len(message))
        vbr = vbr.replace(entry_bytes(), bytes(entry)).replace(message, banner)
        struct.pack_into('<HHI', vbr, 24, 63, 16, start)
        if mixed:
            label = f'RB FAT{bits} P{slot}'.encode('ascii')
            label_at = 71 if bits == 32 else 43
            vbr[label_at:label_at + 11] = label
            if bits == 32:
                struct.pack_into('<BBBI', vbr, 64, 0x80, 0, 0x29, 0x52424600 + slot)
                vbr[82:90] = b'FAT32   '
            empty_filesystem(extents, start, vbr, bits, label)
        extents[start * SECTOR] = bytes(vbr)
        target = dict(install_id=config_records.TEST_INSTALL_ID + slot, slot=slot,
                      start=start, sectors=sectors, type=base, kind=1)
        title = f'FAT{bits}-Test P{slot}' if mixed else f'DOS-Test P{slot}'
        profiles.append(dict(target, id=100 + slot, name=title, installed=2, approved=1))
        installations.append(dict(target, phase=6, vbr_crc=zlib.crc32(vbr)))

    before = install_view(table, count, 1)
    extents[0] = install_view(table, count, active)
    admin = struct.unpack_from('<I', table, 436)[0]
    vbr = extents[admin * SECTOR]
    binding = dict(disk_id=DISK_ID, layout=config_records.layout_crc(extents), admin_start=admin,
                   admin_sectors=struct.unpack_from('<I', vbr, 32)[0], media_id=config_records.FIXTURE_MEDIA_ID)
    data_lba = admin + 1 + 2 * struct.unpack_from('<H', vbr, 22)[0] + 32

    def offsets(clusters):
        return [(data_lba + (cluster - 2) * vbr[13]) * SECTOR for cluster in clusters]

    raw = work / f'profile-{count}-p{active}.img'
    disk = Disk(raw, extents, profiles, binding, offsets(config_records.CLUSTERS),
                offsets(config_records.STATE_CLUSTERS), offsets(journal_records.CLUSTERS))
    for at in disk.config_at:
        extents[at] = config_records.encode(**binding, profiles=profiles, language=language,
                                            default_id=profiles[0]['id'], countdown=1)
    for at in disk.state_at:
        extents[at] = state_records.encode(**binding, installations=list(reversed(installations)))
    for copy, at in enumerate(disk.journal_at):
        phase = journal_records.EMPTY if active == 1 else (journal_records.PREPARED, journal_records.COMMITTED)[copy]
        extents[at] = journal_records.encode(**binding, before=before, after=extents[0],
                  sequence=1 if active == 1 else 2, phase=phase, capacity=IMAGE_BYTES // SECTOR)
    write_fixture(raw, IMAGE_BYTES, extents)
    return disk


def package(work, disks, language):
    name = 'RetroBoot-Profilauswahl-DE.zip' if language == 'de' else 'RetroBoot-Profile-Selection-EN.zip'
    images = [(disk, f'RetroBoot-P{active}.vdi', f'profile-{language}-p{active}')
              for active, disk in enumerate(disks, 1)]
    return package_disks(work, name, images)


def package_disks(work, name, images):
    """Package each raw disk under a stable VDI identity and compare its extracted bytes."""
    bundle = work / name
    with zipfile.ZipFile(bundle, 'x') as archive:
        for disk, filename, fixture_id in images:
            vdi = work / filename
            subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', disk.raw, vdi], check=True)
            identity = uuid.uuid5(uuid.NAMESPACE_URL,
                'https://github.com/ixylon88/RetroBoot/fixtures/' + fixture_id)
            set_fixture_identity(vdi, str(identity), IMAGE_BYTES // SECTOR)
            archive.writestr(zipfile.ZipInfo(vdi.name), vdi.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        delivered = [Path(archive.extract(name, work / 'delivered')) for name in archive.namelist()]
    for image, (disk, _, _) in zip(delivered, images, strict=True):
        compare(image, disk.raw)
    return bundle, delivered


def handoff(menu, disk, slot):
    menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 20})
    menu.wait(f'Test VBR P{slot} OK.')
    menu.expect('RB HANDOFF PASS')
    menu.expect(f'Test VBR P{slot} OK.')
    start = disk.profiles[slot - 1]['start']
    offset = 446 + (slot - 1) * 16
    if (menu.memory(0x7c00, 512) != disk.extents[start * SECTOR]
            or menu.memory(0x800, 16) != disk.extents[0][offset:offset + 16]):
        raise ValueError(f'P{slot} handoff used different VBR or partition bytes')


def preview(menu, ui, active, selected, disk):
    menu.expect(ui['VIS_CHANGE'])
    menu.expect(disk.profiles[selected - 1]['name'])
    rows = menu.screen()
    for slot, profile in enumerate(disk.profiles, 1):
        visible = (f"0x{profile['type']:02X}", '0x80')
        hidden = (f"0x{profile['type'] + 0x10:02X}", '0x00')
        current = visible if slot == active else hidden
        wanted = visible if slot == selected else hidden
        row = rows[10 + slot]
        if (row[17:21], row[25:29], row[45:49], row[53:57]) != current + wanted:
            raise ValueError(f'Incorrect visibility plan for P{slot}: {row}')
    changed = (1 << (active - 1)) | (1 << (selected - 1))
    if rows[17][30:34] != f'0x{changed:02X}':
        raise ValueError('Unexpected visibility change mask')


def put(raw, changes):
    with raw.open('r+b') as stream:
        for offset, data in changes.items():
            stream.seek(offset)
            stream.write(data)


def run(language, qemu, bios):
    ui = load_catalog(language)
    directory = ROOT / 'build' / output_name('hdd', language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        disks = [make_fixture(work, directory, language, slot) for slot in (1, 2)]
        bundle, delivered = package(work, disks, language)
        for active, (disk, image) in enumerate(zip(disks, delivered), 1):
            hidden = 3 - active
            with boot(qemu, bios, work, image, f'profile-p{active}-cold') as menu:
                menu.expect(ui['AUTO_OFF'])
                menu.expect(ui['PROFILE_MENU_HELP'])
                time.sleep(1.3)  # The configured single-profile countdown would have expired.
                for profile in disk.profiles:
                    menu.expect(profile['name'])
                menu.key('f9', 0)
                menu.key('v', 0)
                if hidden == 2:
                    menu.key('down', 0)
                menu.key('f6', 7)
                menu.expect(f'DOS-Test P{hidden}')
                menu.expect(ui['STATE_MATCH'])
                menu.key('esc', 0)
                menu.key('ret', 8)
                preview(menu, ui, active, hidden, disk)
                menu.key('ret', 8)
                menu.key('f7', 8)
                preview(menu, ui, active, hidden, disk)
                menu.key('esc', 0)
                menu.key('up' if active == 1 else 'down', 0)
                handoff(menu, disk, active)
            compare(image, disk.raw)

        three = make_fixture(work, directory, language, 3, 3)
        with boot(qemu, bios, work, three.raw, 'three-profiles') as menu:
            for profile in three.profiles:
                menu.expect(profile['name'])
            menu.key('ret', 8)
            preview(menu, ui, 3, 1, three)
            menu.key('esc', 0)
            menu.key('down', 0)
            menu.key('down', 0)
            handoff(menu, three, 3)

        disk = disks[0]
        def cfg(profiles, default=None):
            return config_records.encode(**disk.binding, profiles=profiles, language=language, generation=2,
                                         default_id=disk.profiles[0]['id'] if default is None else default, countdown=1)

        second = disk.profiles[1]
        second_default = cfg(disk.profiles, default=second['id'])
        put(disk.raw, {at: second_default for at in disk.config_at})
        with boot(qemu, bios, work, disk.raw, 'second-profile-default') as menu:
            menu.expect(ui['AUTO_OFF'])
            menu.key('f5', 6)
            menu.expect(second['name'])
            menu.key('esc', 0)
            menu.key('ret', 8)
            preview(menu, ui, 1, 2, disk)
        put(disk.raw, {at: disk.extents[at] for at in disk.config_at})

        hidden_at = second['start'] * SECTOR
        corrupt = bytearray(disk.extents[hidden_at])
        corrupt[509] ^= 1
        with boot(qemu, bios, work, disk.raw, 'hidden-vbr-changed') as menu:
            menu.key('down', 0)
            menu.qmp.call('stop')
            put(disk.raw, {hidden_at: corrupt})
            menu.qmp.call('cont')
            menu.key('ret', 12)
            menu.expect(ui['STATE_VBR'])
        put(disk.raw, {hidden_at: disk.extents[hidden_at]})

        reordered = cfg(disk.profiles[::-1])
        original = disk.profiles[0]
        renamed = cfg([dict(original, name='Changed P1'), disk.profiles[1]])
        replaced = cfg([dict(original, id=201), disk.profiles[1]], default=201)
        sector_at = original['start'] * SECTOR
        bad_vbr = bytearray(disk.extents[sector_at])
        bad_vbr[509] ^= 1
        journal_at = disk.journal_at[0]
        bad_journal = bytearray(disk.extents[journal_at])
        bad_journal[508] ^= 1
        state = bytearray(disk.extents[disk.state_at[0]])
        state[83] = 5  # P2, first in the installation records. Hold the whole disk.
        state[84:88] = bytes(4)
        pending = config_records.seal(state)
        cases = (
            ('reordered', {at: reordered for at in disk.config_at}, None),
            ('renamed', {at: renamed for at in disk.config_at}, 'PROFILE_TEST_SELECTION'),
            ('replaced-id', {at: replaced for at in disk.config_at}, 'PROFILE_TEST_SELECTION'),
            ('vbr', {sector_at: bad_vbr}, 'STATE_VBR'),
            ('pending-peer', {at: pending for at in disk.state_at}, 'STATE_PENDING'),
            ('damaged-journal', {journal_at: bad_journal}, 'DOS_BASELINE'),
            ('incomplete-switch', {disk.journal_at[1]: disks[1].extents[journal_at]}, 'DOS_BASELINE'),
            ('different-cold-mbr', {at: disks[1].extents[at] for at in (0, *disk.journal_at)}, 'DOS_BASELINE'),
        )
        for case, changes, message in cases:
            with boot(qemu, bios, work, disk.raw, 'profile-' + case) as menu:
                menu.expect(original['name'])
                menu.qmp.call('stop')
                put(disk.raw, changes)
                menu.qmp.call('cont')
                if message:
                    menu.key('ret', 12)
                    menu.expect(ui[message])
                    if 'RB HANDOFF' in menu.log.read_text():
                        raise ValueError('Handoff after ' + case)
                else:
                    handoff(menu, disk, 1)
            put(disk.raw, {at: disk.extents[at] for at in changes})
        for case, changes, message in (
            ('pending-at-boot', {at: pending for at in disk.state_at}, 'TRIAL_PENDING'),
            ('duplicate-slot', {at: cfg([original, dict(original, id=202)]) for at in disk.config_at}, 'NO_PROFILES'),
        ):
            put(disk.raw, changes)
            with boot(qemu, bios, work, disk.raw, 'profile-' + case) as menu:
                menu.expect(ui[message])
                if any('DOS-Test P' in row for row in menu.screen()):
                    raise ValueError('Exposed a profile on ' + case)
                menu.key('ret', 1)
            put(disk.raw, {at: disk.extents[at] for at in changes})
        compare(delivered[0], disk.raw)
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
