"""Boot the bilingual installer planner and verify exact byte proposals and zero writes."""
import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, write_fixture
from install_reference import DISK_ID, DISK_UUID
from mbr_boot import boot_fixture
from package_mbr_recovery import set_fixture_identity
from rescue_text import load_catalog
from retroboot_layout import load_plan
from setup_toolchain import sha256
from test_dos_countdown import compare
from test_fat_format_plan import GEOMETRY, LANGUAGES, builds, fixture_extents

KIT = 'RetroBoot-Installationsplanung.zip'
DISK = 'Installationsziel.vdi'
FLOPPY = 'install-plan.img'
SYSTEMS = ('MS-DOS 6.22', 'Windows 95 OSR2', 'Windows 98 SE')

# Golden layout/byte changes for the supplied reference, independent of the C planner.
TABLES = [0, 10474380, 11518605, 11647125]
START = {1: 63, 2: 3148740, 3: 6297480}
END = {1: 3148739, 2: 6297479, 3: 10474379}
HIDE_SHARED = [('L1', 10474380, 450, 0x06, 0x16), ('L3', 11647125, 450, 0x0b, 0x1b)]
HIDE_P1 = [('P1', 0, 446, 0x80, 0), ('P1', 0, 450, 0x06, 0x16)]
SHOW_P2 = [('P2', 0, 462, 0, 0x80), ('P2', 0, 466, 0x1b, 0x0b)]
SHOW_P3 = [('P3', 0, 478, 0, 0x80), ('P3', 0, 482, 0x1b, 0x0b)]


