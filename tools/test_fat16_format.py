"""Boot the shipped FAT16 diskette, check cold states and undo interrupted publication."""
import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, write_fixture
from mbr_boot import boot_fixture
from prepare_fat16_format import TICKET_LBA, ticketed_floppy
from prepare_mbr_target import sealed
from rescue_text import load_catalog
from retroboot_layout import load_plan
from setup_toolchain import sha256
from test_dos_countdown import compare
from test_fat_format_plan import GEOMETRY, LANGUAGES, builds, fixture
from test_fat_format_review import MODEL, enrolled_vdis, paired_floppy

KIT = 'RetroBoot-FAT16-Formatierung.zip'
STEM = 'fat16-format'
SYSTEM, CLONE = 'FAT16-Ziel.vdi', 'FAT16-Sicherung.vdi'
UUIDS = ('52429601-d413-4b6c-a396-000011111111', '52429602-d413-4b6c-a396-000022222222')
SERIALS = ('VB52429601-11111111', 'VB52429602-22222222')
# Golden P1 addresses from the independently frozen RB-8G-CHS255 profile.
START, DATA, LENGTH = 63, 482, 3148677
ORDER = (64, 72, 257, 63)


def package(work, plan, artifacts):
    raw, vdi, extents = fixture(work, plan, markers={
        DATA * SECTOR: b'P1 data-area guard', (START + LENGTH - 1) * SECTOR: b'P1 last-sector guard'})
    capacity = plan['disk_bytes'] // SECTOR
    media = enrolled_vdis(work, vdi, capacity, (SYSTEM, CLONE), UUIDS, SERIALS)
    for lang, folder in LANGUAGES.items():
        template = (artifacts[lang][0] / (STEM + '.img')).read_bytes()
        with raw.open('rb') as original:
            media[f'{folder}/{STEM}.img'] = ticketed_floppy(
                paired_floppy(template, SERIALS, capacity), plan, original, 1, GEOMETRY[1], GEOMETRY[2])
    media['README.md'] = (ROOT / 'docs/FAT16Format.md').read_bytes()
    bundle, delivered = work / KIT, work / 'delivered'
    with zipfile.ZipFile(bundle, 'x') as archive:
        for name, data in media.items():
            archive.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(delivered)
    for name, data in media.items():
        if (delivered / name).read_bytes() != data:
            raise ValueError('Package member differs: ' + name)
    return bundle, delivered, raw, extents


def formatted_sectors():
    # Golden BPB, two FAT reserved entries and empty fixed root. Build it
    # from the published reference geometry without calling the guest renderer.
    boot = bytearray(SECTOR)
    struct.pack_into('<3s8sHBHBHHBHHHII', boot, 0, b'\xeb\x3c\x90', b'RETROBT1',
                     512, 64, 1, 2, 512, 0, 0xf8, 193, 63, 255, START, LENGTH)
    struct.pack_into('<BBBI11s8s', boot, 36, 0x80, 0, 0x29, 0x52425431 ^ START,
                     b'NO NAME    ', b'FAT16   ')
    boot[62:66], boot[510:] = b'\xcd\x18\xeb\xfe', b'\x55\xaa'
    fat = b'\xf8\xff\xff\xff'.ljust(SECTOR, b'\0')
    return dict(zip(ORDER, (fat, bytes(SECTOR), fat, bytes(boot)), strict=True))


def check_filesystem(work, vdi):
    # Extract the guest-written bytes. mtools writes only to this disposable
    # partition copy. The subsequent guest rollback still sees its pristine FAT.
    raw, partition = work / 'guest.raw', work / 'guest-p1.raw'
    subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', vdi, raw], check=True)
    subprocess.run(['dd', 'if=' + str(raw), 'of=' + str(partition), 'bs=1M',
                    'skip=' + str(START * SECTOR), 'count=' + str(LENGTH * SECTOR),
                    'iflag=skip_bytes,count_bytes,fullblock', 'conv=sparse', 'status=none'], check=True)
    subprocess.run(['fsck.fat', '-n', partition], check=True)
    src, out = work / 'hello.txt', work / 'readback.txt'
    src.write_bytes(b'RetroBoot FAT16 file round trip\r\n' * 2048)
    target = '::RBTEST.TXT'
    subprocess.run(['mcopy', '-i', partition, src, target], check=True)
    subprocess.run(['mcopy', '-o', '-i', partition, target, out], check=True)
    if out.read_bytes() != src.read_bytes():
        raise ValueError('mtools file readback differs')
    subprocess.run(['mdel', '-i', partition, target], check=True)
    subprocess.run(['fsck.fat', '-n', partition], check=True)
    print('FAT16 host check: clean FAT, multi-cluster file write/read/delete, clean FAT', flush=True)


