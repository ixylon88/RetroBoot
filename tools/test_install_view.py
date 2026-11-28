"""Boot, interrupt and restore the checked Windows 95 OSR2/P2 visibility transaction."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, write_fixture
from install_reference import DISK_ID, visibility_tables
from mbr_boot import boot_fixture
from rescue_text import load_catalog
from retroboot_layout import load_plan
from setup_toolchain import sha256
from test_dos_countdown import compare
from test_fat_format_plan import GEOMETRY, LANGUAGES, builds, fixture_extents
from test_fat_format_review import MODEL, enrolled_vdis, paired_floppy
from test_fat_format_write import check_io
from test_install_plan import HIDE_P1, SHOW_P2, HIDE_SHARED, START, END, TABLES

KIT = 'RetroBoot-Setup-Partitionssicht.zip'
SYSTEM, BACKUP = 'Setup-Ziel.vdi', 'Setup-Sicherung.vdi'
FLOPPY = 'install-view.img'
UUIDS = ('52421001-d413-4b6c-a400-000011111111', '52421002-d413-4b6c-a400-000022222222')
SERIALS = ('VB52421001-11111111', 'VB52421002-22222222')
ORDER = (10474380, 11647125, 0)
CHANGES = HIDE_P1 + SHOW_P2 + HIDE_SHARED


def package(work, artifacts):
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    size, extents = fixture_extents(plan)
    for lba, sector in visibility_tables().items():
        extents[lba * SECTOR] = sector
    raw, vdi = work / 'original.raw', work / 'base.vdi'
    write_fixture(raw, size, extents)
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, vdi], check=True)
    media = enrolled_vdis(work, vdi, size // SECTOR, (SYSTEM, BACKUP), UUIDS, SERIALS)
    for lang, folder in LANGUAGES.items():
        media[folder + '/' + FLOPPY] = paired_floppy((artifacts[lang][0] / FLOPPY).read_bytes(),
                                                    SERIALS, size // SECTOR)
    media['README.md'] = (ROOT / 'docs/InstallationView.md').read_bytes()
    kit, shipped = work / KIT, work / 'delivered'
    with zipfile.ZipFile(kit, 'x') as archive:
        for name, data in media.items():
            archive.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(kit) as archive:
        archive.extractall(shipped)
    if any((shipped / name).read_bytes() != data for name, data in media.items()):
        raise ValueError('Package members differ')
    return kit, shipped, raw, extents


def campaign(qemu, bios, work, shipped, raw, extents, binary, lang):
    ui = load_catalog(lang)
    boot = shipped / LANGUAGES[lang] / FLOPPY
    target, backup = work / (lang + '-target.vdi'), shipped / BACKUP
    source, copy, golden = (work / name for name in ('system.raw', 'backup.raw', 'golden.raw'))
    conf = work / 'fault.conf'

    def disk_state(path, done, extra=()):
        sectors = dict(extents)
        for _, lba, offset, before, after in CHANGES:
            buf = bytearray(sectors[lba * SECTOR])
            if buf[offset] != before:
                raise ValueError('Unexpected original byte in reference kit')
            if lba in ORDER[:done]:
                buf[offset] = after
            sectors[lba * SECTOR] = bytes(buf)
        write_fixture(path, raw.stat().st_size, sectors)
        for lba, offset, data in extra:
            edit(path, lba, offset, data)

    def edit(path, lba, offset, data):
        with path.open('r+b', buffering=0) as stream:
            stream.seek(lba * SECTOR + offset)
            stream.write(data)
            os.fsync(stream.fileno())

    def verify(path, done, extra=()):
        disk_state(golden, done, extra)
        subprocess.run(['qemu-img', 'compare', '-q', path, golden], check=True)

    def case(name, done=0, action='esc', confirm=None, *, error=None, lba=None, writes=(),
             at_open=False, disk=target, clone=backup, serials=SERIALS, medium=boot,
             geometry=GEOMETRY, hook=None, fault=None, cut=False, failed_flush=False, rom=None):
        lines, actions = [ui['IV_TITLE'], 'Windows 95 OSR2  P2'], []
        if not at_open:
            lines += [ui['FR_SOURCE'] + ' ' + serials[0], ui['FR_COPY'] + ' ' + serials[1],
                      ui['DISK_ID'] + f' 0x{DISK_ID:08X}    FAT32',
                      ui['FP_VOLUME'] + f' 0x{START[2]:08X} - 0x{END[2]:08X}',
                      ui['FW_COUNT'] + f' {done}', 'RB INSTALL VIEW ACTIVE' if done == 3 else
                      ui['IV_PARTIAL' if done else 'IV_ORIGINAL'], ui['IP_COLUMNS']]
            rows = [r for r in CHANGES if not done or r[1] in ORDER[:done]]
            for label, table, pos, before, after in rows:
                old, new = (after, before) if done else (before, after)
                lines.append(f'{label}     0x{table:08X}    0x{pos:04X}    0x{old:02X} -> 0x{new:02X}')
            lines += [ui['IP_BYTES'] + f' {len(rows)}', ui['IP_SECTORS'] + f' {len({r[1] for r in rows})}',
                      ui['IV_RESTORE' if done else 'IV_APPLY']]
            actions.append((lines[-1], action))
            if confirm:
                lines.append(ui['FW_CONFIRM'])
                actions.append((lines[-1], confirm))
            if confirm != '2':
                lines.append(ui['FW_CANCEL'])
            elif not error and not cut:
                lines.append('RB INSTALL VIEW RESTORE PASS' if done else 'RB INSTALL VIEW APPLY PASS')
        if error:
            lines.append(ui[error])
            if lba is not None:
                lines.append(f'LBA 0x{lba:08X}')
            lines.append('RB INSTALL VIEW BLOCKED')
        elif not cut:
            lines.append('RB INSTALL VIEW END')
        path = f'blkdebug:{fault}:{disk}' if fault else disk
        boot_fixture(qemu, bios, binary, work, medium, path, lang + '-' + name, lines,
                     [(s, k, None, True) for s, k in actions], [], [], readonly_start=True,
                     logical_geometry=geometry, ata_identity=(MODEL, serials[0]),
                     recovery_identity=(MODEL, serials[1]), disk_format='vdi' if disk.suffix == '.vdi' else 'raw',
                     recovery_disk=clone, recovery_format='vdi' if clone and clone.suffix == '.vdi' else 'raw',
                     before_key=hook, rom=rom, cut_on_source_error=cut, io_check=check_io(writes, cut, failed_flush))
        print(f'{lang} {name}: target writes {list(writes)}', flush=True)

    shutil.copyfile(shipped / SYSTEM, target)
    case('cancel')
    case('cancel-confirm', action='a', confirm='esc')
    case('wrong-slot', action='a', confirm='1')
    case('no-backup', clone=None, error='FR_COPY_BAD', at_open=True)
    case('wrong-ide-masters', disk=backup, clone=target, serials=SERIALS[::-1], error='FR_SOURCE_BAD', at_open=True)
    case('apply', action='a', confirm='2', writes=ORDER)
    verify(target, 3)
    case('cold-active', 3)
    case('cancel-restore', 3, 'r', 'esc')
    case('restore', 3, 'r', '2', writes=ORDER[::-1])
    verify(target, 0)
    case('cold-original')
    if lang != 'de':
        rom = ROOT / 'build/rescue/int13-no-edd.rom'
        case('chs-only-apply', action='a', confirm='2', writes=ORDER, rom=rom)
        verify(target, 3)
        case('chs-only-restore', 3, 'r', '2', writes=ORDER[::-1], rom=rom)
        verify(target, 0)
        return

    for restore in (False, True):
        initial, action = (3, 'r') if restore else (0, 'a')
        sequence = ORDER[::-1] if restore else ORDER
        for n, lba in enumerate(sequence):
            name = ('undo' if restore else 'apply') + f'-cut-{n}'
            disk_state(source, initial)
            conf.write_text('[inject-error]\nevent = "write_aio"\niotype = "write"\nerrno = "5"\n'
                            f'once = "on"\nsector = "{lba}"\n')
            case(name, initial, action, '2', disk=source, fault=conf, cut=True, writes=sequence[:n + 1])
            present = initial - n if restore else n
            verify(source, present)
            if present:
                case(name + '-reopen', present, 'r', '2', disk=source, writes=ORDER[:present][::-1])
            else:
                case(name + '-reopen', disk=source)
            verify(source, 0)

    disk_state(source, 0)
    conf.write_text('[inject-error]\nevent = "flush_to_disk"\niotype = "flush"\nerrno = "5"\nonce = "on"\n')
    case('flush-error', action='a', confirm='2', disk=source, fault=conf, failed_flush=True,
         error='IV_IO', lba=ORDER[0], writes=ORDER[:1])
    verify(source, 1)
    case('flush-reopen', 1, 'r', '2', disk=source, writes=ORDER[:1])

    disk_state(source, 0)
    conf.write_text('[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
                    '[inject-error]\nstate = "2"\nevent = "read_aio"\niotype = "read"\n'
                    f'sector = "{ORDER[0]}"\nerrno = "5"\nonce = "on"\n')
    case('readback-error', action='a', confirm='2', disk=source, fault=conf,
         error='IV_IO', lba=ORDER[0], writes=ORDER[:1])
    verify(source, 1)

    disk_state(source, 0, [(ORDER[1], 450, b'\x1b')])
    case('out-of-order', disk=source, error='IV_FOREIGN', lba=ORDER[1], at_open=True)
    disk_state(source, 2, [(0, 446, b'\x00')])
    case('torn-mbr', disk=source, error='IV_FOREIGN', lba=0, at_open=True)
    disk_state(source, 3, [(TABLES[2], 90, b'X')])
    case('changed-management-ebr', disk=source, error='IV_FOREIGN', lba=TABLES[2], at_open=True)
    disk_state(source, 0)
    disk_state(copy, 0, [(TABLES[1], 57, b'X')])
    case('altered-backup', disk=source, clone=copy, error='IV_BACKUP', lba=TABLES[1], at_open=True)
    edit(source, TABLES[1], 57, b'X')
    case('both-tables-altered-alike', disk=source, clone=copy, error='IV_BACKUP', lba=TABLES[1], at_open=True)
    disk_state(source, 0)
    case('geometry', disk=source, geometry=(10, 16, 63), error='IP_GEOMETRY', at_open=True)
    blank = ROOT / 'build/rescue-de' / FLOPPY
    case('blank-profile', medium=blank, disk=source, error='FR_PROFILE', at_open=True)

    def change_at_confirm(path, sector, offset, data):
        def hook(q, prompt):
            if prompt == ui['FW_CONFIRM']:
                q.call('stop')
                edit(path, sector, offset, data)
                q.call('cont')
        return hook

    for tag, mount, lba, offset, data, reason in (
            ('changed-confirm-target', source, TABLES[3], 400, b'X', 'IV_FOREIGN'),
            ('changed-confirm-backup', copy, TABLES[2], 400, b'X', 'IV_BACKUP'),
            ('occupied-confirm', source, START[2] + 6, 42, b'X', 'IP_OCCUPIED')):
        disk_state(source, 0)
        disk_state(copy, 0)
        case(tag, action='a', confirm='2', disk=source, clone=copy, error=reason, lba=lba,
             hook=change_at_confirm(mount, lba, offset, data))

    # A changed partition boot area blocks a fresh installation, but table-only undo preserves it.
    user_data = [(START[2] + 6, 42, b'volume boot data'), (START[2] + 9000, 0, b'file data')]
    disk_state(source, 3, user_data)
    case('restore-preserves-volume', 3, 'r', '2', disk=source, writes=ORDER[::-1])
    verify(source, 0, user_data)
    case('occupied-reapply', disk=source, error='IP_OCCUPIED', lba=START[2] + 6, at_open=True)


def run(qemu, bios):
    out = ROOT / 'build/install-view'
    out.mkdir(exist_ok=True)
    artifacts = builds('install-view')
    with tempfile.TemporaryDirectory(dir=out) as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\n')
        kit, shipped, raw, extents = package(work, artifacts)
        original = {p: sha256(p) for p in shipped.rglob('*') if p.is_file()}
        for lang in LANGUAGES:
            campaign(qemu, bios, work, shipped, raw, extents, artifacts[lang][1], lang)
        for name in (SYSTEM, BACKUP):
            compare(shipped / name, raw)
        if any(sha256(p) != digest for p, digest in original.items()):
            raise ValueError('A distributed disk or floppy changed')
        kit.replace(out / KIT)
    print(f'{KIT} {sha256(out / KIT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios)