def package(work, artifacts):
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    size, sectors = fixture_extents(plan)
    mbr = bytearray(sectors[0])
    struct.pack_into('<I', mbr, 440, DISK_ID)
    mbr[446], mbr[466], mbr[482] = 0x80, 0x1b, 0x1b
    sectors[0] = bytes(mbr)
    raw, disk = work / 'reference.raw', work / DISK
    write_fixture(raw, size, sectors)
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, disk], check=True)
    set_fixture_identity(disk, DISK_UUID, size // SECTOR, heads=255)
    members = {DISK: disk, 'README.md': ROOT / 'docs/InstallationPlan.md'}
    members.update({f'{folder}/{FLOPPY}': artifacts[lang][0] / FLOPPY for lang, folder in LANGUAGES.items()})
    kit, shipped = work / KIT, work / 'delivered'
    with zipfile.ZipFile(kit, 'x') as archive:
        for name, path in members.items():
            archive.writestr(zipfile.ZipInfo(name), path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(kit) as archive:
        archive.extractall(shipped)
    for name, path in members.items():
        if sha256(shipped / name) != sha256(path):
            raise ValueError('Package member differs: ' + name)
    return kit, shipped, raw, sectors


def boot_sectors(slot):
    offsets = (0,) if slot == 1 else (0, 1, 2, 6, 7, 8)
    return [START[slot] + offset for offset in offsets]


def campaign(qemu, bios, work, shipped, raw, sectors, binary, lang):
    ui = load_catalog(lang)
    disk, floppy = shipped / DISK, shipped / LANGUAGES[lang] / FLOPPY
    altered = work / 'altered.raw'

    def make_altered(*patches):
        write_fixture(altered, raw.stat().st_size, sectors)
        with altered.open('r+b') as out:
            for lba, pos, data in patches:
                out.seek(lba * SECTOR + pos)
                out.write(data)
        return altered

    def blocked(reason, lba=None):
        return [ui[reason]] + ([] if lba is None else [f'LBA 0x{lba:08X}']) + ['RB INSTALL PLAN BLOCKED']

    def case(name, os_key, slot, *, rows=None, refusal=None, reads=None, retry=True,
             repeat_error=None, repeat_reads=None, source=disk, geometry=GEOMETRY, hook=None, rom=None):
        lines = [ui['IP_TITLE'], ui['IP_SCOPE'], ui['IP_OS']]
        actions = [(ui['IP_OS'], str(os_key))]
        expected = []
        if os_key != 'esc':
            lines.append(ui['IP_SLOT'])
            actions.append((ui['IP_SLOT'], str(slot)))
            if slot != 'esc':
                lines.append(f'{SYSTEMS[os_key - 1]}  P{slot}')
                expected = list(reads) if reads is not None else TABLES + boot_sectors(slot)
                if refusal is not None:
                    lines.extend(refusal)
                else:
                    lines += [f"{ui['DISK_ID']} 0x{DISK_ID:08X}    FAT{16 if slot == 1 else 32}",
                              f"{ui['FP_VOLUME']} 0x{START[slot]:08X} - 0x{END[slot]:08X}",
                              ui['IP_BOOT_CLEAR'], ui['IP_VIEW'], ui['IP_COLUMNS']]
                    for label, lba, offset, before, after in rows:
                        lines.append(f'{label}     0x{lba:08X}    0x{offset:04X}    0x{before:02X} -> 0x{after:02X}')
                    lines += [f"{ui['IP_BYTES']} {len(rows)}",
                              f"{ui['IP_SECTORS']} {len({row[1] for row in rows})}", ui['IP_REPEAT']]
                    actions.append((ui['IP_REPEAT'], 'r' if retry else 'esc'))
                    if retry:
                        expected += list(repeat_reads) if repeat_reads is not None else list(expected)
                        lines.extend(repeat_error or ['RB INSTALL PLAN VERIFIED'])
            lines.append(ui['IP_OS'])
            actions.append((ui['IP_OS'], 'esc'))
        lines.append('RB INSTALL PLAN END')
        boot_fixture(qemu, bios, binary, work, floppy, source, lang + '-' + name, lines,
                     [(prompt, key, None, True) for prompt, key in actions], [], expected,
                     readonly_start=True, logical_geometry=geometry, before_key=hook,
                     disk_format='vdi' if source == disk else 'raw', rom=rom)
        print(f'{lang} {name}: {len(expected)} HDD sectors read, zero disk writes', flush=True)

    case('exit', 'esc', None)
    case('back', 2, 'esc')
    case('dos-p1', 1, 1, rows=HIDE_SHARED)
    case('dos-p2', 1, 2, refusal=blocked('IP_DOS_FAT'), reads=TABLES)
    case('windows95-p1', 2, 1, rows=HIDE_SHARED)
    case('windows95-p2', 2, 2, rows=HIDE_P1 + SHOW_P2 + HIDE_SHARED)
    case('windows98-p2', 3, 2, rows=HIDE_P1 + SHOW_P2 + HIDE_SHARED)
    case('cancel-review', 2, 2, rows=HIDE_P1 + SHOW_P2 + HIDE_SHARED, retry=False)
    case('protected-p3', 3, 3, refusal=blocked('IP_OCCUPIED', START[3]), reads=TABLES + [START[3]])
    case('extended-p4', 3, 4, refusal=blocked('IP_SYSTEM_SLOT'), reads=TABLES)

    clear_p3 = make_altered((START[3], 0, bytes(SECTOR)))
    case('windows95-p3', 2, 3, rows=HIDE_P1 + SHOW_P3 + HIDE_SHARED, source=clear_p3)
    case('windows98-p3', 3, 3, rows=HIDE_P1 + SHOW_P3 + HIDE_SHARED, source=clear_p3)
    if lang != 'en':
        return
    roms = ROOT / 'build/rescue'
    case('chs-only', 1, 1, rows=HIDE_SHARED, rom=roms / 'int13-1.rom')
    case('capacity-changed', 3, 2, rows=HIDE_P1 + SHOW_P2 + HIDE_SHARED,
         repeat_error=blocked('IP_DISK'), repeat_reads=[], rom=roms / 'int13-14.rom')
    patches = [(lba, pos, bytes([new])) for _, lba, pos, _, new in HIDE_P1 + SHOW_P2 + HIDE_SHARED]
    case('p2-already-isolated', 2, 2, rows=[], source=make_altered(*patches))
    case('no-disk', 2, 2, refusal=blocked('FP_DEVICE'), reads=[], source=None)
    case('outside-chs', 1, 1, refusal=blocked('IP_GEOMETRY'), reads=[], geometry=(10, 16, 63))
    for name, table, pos, data, seen in (
            ('wrong-disk-id', 0, 440, b'XXXX', TABLES[:1]),
            ('different-chs-bytes', 0, 447, b'\x03', TABLES[:1]),
            ('different-extended-link', TABLES[1], 470, b'XX', TABLES[:2]),
            ('visible-management', TABLES[2], 450, b'\x06', TABLES[:3]),
            ('foreign-slot-type', TABLES[3], 450, b'\x07', TABLES),
            ('damaged-ebr-signature', TABLES[2], 511, b'\x00', TABLES),
            ('multiple-active', 0, 462, b'\x80', TABLES)):
        case(name, 3, 2, source=make_altered((table, pos, data)), reads=seen,
             refusal=blocked('IP_DISK' if name == 'wrong-disk-id' else 'IP_LAYOUT', table))
    for offset in (0, 1, 2, 6, 7, 8):
        lba = START[2] + offset
        inspected = [n for n in boot_sectors(2) if n <= lba]
        case(f'occupied-boot-{offset}', 2, 2, source=make_altered((lba, 119, b'X')),
             refusal=blocked('IP_OCCUPIED', lba), reads=TABLES + inspected)

    def edit_while_waiting(lba, pos, data):
        def edit(q, prompt):
            if prompt == ui['IP_REPEAT']:
                q.call('stop')
                with altered.open('r+b', buffering=0) as out:
                    out.seek(lba * SECTOR + pos)
                    out.write(data)
                    os.fsync(out.fileno())
                q.call('cont')
        return edit

    for name, lba, pos, data, reason in (
            ('changed-foreign-table-byte', TABLES[2], 32, b'X', 'IP_CHANGED'),
            ('changed-legal-visibility', TABLES[1], 450, b'\x16', 'IP_CHANGED'),
            ('new-boot-data', START[2] + 6, 40, b'X', 'IP_OCCUPIED')):
        fresh = reason == 'IP_CHANGED'
        case(name, 2, 2, rows=HIDE_P1 + SHOW_P2 + HIDE_SHARED, source=make_altered(),
             repeat_error=blocked(reason, None if fresh else lba),
             repeat_reads=TABLES + (boot_sectors(2) if fresh else boot_sectors(2)[:4]),
             hook=edit_while_waiting(lba, pos, data))


def run(qemu, bios):
    out = ROOT / 'build/install-plan'
    out.mkdir(exist_ok=True)
    artifacts = builds('install-plan')
    with tempfile.TemporaryDirectory(dir=out) as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        kit, shipped, raw, sectors = package(work, artifacts)
        originals = {p: sha256(p) for p in shipped.rglob('*') if p.is_file()}
        for lang in LANGUAGES:
            campaign(qemu, bios, work, shipped, raw, sectors, artifacts[lang][1], lang)
        compare(shipped / DISK, raw)
        if any(sha256(p) != digest for p, digest in originals.items()):
            raise ValueError('A distributed disk or floppy changed')
        kit.replace(out / KIT)
    print(f'{KIT} {sha256(out / KIT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios)