def check_io(expected, failed_write=False, failed_flush=False):
    def check(trace, stats):
        writes = [(int(l), int(n)) for l, n in re.findall(r'ide_sector_write sector=(\d+) nsectors=(\d+)', trace)]
        commands = re.findall(r'ide_bus_exec_cmd[^\n]*state (0x[0-9a-f]+); cmd (0x30|0xe7)\b', trace)
        sequence = ['0x30', '0xe7'] * len(expected)
        if failed_write:
            sequence.pop()
        if (writes != [(lba, 1) for lba in expected] or [op for _, op in commands] != sequence
                or len({state for state, _ in commands}) > 1):
            raise ValueError(f'Unexpected write/flush sequence: {writes}, {commands}')
        if stats['rb']['wr_bytes'] != (len(expected) - failed_write) * SECTOR:
            raise ValueError('Unexpected byte count on target')
        for name in ('recovery', 'floppy'):
            if stats.get(name, {}).get('wr_bytes', 0):
                raise ValueError('Unexpected write to ' + name)
        if failed_flush and not stats['rb'].get('failed_flush_operations'):
            raise ValueError('Missing expected target flush error')
        return {}
    return check


def campaign(qemu, bios, work, shipped, lang, binary, original, extents, host_tools):
    ui = load_catalog(lang)
    boot = shipped / LANGUAGES[lang] / (STEM + '.img')
    clone, target = shipped / CLONE, work / (lang + '-target.vdi')
    final = formatted_sectors()
    golden = work / 'expected.raw'
    size = original.stat().st_size

    def raw_state(path, done):
        data = dict(extents)
        data.update({lba * SECTOR: final[lba] for lba in ORDER[:done]})
        write_fixture(path, size, data)

    def disk_state(path, done):
        raw_state(golden, done)
        subprocess.run(['qemu-img', 'compare', '-q', path, golden], check=True)

    def boot_case(name, done=0, action='esc', key=None, *, error=None, at='open', writes=(),
                  source=target, backup=clone, medium=boot, serials=SERIALS, hook=None,
                  fault=None, cut=False, failed_write=False, failed_flush=False):
        lines = [ui['FW_TITLE']]
        actions = []
        if error is None or at != 'open':
            lines += [ui['FP_TARGET'] + ' P1', ui['FR_SOURCE'] + ' ' + serials[0], ui['FR_COPY'] + ' ' + serials[1],
                      ui['FR_SPAN'] + ' 0x0000003F - 0x000001E1', ui['FW_COUNT'] + f' {done}',
                      ui['FW_TOTAL'] + ' 4', 'RB FAT16 VERIFIED' if done == 4 else ui['FW_PARTIAL' if done else 'FW_ORIGINAL'],
                      ui['FW_RESTORE' if done else 'FW_FORMAT']]
            actions.append((lines[-1], action))
            if key:
                lines.append(ui['FW_CONFIRM'])
                actions.append((lines[-1], key))
            if key == '1':
                if at != 'confirm':
                    lines.append(ui['FW_RESTORING' if done else 'FW_WRITING'])
                    if not error and not cut:
                        lines.append('RB FAT16 RESTORE PASS' if done else 'RB FAT16 FORMAT PASS')
            else:
                lines.append(ui['FW_CANCEL'])
        if error:
            lines += [ui[error], 'RB FAT16 BLOCKED']
        elif not cut:
            lines.append('RB FAT16 END')
        path = f'blkdebug:{fault}:{source}' if fault else source
        boot_fixture(qemu, bios, binary, work, medium, path, lang + '-' + name, lines,
                     [(s, k, None, True) for s, k in actions], [], [], logical_geometry=GEOMETRY,
                     timeout=45, ata_identity=(MODEL, serials[0]), recovery_identity=(MODEL, serials[1]),
                     disk_format='vdi' if source.suffix == '.vdi' else 'raw', recovery_disk=backup,
                     recovery_format='vdi' if backup and backup.suffix == '.vdi' else 'raw',
                     before_key=hook, cut_on_source_error=cut, io_check=check_io(writes, failed_write, failed_flush))
        print(f'{lang} {name}: target sector writes {list(writes)}', flush=True)

    shutil.copyfile(shipped / SYSTEM, target)
    boot_case('cancel', action='f', key='esc')
    boot_case('wrong-slot', action='f', key='2')
    boot_case('no-backup', backup=None, error='FR_COPY_BAD')
    boot_case('swapped', source=clone, backup=target, serials=SERIALS[::-1], error='FR_SOURCE_BAD')
    boot_case('format', action='f', key='1', writes=ORDER)
    disk_state(target, 4)
    boot_case('cold-formatted', 4)
    if host_tools and lang == 'en':
        check_filesystem(work, target)
    boot_case('restore', 4, 'r', '1', writes=ORDER[::-1])
    boot_case('cold-original')
    compare(target, original)
    if lang != 'de':
        return

    source, copy = work / 'target.raw', work / 'backup.raw'
    conf = work / 'fault.conf'

    def edit(path, lba, data):
        with path.open('r+b', buffering=0) as stream:
            stream.seek(lba * SECTOR)
            stream.write(data)
            os.fsync(stream.fileno())

    def fault_at(event, operation, lba):
        conf.write_text(f'[inject-error]\nevent = "{event}"\niotype = "{operation}"\nerrno = "5"\nonce = "on"\n'
                        + (f'sector = "{lba}"\n' if lba is not None else ''))

    # Power cuts occur on a blocked primary write. Reopen that exact raw file.
    for restore in (False, True):
        order, initial, action = (ORDER[::-1], 4, 'r') if restore else (ORDER, 0, 'f')
        for n, lba in enumerate(order):
            raw_state(source, initial)
            fault_at('write_aio', 'write', lba)
            name = ('restore' if restore else 'format') + f'-cut-{n}'
            boot_case(name, initial, action, '1', source=source, fault=conf, cut=True,
                      writes=order[:n + 1], failed_write=True)
            present = initial - n if restore else n
            disk_state(source, present)
            if present:
                boot_case(name + '-reopen', present, 'r', '1', source=source, writes=ORDER[:present][::-1])
            else:
                boot_case(name + '-reopen', 0, source=source)
            disk_state(source, 0)

    raw_state(source, 0)
    fault_at('flush_to_disk', 'flush', None)
    boot_case('flush-error', action='f', key='1', source=source, fault=conf, error='FW_IO', at='write',
              writes=ORDER[:1], failed_flush=True)
    disk_state(source, 1)
    boot_case('flush-reopen', 1, 'r', '1', source=source, writes=ORDER[:1])

    raw_state(source, 0)
    conf.write_text('[set-state]\nevent = "flush_to_disk"\nnew_state = "2"\n'
                    '[inject-error]\nstate = "2"\nevent = "read_aio"\niotype = "read"\n'
                    f'sector = "{ORDER[0]}"\nerrno = "5"\nonce = "on"\n')
    boot_case('readback-error', action='f', key='1', source=source, fault=conf, error='FW_IO', at='write', writes=ORDER[:1])
    disk_state(source, 1)

    raw_state(source, 0)
    edit(source, ORDER[2], final[ORDER[2]])  # recognizable bytes in the wrong order
    boot_case('gap', source=source, error='FW_FOREIGN')
    raw_state(source, 1)
    edit(source, ORDER[0], b'\xf8\0')
    boot_case('torn-sector', source=source, error='FW_FOREIGN')
    raw_state(source, 4)
    edit(source, 450, b'FILE    TXT')
    boot_case('used-root', source=source, error='FW_FOREIGN')
    raw_state(source, 0)
    raw_state(copy, 0)
    edit(copy, 72, b'changed original')
    boot_case('stale-backup', source=source, backup=copy, error='FW_BACKUP')
    raw_state(copy, 0)

    def both_changed(q, prompt):
        if prompt == ui['FW_CONFIRM']:
            q.call('stop')
            for disk in (copy, source):
                edit(disk, 72, b'new common source')
            q.call('cont')

    boot_case('both-changed', action='f', key='1', source=source, backup=copy, hook=both_changed,
              error='FW_BACKUP', at='confirm')
    raw_state(source, 0)
    raw_state(copy, 0)
    edit(source, 0, b'X')
    boot_case('mbr-changed', source=source, backup=copy, error='FR_DIFFERENT')
    changed_boot = work / 'changed.img'
    buf = bytearray(boot.read_bytes())
    pos = TICKET_LBA * SECTOR
    buf[pos + 508] ^= 1
    changed_boot.write_bytes(buf)
    boot_case('damaged-ticket', medium=changed_boot, error='FW_TICKET')
    struct.pack_into('<H', buf, pos + 28, 2)
    buf[pos:pos + SECTOR] = sealed(bytes(buf[pos:pos + 508]))
    changed_boot.write_bytes(buf)
    boot_case('fat32-target', medium=changed_boot, error='FW_LAYOUT')


def run(qemu, bios, host_tools):
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    artifacts = builds(STEM)
    out = ROOT / 'build' / STEM
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        work = Path(tmp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\n')
        bundle, shipped, raw, sectors = package(work, plan, artifacts)
        originals = {p: sha256(p) for p in shipped.rglob('*') if p.is_file()}
        for disk in (SYSTEM, CLONE):
            compare(shipped / disk, raw)
        for lang in LANGUAGES:
            campaign(qemu, bios, work, shipped, lang, artifacts[lang][1], raw, sectors, host_tools)
        for path, digest in originals.items():
            if sha256(path) != digest:
                raise ValueError('Guest changed shipped ' + path.name)
        compare(shipped / CLONE, raw)
        bundle.replace(out / KIT)
        print(f'{KIT} {sha256(out / KIT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    parser.add_argument('--host-tools', action='store_true', help='also check the filesystem with dosfstools and mtools')
    args = parser.parse_args()
    run(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios, args.host_tools)
