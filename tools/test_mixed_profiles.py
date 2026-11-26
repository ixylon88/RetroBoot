"""Qualify the shipped CHS FAT16/FAT32 disk through its normal BIOS menu."""
import argparse
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

import config_records
import state_records
from build_hdd import ROOT, SECTOR, write_fixture
from handoff_fixtures import IMAGE_BYTES
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from test_profile_menu import make_fixture, put
from test_profile_switch import Switch, change, cold, confirm, package, review
from ui_text import LANGUAGES, load_catalog, output_name


def check_volumes(disk):
    """Check the actual disk ranges, both complete FATs, boot copies and root directories."""
    with disk.raw.open('rb') as source:
        def read(lba, count=1):
            source.seek(lba * SECTOR)
            return source.read(count * SECTOR)

        for profile in disk.profiles:
            start, length, slot = profile['start'], profile['sectors'], profile['slot']
            boot_sector = read(start)
            reserved = int.from_bytes(boot_sector[14:16], 'little')
            if slot == 1:
                fat_size = int.from_bytes(boot_sector[22:24], 'little')
                root_sectors = 32
                entries = struct.pack('<HH', 0xFFF8, 0xFFFF)
            else:
                fat_size = int.from_bytes(boot_sector[36:40], 'little')
                root_sectors = 0
                entries = struct.pack('<III', 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)
                if (struct.unpack_from('<IHH', boot_sector, 44) != (2, 1, 6)
                        or read(start, 3) != read(start + 6, 3)
                        or read(start + 2)[510:] != b'\x55\xaa'
                        or struct.unpack_from('<I', read(start + 1))[0] != 0x41615252
                        or struct.unpack_from('<I', read(start + 1), 484)[0] != 0x61417272
                        or read(start + 1)[508:] != b'\0\0\x55\xaa'):
                    raise ValueError(f'Invalid FAT32 boot region in P{slot}')
            clusters = (length - reserved - 2 * fat_size - root_sectors) // boot_sector[13]
            if (boot_sector[16] != 2 or not 4085 <= clusters
                    or (clusters >= 65525) != (slot != 1)
                    or struct.unpack_from('<II', boot_sector, 28) != (start, length)):
                raise ValueError(f'Unexpected BPB or cluster count in P{slot}')
            expected = entries.ljust(fat_size * SECTOR, b'\0')
            first = start + reserved
            if read(first, fat_size) != expected or read(first + fat_size, fat_size) != expected:
                raise ValueError(f'Incorrect FAT allocation in P{slot}')
            label = f'RB FAT{16 if slot == 1 else 32} P{slot}'.encode('ascii')
            root = read(first + 2 * fat_size, root_sectors or boot_sector[13])
            if root != (label + b'\x08').ljust(len(root), b'\0'):
                raise ValueError(f'Unexpected root directory in P{slot}')


def refusals(qemu, bios, work, disk, first, ui, language):
    start = disk.profiles[1]['start'] * SECTOR
    with boot(qemu, bios, work, disk.raw, 'mixed-stale-after-review') as menu:
        review(menu, disk, first, ui)
        menu.qmp.call('stop')
        put(disk.raw, {start + 400: bytes([disk.extents[start][400] ^ 1])})
        menu.qmp.call('cont')
        menu.key('ret', 18)
        menu.expect(ui['SWITCH_CHANGED'])

    # Both state copies approve the CRC of this deliberately wrong-family BPB.
    # Cluster arithmetic must still reject it before the switch review.
    invalid = bytearray(disk.extents[start])
    invalid[13] = 2
    installations = []
    for profile in disk.profiles:
        sector = invalid if profile['slot'] == 2 else disk.extents[profile['start'] * SECTOR]
        installations.append(dict(profile, phase=6, vbr_crc=zlib.crc32(sector)))
    state = state_records.encode(**disk.binding, installations=installations)
    put(disk.raw, {start: invalid, **dict.fromkeys(disk.state_at, state)})
    with boot(qemu, bios, work, disk.raw, 'mixed-wrong-family') as menu:
        menu.key('down', 0)
        menu.key('ret', 12)
        menu.expect(ui['STATE_VOLUME'])

    # The single-profile DOS preparation, countdown and trial path stays FAT16-only.
    single = disk.profiles[1]
    config = config_records.encode(**disk.binding, profiles=[single], default_id=single['id'],
                                   countdown=1, language=language)
    state = state_records.encode(**disk.binding, installations=[
        dict(single, phase=6, vbr_crc=zlib.crc32(disk.extents[start]))])
    put(disk.raw, {start: disk.extents[start], **dict.fromkeys(disk.state_at, state),
                   **dict.fromkeys(disk.config_at, config)})
    with boot(qemu, bios, work, disk.raw, 'single-fat32') as menu:
        menu.expect(ui['NO_PROFILES'])
        menu.key('f9', 0)
        menu.expect(ui['NO_PROFILES'])


def run(language, qemu, bios):
    directory = ROOT / 'build' / output_name('hdd', language)
    ui = load_catalog(language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        disk = make_fixture(work, directory, language, 1, 3, mixed=True)
        check_volumes(disk)
        bundle, image = package(work, language, disk, mixed=True)
        p2 = change(disk, disk.extents, 2, 2, 1)
        p3 = change(disk, p2.after, 3, 3, 1)
        p1 = change(disk, p3.after, 1, 4, 1)
        if [len(step.rows) for step in (p2, p3, p1)] != [5, 7, 7]:
            raise ValueError('Unexpected mixed-profile transaction schedule')
        with boot(qemu, bios, work, image, 'mixed-cancel') as menu:
            menu.expect(ui['AUTO_OFF'])
            for profile in disk.profiles:
                menu.expect(profile['name'])
            review(menu, disk, p2, ui)
            menu.key('esc', 0)
        compare(image, disk.raw)
        cold(qemu, bios, work, image, disk, Switch([], {}, disk.extents, 1, 1), 'mixed-initial-p1')
        expected = work / 'expected.raw'
        for step in (p2, p3, p1):
            writes = [at // SECTOR for at, _ in step.rows]
            with boot(qemu, bios, work, image, f'mixed-switch-{step.target}', writes) as menu:
                review(menu, disk, step, ui)
                confirm(menu, disk, step)
            write_fixture(expected, IMAGE_BYTES, step.after)
            compare(image, expected)
            cold(qemu, bios, work, image, disk, step, f'mixed-cold-{step.target}')
            compare(image, expected)
        refusals(qemu, bios, work, disk, p2, ui, language)
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
