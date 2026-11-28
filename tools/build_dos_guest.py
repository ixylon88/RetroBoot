"""Build the bilingual DOS T11 kit from real RetroBoot formatter output and FreeDOS."""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, directory_entry, layout, write_fixture
from build_rescue import fat12_set
from mbr_boot import boot_fixture
from package_mbr_recovery import set_fixture_identity
from rescue_text import load_catalog
from retroboot_layout import load_plan
from setup_toolchain import LOCK, TOOLCHAIN, download, sha256
from test_fat_format_plan import GEOMETRY, LANGUAGES, builds
from test_fat_format_review import MODEL
from test_fat_format_write import FAT16, FAT32, check_io, package

OUT = ROOT / 'build/dos-guest'
KIT = 'RetroBoot-DOS-Dateitest.zip'
DISK = 'DOS-Dateitest.vdi'
FLOPPY = 'dos-test.img'
FIXTURE_ID = '422a9982-5525-4e97-8b0e-02019f6c5d68'
BINARY = 'ke2046_386f32.zip'
SOURCE = 'ke2046s.zip'
ARCHIVES = {BINARY: '9305ba9140c6ab0287612b5898c250756c6c6953204c3bda802b39ef853d372c',
            SOURCE: '0ea71c9276aba7e1e371f42e8e17d4e9223ac4bedeacccce3ee700fc2866c5e3'}


def catalog(lang):
    return json.loads((ROOT / 'ui/dos_guest' / (lang + '.json')).read_text(encoding='utf-8'))


def marker(slot):
    return f'RetroBoot T11 {FIXTURE_ID} P{slot}\r\n'.encode('ascii')


