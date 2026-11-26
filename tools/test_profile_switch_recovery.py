"""Boot the independent rescue floppy against the first switch from the normal HDD menu."""
import argparse
from functools import partial
from pathlib import Path
import shutil
import struct
import tempfile

from backup_container import Chunk, Identity, encode
from build_hdd import ROOT, SECTOR, write_fixture
from handoff_fixtures import IMAGE_BYTES
from package_journal_recovery import IDS, PRIMARY, SECONDARY, WRITE_FLUSH, run_boot
from package_mbr_restore import capture_and_publish, checked_build
from prepare_mbr_target import WITNESS_START, prepare_pair
from test_backup_disk import CAPACITY
from test_dos_countdown import boot
from test_mbr_target import MODEL
from test_profile_menu import make_fixture
from test_profile_switch import change, cold, review, verify_raw
from ui_text import load_catalog


def profile_backup(disk, original, approved):
    """External container with the complete reserved area of every enrolled volume."""
    b = disk.binding
    capacity = IMAGE_BYTES // SECTOR
    admin, count = b['admin_start'], b['admin_sectors']
    identity = Identity(1, b['disk_id'], b['layout'], admin, count, capacity, b['media_id'])
    ebr = int.from_bytes(approved[502:506], 'little')
    chunks = [Chunk(1, 0, 0, original), Chunk(2, 0, 0, approved), Chunk(3, 0, ebr, disk.extents[ebr * SECTOR])]
    volumes = [(p['start'], p['sectors']) for p in disk.profiles] + [(admin, count)]
    for index, (start, sectors) in enumerate(volumes):
        reserved = struct.unpack_from('<H', disk.extents[start * SECTOR], 14)[0]
        area = b''.join(disk.extents.get((start + i) * SECTOR, bytes(SECTOR)) for i in range(reserved))
        chunks.append(Chunk(4, index, start, area, start, sectors))
    for kind, offset in enumerate(disk.config_at + disk.state_at, 5):
        chunks.append(Chunk(kind, 0, offset // SECTOR, disk.extents[offset], admin, count))
    return encode(identity, chunks)


def run(exe, bios, *, mixed=False):
    src = ROOT / 'build/rescue'
    checked_build(src, 'journal-recovery')
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        disk = make_fixture(work, ROOT / 'build/hdd', 'en', 1, 3 if mixed else 2, mixed=mixed)
        step = change(disk, disk.extents, 2, 2, 1)
        carrier, floppy = work / 'backup.raw', work / 'rescue.img'
        witness, _, _ = capture_and_publish(exe, bios, src, work, work / 'enroll.raw', carrier,
                IMAGE_BYTES, disk.extents, step.after[0], primary=PRIMARY[2], secondary=SECONDARY[2], ids=IDS,
                backup_file=partial(profile_backup, disk))
        base, _ = prepare_pair((src / 'journal-recovery.img').read_bytes(), MODEL, PRIMARY[2],
                               IMAGE_BYTES // SECTOR, *IDS, recovery=(MODEL, SECONDARY[2], CAPACITY))
        floppy.write_bytes(base[:WITNESS_START] + witness)
        expected = work / 'settled.img'
        write_fixture(expected, IMAGE_BYTES, step.after)
        ui = load_catalog('en')
        lbas = [at // SECTOR for at, _ in step.rows]
        delta = [(at, old, new) for at, (old, new) in enumerate(zip(step.before[0], step.after[0])) if old != new]
        # Each interrupted run uses the actual shipped HDD firmware. The floppy
        # and its previously published external witness supply the separate authority.
        for index in range(1, len(lbas)):
            write_fixture(disk.raw, IMAGE_BYTES, disk.extents)
            fault = f'[inject-error]\nevent = "write_aio"\niotype = "write"\nsector = "{lbas[index]}"\nerrno = "5"\n'
            with boot(str(exe), bios, work, disk.raw, f'source-cut-{index}', lbas[:index + 1], fault) as menu:
                review(menu, disk, step, ui)
                menu.key('ret', 18)
                menu.expect(ui['SWITCH_IO'])
            remaining = lbas[index:]
            run_boot(exe, bios, work, 'en', floppy, disk.raw, carrier, f'external-repair-{index}', 'JR_DONE',
                     lbas[-1], key='y', slot='A', writes=WRITE_FLUSH * len(remaining), stored=len(remaining) * SECTOR,
                     prepare_lba=lbas[1] if index == 1 else None, prepare_checked=index == 1,
                     mbr_changes=delta if index <= 2 else (), mbr_checked=index <= 2,
                     snapshot_lba=lbas[-2] if index <= 3 else None, snapshot_checked=index <= 3)
            verify_raw(disk.raw, expected)
            cold(str(exe), bios, work, disk.raw, disk, step, f'external-p2-cold-{index}')
        print('Independent rescue restored the first HDD switch at every intermediate publication boundary.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    exe = Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True)
    run(exe, args.bios)
    run(exe, args.bios, mixed=True)
