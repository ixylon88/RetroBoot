"""Boot the released read-only FAT format planner on the physical reference layout."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, layout, write_fixture
from build_inputs import check_build_inputs
from mbr_boot import boot_fixture
from package_mbr_recovery import set_fixture_identity
from rescue_text import load_catalog, output_name
from retroboot_layout import fat_geometry, load_plan, validate_plan
from setup_toolchain import sha256
from test_dos_countdown import compare
from volume_fixtures import header

KIT = 'RetroBoot-Formatvorschau.zip'
PRIMARY = 'Format-Test.vdi'
FLOPPY = 'fat-plan.img'
GEOMETRY = (973, 255, 63)
LANGUAGES = {'de': 'Deutsch', 'en': 'English'}


def expected_layout(ui, volume, capacity, boot_message):
    """Use the frozen profile and the separate host layout checker as the oracle."""
    spec = volume['fat']
    start, total = volume['start_lba'], volume['sectors']
    f = fat_geometry(total, spec['bits'], spec['sectors_per_cluster'], spec['sectors_per_fat'])
    first = start + f['reserved_sectors']
    fat, clusters = f['sectors_per_fat'], f['data_clusters']
    root = first + 2 * fat
    data = root + f['root_directory_sectors']
    root_length = f['root_directory_sectors'] or f['sectors_per_cluster']

    def span(label, begin, end):
        return f'{label} 0x{begin:08X} - 0x{end:08X}'

    lines = [ui['DISK_ID'] + ' 0x52425431', ui['CAPACITY'] + f' 0x{capacity:016X}',
             span(ui['FP_VOLUME'], start, start + total - 1), ui[boot_message], f'FAT{f["bits"]}',
             f'{ui["FP_SPC"]} {f["sectors_per_cluster"]}', f'{ui["FP_FATSIZE"]} {fat}',
             f'{ui["FP_CLUSTERS"]} {clusters}', span(ui['FP_RESERVED'], start, first - 1),
             span('FAT 1', first, first + fat - 1), span('FAT 2', first + fat, root - 1),
             span(ui['FP_ROOT'], root, root + root_length - 1), f'{ui["FP_DATA"]} 0x{data:08X}']
    if f['bits'] == 32:
        lines += [f'{ui["FP_BOOT"]} 0x{start:08X} / 0x{start + 6:08X}',
                  f'{ui["FP_INFO"]} 0x{start + 1:08X} / 0x{start + 7:08X}']
    return lines


def fixture(work, plan):
    size, _, sectors = layout(True)
    target = plan['primary'][2]
    start = target['start_lba']
    vbr = header(32, start)
    vbr[13] = target['fat']['sectors_per_cluster']
    struct.pack_into('<HH', vbr, 24, 63, 255)
    struct.pack_into('<II', vbr, 32, target['sectors'], target['fat']['sectors_per_fat'])
    sectors[start * SECTOR] = bytes(vbr)
    # P1 has a zero first sector and nonzero data farther into the volume.
    sectors[(plan['primary'][0]['start_lba'] + 9) * SECTOR] = b'RB occupied sector'
    raw = work / 'reference.raw'
    write_fixture(raw, size, sectors)
    image = work / PRIMARY
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, image], check=True)
    set_fixture_identity(image, '52429401-8100-4000-8000-000000000001', size // SECTOR, heads=255)
    return raw, image, sectors


def builds():
    found = {}
    for lang in LANGUAGES:
        directory = ROOT / 'build' / output_name('rescue', lang)
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        check_build_inputs(manifest, ROOT)
        for name in (FLOPPY, 'fat-plan.bin'):
            if sha256(directory / name) != manifest['artifacts'][name]['sha256']:
                raise ValueError(f'{lang}: stale {name}')
        found[lang] = directory, dict(binary=(directory / 'fat-plan.bin').read_bytes(),
                                      memory=manifest['memory']['fat-plan'])
    return found


def run(qemu, bios):
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    validate_plan(plan)
    tables = [0, *(v['ebr_lba'] for v in plan['logical'])]
    size = plan['disk_bytes']
    artifacts = builds()
    output = ROOT / 'build/fat-plan'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        raw, image, sectors = fixture(work, plan)
        bundle = work / KIT
        members = {PRIMARY: image, 'README.md': ROOT / 'docs/FATFormatPlan.md'}
        for lang, folder in LANGUAGES.items():
            members[f'{folder}/{FLOPPY}'] = artifacts[lang][0] / FLOPPY
        with zipfile.ZipFile(bundle, 'x') as archive:
            for name, local in members.items():
                archive.writestr(zipfile.ZipInfo(name), local.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        delivered = work / 'delivered'
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(delivered)
        for name, local in members.items():
            if sha256(delivered / name) != sha256(local):
                raise ValueError('Package member differs: ' + name)
        example = delivered / PRIMARY
        compare(example, raw)
        original_hash = sha256(example)

        for lang, folder in LANGUAGES.items():
            ui = load_catalog(lang)
            source, binary = artifacts[lang]
            floppy = delivered / folder / FLOPPY

            def check(name, requests, *, disk=example, fmt='vdi', geometry=GEOMETRY, rom=None):
                lines = [ui['FP_TITLE'], ui['FP_SCOPE'], ui['FP_SELECT']]
                actions, reads = [], []
                for slot, key, result, sectors_read in requests:
                    actions += [(ui['FP_SELECT'], str(slot), None, True), (ui['FP_AUTO'], key, None, True)]
                    lines += [ui['FP_CHOICES'], ui['FP_AUTO']]
                    if key != 'esc':
                        lines += [ui['FP_TARGET'] + f' P{slot}', *result]
                    lines.append(ui['FP_SELECT'])
                    reads.extend(sectors_read)
                actions.append((ui['FP_SELECT'], 'esc', None, True))
                lines.append('RB FAT PLAN END')
                boot_fixture(qemu, bios, binary, work, floppy, disk, lang + '-' + name, lines, actions, [], reads,
                             logical_geometry=geometry, readonly_start=True, disk_format=fmt, rom=rom,
                             debug_prefix=('%0B3F',) if rom else ())  # ROM logs the profile read at floppy LBA 2879
                print(f'{lang} {name}: {len(reads)} HDD sectors read, zero guest writes', flush=True)

            def reference(slot, key, boot_message):
                v = plan['primary'][slot - 1]
                return (slot, key, expected_layout(ui, v, size // SECTOR, boot_message),
                        (tables + [v['start_lba']]) * 2)

            check('reference', [reference(1, 'ret', 'FP_ZERO'), reference(2, 'ret', 'FP_ZERO'),
                                reference(3, 'd', 'FP_BPB32'),
                                (2, 'g', [ui['FP_COUNT_BAD']], tables),
                                (4, 'ret', [ui['FP_TARGET_BAD']], tables), (1, 'esc', [], [])])
            check('chs-out-of-reach', [(1, 'ret', [ui['FP_CHS']], tables)], geometry=(10, 16, 63))
            check('changed-on-reprobe', [(1, 'ret', [ui['FP_CHANGED']], tables + [63])],
                  rom=source / 'int13-15.rom')
            check('no-disk', [(1, 'ret', [ui['FP_DEVICE']], [])], disk=None)
            # Recreate a copy for each negative case. Never change the delivered VDI.
            changed = work / 'changed.raw'
            mbr = bytearray(sectors[0])
            mbr[447] ^= 1
            write_fixture(changed, size, {**sectors, 0: bytes(mbr)})
            check('chs-entry-mismatch', [(1, 'ret', [ui['FP_CHS']], tables)], disk=changed, fmt='raw')
            mbr[450] = 0x1E  # Hidden FAT16 LBA target; CHS bytes are not used.
            write_fixture(changed, size, {**sectors, 0: bytes(mbr), 63 * SECTOR: b'Other data'})
            check('hidden-lba', [reference(1, 'g', 'FP_OTHER')], disk=changed, fmt='raw', geometry=(10, 16, 63))
            mbr[470:474] = mbr[454:458]  # P2 overlaps P1.
            write_fixture(changed, size, {**sectors, 0: bytes(mbr)})
            check('overlap', [(1, 'ret', [ui['FP_TABLE']], [0])], disk=changed, fmt='raw')
            if sha256(floppy) != sha256(source / FLOPPY):
                raise ValueError('Boot changed the released floppy')
        compare(example, raw)
        if sha256(example) != original_hash:
            raise ValueError('Boot changed the released VDI')
        bundle.replace(output / KIT)
        print(f'{KIT} {sha256(output / KIT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios)