def freedos(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for name, digest in ARCHIVES.items():
        download(dict(url='https://github.com/FDOS/kernel/releases/download/ke2046/' + name,
                      sha256=digest), cache / name)


def boot_floppy(loader, files):
    # Standard 1.44 MiB FAT12 BPB in the upstream FAT12 loader.
    image = bytearray(2880 * SECTOR)
    image[:SECTOR] = loader
    if len(loader) != SECTOR or loader[510:] != b'\x55\xaa':
        raise ValueError('Invalid FreeDOS FAT12 loader')
    struct.pack_into('<8sHBHBHHBHHHIIBBBI11s8s', image, 3, b'FRDOS5.1', 512, 1, 1, 2, 224,
                     2880, 0xf0, 9, 18, 2, 0, 0, 0, 0, 0x29, 0x52425448, b'NO NAME    ', b'FAT12   ')
    fat = bytearray(9 * SECTOR)
    fat[:3] = b'\xf0\xff\xff'
    cluster = 2
    for index, (name, data) in enumerate(files.items()):
        count = (len(data) + SECTOR - 1) // SECTOR
        entry = bytearray(directory_entry(name, cluster, len(data)))
        for pos in (16, 18, 24):
            struct.pack_into('<H', entry, pos, 0x21)  # 1980-01-01
        root = 19 * SECTOR + 32 * index
        image[root:root + 32] = entry
        offset = (31 + cluster) * SECTOR
        image[offset:offset + len(data)] = data
        for n in range(cluster, cluster + count):
            fat12_set(fat, n, 0xfff if n + 1 == cluster + count else n + 1)
        cluster += count
    image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat
    return bytes(image)


def floppies(work, cache):
    lock = json.loads(LOCK.read_bytes())
    nasm = TOOLCHAIN / ('nasm-' + lock['nasm']['version']) / 'nasm'
    with zipfile.ZipFile(cache / SOURCE) as source:
        for name in ('boot.asm', 'magic.mac'):
            (work / name).write_bytes(source.read('SOURCE/ke2046/boot/' + name))
        license_text = source.read('SOURCE/ke2046/COPYING')
    subprocess.run([nasm, '-DISFAT12', '-f', 'bin', 'boot.asm', '-o', 'boot.bin'], cwd=work, check=True)
    boot = (work / 'boot.bin').read_bytes()
    with zipfile.ZipFile(cache / BINARY) as archive:
        kernel = archive.read('bin/kernel.sys')
    members = {'FreeDOS/' + SOURCE: (cache / SOURCE).read_bytes(), 'FreeDOS/COPYING': license_text}
    for lang, folder in LANGUAGES.items():
        strings = [f'msg_{key} db ' + ','.join(map(str, value.encode('cp437'))) + ',13,10,0'
                   for key, value in catalog(lang).items()]
        strings.extend([f'serial_p{ref.slot} equ 0x{0x52425431 ^ ref.start:08x}' for ref in (FAT16, FAT32)])
        strings.extend(['id_text db ' + ','.join(map(str, marker(1))), 'id_length equ $ - id_text',
                        'id_slot equ id_length - 3'])  # slot digit immediately before CR/LF
        (work / 'dos_guest_text.inc').write_text('\n'.join(strings) + '\n', encoding='ascii')
        probe = work / 'RBT11.COM'
        subprocess.run([nasm, '-Werror', '-f', 'bin', ROOT / 'tests/format/dos_guest.asm', '-o', probe],
                       cwd=work, check=True)
        image = boot_floppy(boot, {b'KERNEL  SYS': kernel,
                                  b'FDCONFIGSYS': b'SHELL=A:\\RBT11.COM /BOOT\r\n',
                                  b'RBT11   COM': probe.read_bytes()})
        members[f'{folder}/{FLOPPY}'] = image
    return members


def formatted_metadata(work, qemu, bios, plan, ref):
    work.mkdir()
    artifacts = builds(ref.stem)
    _, shipped, _, _ = package(work, plan, artifacts, ref)
    (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\n')
    ui = load_catalog('en')
    text = 'FW_' if ref.bits == 16 else 'FW32_'
    disk = shipped / ref.system
    lines = [ui[text + 'TITLE'], ui['FP_TARGET'] + f' P{ref.slot}',
             ui['FR_SOURCE'] + ' ' + ref.serials[0], ui['FR_COPY'] + ' ' + ref.serials[1],
             ui['FR_SPAN'] + f' 0x{ref.start:08X} - 0x{ref.first_unowned - 1:08X}',
             ui['FW_COUNT'] + ' 0', ui['FW_TOTAL'] + f' {len(ref.order)}', ui['FW_ORIGINAL'],
             ui[text + 'FORMAT'], ui['FW_CONFIRM'], ui[text + 'WRITING'],
             f'RB FAT{ref.bits} FORMAT PASS', f'RB FAT{ref.bits} END']
    keys = [(ui[text + 'FORMAT'], 'f', None, True), (ui['FW_CONFIRM'], str(ref.slot), None, True)]
    boot_fixture(qemu, bios, artifacts['en'][1], work, shipped / 'English' / (ref.stem + '.img'),
                 disk, 'format', lines, keys, [], [], logical_geometry=GEOMETRY,
                 ata_identity=(MODEL, ref.serials[0]), recovery_disk=shipped / ref.clone,
                 recovery_identity=(MODEL, ref.serials[1]), disk_format='vdi', recovery_format='vdi',
                 timeout=45, io_check=check_io(ref.order))
    raw = work / 'formatted.raw'
    subprocess.run(['qemu-img', 'convert', '-O', 'raw', disk, raw], check=True)
    with raw.open('rb') as stream:
        stream.seek(ref.start * SECTOR)
        size = (ref.first_unowned - ref.start) * SECTOR
        metadata = stream.read(size)
    if len(metadata) != size or (ref.bits == 32 and metadata[:3 * SECTOR] != metadata[6 * SECTOR:9 * SECTOR]):
        raise ValueError('Incomplete formatter metadata or divergent FAT32 boot records')
    return metadata


def build(qemu, bios, work):
    cache = ROOT / 'build/freedos-2046'
    freedos(cache)
    members = floppies(work, cache)
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    size, _, sectors = layout(True)
    # Disposable data disk: retain P1/P2 starts and sizes, expose only those
    # two partitions, and keep the formatter's entire metadata span for each.
    mbr = bytearray(sectors[0])
    mbr[478:510] = bytes(32)
    mbr[446] = 0x80
    struct.pack_into('<I', mbr, 440, 0x52425448)
    data = {0: mbr}
    for ref in (FAT16, FAT32):
        data[ref.start * SECTOR] = formatted_metadata(work / ref.stem, qemu, bios, plan, ref)
    raw, disk = work / 'dos.raw', work / DISK
    write_fixture(raw, size, data)
    for ref in (FAT16, FAT32):
        tag = work / 'RBT11.ID'
        tag.write_bytes(marker(ref.slot))
        os.utime(tag, (946684800, 946684800))
        image = f'{raw}@@{ref.start * SECTOR}'
        subprocess.run(['mcopy', '-m', '-i', image, tag, '::RBT11.ID'], check=True,
                       env={**os.environ, 'TZ': 'UTC'})
        subprocess.run(['mattrib', '-i', image, '+r', '::RBT11.ID'], check=True)
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, disk], check=True)
    set_fixture_identity(disk, FIXTURE_ID, size // SECTOR, heads=255)
    members[DISK] = disk.read_bytes()
    members['README.md'] = (ROOT / 'docs/DOSGuestTest.md').read_bytes()
    bundle = work / KIT
    with zipfile.ZipFile(bundle, 'x') as archive:
        for name, content in members.items():
            archive.writestr(zipfile.ZipInfo(name), content, compress_type=zipfile.ZIP_DEFLATED)
    return bundle


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT) as folder:
        bundle = build(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios, Path(folder))
        bundle.replace(OUT / KIT)
    print(f'{KIT} {sha256(OUT / KIT)}', flush=True)
