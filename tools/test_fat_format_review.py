"""Boot the shipped bilingual target review with two independently identified IDE masters."""
import argparse
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile

from build_hdd import ROOT, SECTOR, write_fixture
from mbr_boot import boot_fixture
from package_mbr_recovery import set_fixture_identity
from prepare_mbr_target import prepare_pair
from rescue_text import load_catalog
from setup_toolchain import sha256
from test_dos_countdown import compare
from retroboot_layout import load_plan
from test_fat_format_plan import FLOPPY, GEOMETRY, LANGUAGES, builds, expected_layout, fixture
from test_rescue import trace_reads

KIT = 'RetroBoot-Formatziel.zip'
SYSTEM, CLONE = 'Format-Ziel.vdi', 'Format-Sicherung.vdi'
MODEL = 'VBOX HARDDISK'
SERIALS = ('VB52429501-11111111', 'VB52429502-22222222')
UUIDS = ('52429501-d413-4b6c-a395-000011111111', '52429502-d413-4b6c-a395-000022222222')


def package(work, plan, artifacts):
    raw, vdi, sectors = fixture(work, plan)
    capacity = plan['disk_bytes'] // SECTOR
    media = {}
    for name, guid, serial in zip((SYSTEM, CLONE), UUIDS, SERIALS, strict=True):
        path = work / name
        shutil.copyfile(vdi, path)
        set_fixture_identity(path, guid, capacity, heads=255)
        with path.open('rb') as image:
            image.seek(392)
            words = struct.unpack('<4I', image.read(16))
        if f'VB{words[0]:08x}-{words[3]:08x}' != serial:
            raise ValueError('Enrolled serial differs from the VDI creation UUID')
        media[name] = path.read_bytes()
    for lang, folder in LANGUAGES.items():
        floppy, _ = prepare_pair((artifacts[lang][0] / FLOPPY).read_bytes(), MODEL, SERIALS[0], capacity,
                                 *(bytes(15) + bytes([i]) for i in (1, 2, 3)),
                                 recovery=(MODEL, SERIALS[1], capacity))
        media[f'{folder}/fat-review.img'] = floppy
    media['README.md'] = (ROOT / 'docs/FATFormatReview.md').read_bytes()
    bundle = work / KIT
    with zipfile.ZipFile(bundle, 'x') as archive:
        for name, data in media.items():
            archive.writestr(zipfile.ZipInfo(name), data, compress_type=zipfile.ZIP_DEFLATED)
    delivered = work / 'delivered'
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(delivered)
    for name, expected in media.items():
        if (delivered / name).read_bytes() != expected:
            raise ValueError('Package member differs: ' + name)
    return bundle, delivered, raw, sectors


def io_check(expected, failed_read):
    def verify(trace, devices):
        if 'ide_sector_write' in trace or 'blk_co_pwritev' in trace or any(d['wr_bytes'] for d in devices.values()):
            raise ValueError('The format review wrote to a disk or the floppy')
        if trace_reads(trace) != [lba for _, lba in expected]:
            raise ValueError(f'Unexpected read order ({len(trace_reads(trace))} vs {len(expected)} reads)')
        for drive in ('rb', 'recovery'):
            total = sum(role == drive for role, _ in expected)
            stats = devices.get(drive, {})
            failures = int(failed_read and drive == 'recovery')
            if stats.get('failed_rd_operations', 0) != failures or stats.get('rd_bytes', 0) != (total - failures) * SECTOR:
                raise ValueError(f'{drive}: unexpected physical reads')
        return {}
    return verify


def campaign(qemu, bios, work, shipped, lang, binary, plan, sectors):
    ui = load_catalog(lang)
    floppy = shipped / LANGUAGES[lang] / 'fat-review.img'
    tables = [0, *(v['ebr_lba'] for v in plan['logical'])]
    capacity = plan['disk_bytes'] // SECTOR

    def check(name, slot=1, key=None, *, error=None, failed_lba=None, changed_after=False,
              source=shipped / SYSTEM, clone=shipped / CLONE, source_serial=SERIALS[0],
              clone_serial=SERIALS[1], hook=None, fault=None):
        v = plan['primary'][slot - 1]
        fat = v['fat']
        start = v['start_lba']
        count = (33 if fat['bits'] == 16 else 32 + fat['sectors_per_cluster']) + 2 * fat['sectors_per_fat']
        last = start + count - 1
        ndata = sum(any(data) for at, data in sectors.items() if start <= at // SECTOR <= last)
        view = [('rb', lba) for lba in tables + [start]]
        reads = view * 2
        target = ui['FP_TARGET'] + f' P{slot}'
        lines = [ui['FP_TITLE'], ui['FP_SCOPE'], ui['FR_MODE'], ui['FP_SELECT'], ui['FP_CHOICES'],
                 ui['FP_AUTO'], target, *expected_layout(ui, v, capacity, 'FP_BPB32' if slot == 3 else 'FP_ZERO'),
                 ui['FR_OFFER'], ui['FP_SELECT'], ui['FR_READING']]
        actions = [(ui['FP_SELECT'], str(slot)), (ui['FP_AUTO'], 'ret'), (ui['FP_SELECT'], 'r')]

        def verify_pass(failure, where):
            reads.extend(view)
            if failure not in ('FR_SOURCE_BAD', 'FR_COPY_BAD', 'FR_PROFILE'):
                for lba in tables:
                    if lba:
                        reads.append(('rb', lba))  # BIOS read of each EBR before the two ATA reads
                    reads.extend((('rb', lba), ('recovery', lba)))
                    if lba == where:
                        break
                else:
                    for lba in range(start, (where if where is not None else last) + 1):
                        reads.extend((('rb', lba), ('recovery', lba)))
                    if where is None:
                        reads.extend(view)
            if failure:
                lines.append(ui[failure])
                if where is not None:
                    lines.append(ui['FR_ERROR_LBA'] + f' 0x{where:08X}')

        verify_pass(None if changed_after else error, None if changed_after else failed_lba)
        if key is not None:
            lines += [target, ui['FR_SOURCE'] + ' ' + SERIALS[0], ui['FR_COPY'] + ' ' + SERIALS[1],
                      ui['DISK_ID'] + ' 0x52425431',
                      ui['FP_VOLUME'] + f' 0x{start:08X} - 0x{start + v["sectors"] - 1:08X}', f'FAT{fat["bits"]}',
                      ui['FP_SPC'] + f' {fat["sectors_per_cluster"]}',
                      ui['FR_SPAN'] + f' 0x{start:08X} - 0x{last:08X}', ui['FR_SECTORS'] + f' {count}',
                      ui['FR_NONZERO'] + f' {ndata}', ui['FR_LOSS'], ui['FR_CONFIRM']]
            actions.append((ui['FR_CONFIRM'], key))
            if key == str(slot):
                lines.append(ui['FR_READING'])
                verify_pass(error, failed_lba)
                if not error:
                    lines += [ui['FR_DONE'], 'RB FAT REVIEW PASS']
            else:
                lines.append(ui['FR_CANCEL' if key == 'esc' else 'FR_WRONG'])
        lines += [ui['FP_SELECT'], 'RB FAT PLAN END']
        actions.append((ui['FP_SELECT'], 'esc'))
        boot_fixture(qemu, bios, binary, work, floppy, source, lang + '-' + name, lines,
                     [(s, k, None, True) for s, k in actions], [], [], logical_geometry=GEOMETRY, timeout=90,
                     ata_identity=(MODEL, source_serial), recovery_identity=(MODEL, clone_serial),
                     disk_format='vdi' if source.suffix == '.vdi' else 'raw',
                     recovery_disk=f'blkdebug:{fault}:{clone}' if fault else clone,
                     recovery_format='vdi' if clone and clone.suffix == '.vdi' else 'raw',
                     before_key=hook, io_check=io_check(reads, fault is not None))
        print(f'{lang} {name}: {len(reads)} ordered reads, zero writes', flush=True)

    for slot in (1, 2, 3):
        check(f'confirm-p{slot}', slot, str(slot))
    check('cancel', key='esc')
    check('wrong-slot', key='2')
    check('enter', key='ret')
    check('without-backup', clone=None, error='FR_COPY_BAD')
    check('replacement-backup', clone_serial='VB52429503-33333333', error='FR_COPY_BAD')
    check('swapped', source=shipped / CLONE, clone=shipped / SYSTEM,
          source_serial=SERIALS[1], clone_serial=SERIALS[0], error='FR_SOURCE_BAD')

    corrupt = work / 'changed-enrollment.img'
    changed_floppy = bytearray(floppy.read_bytes())
    changed_floppy[-1] ^= 1
    corrupt.write_bytes(changed_floppy)

    def change_floppy(q, prompt):
        if prompt == ui['FR_CONFIRM']:
            q.call('blockdev-change-medium', {'device': 'floppy', 'filename': str(corrupt),
                                             'format': 'raw', 'read-only-mode': 'read-only'})

    check('changed-enrollment', key='1', changed_after=True, error='FR_PROFILE', hook=change_floppy)

    def change(path, lba):
        with path.open('r+b', buffering=0) as f:
            f.seek(lba * SECTOR)
            f.write(b'X')
            os.fsync(f.fileno())

    first = plan['primary'][0]['start_lba']
    bad = work / 'different.raw'
    write_fixture(bad, plan['disk_bytes'], sectors)
    fault = work / 'unreadable.conf'
    fault.write_text(f'[inject-error]\nevent = "read_aio"\niotype = "read"\nsector = "{first + 9}"\nerrno = "5"\n')
    check('unreadable', clone=bad, error='FR_IO', failed_lba=first + 9, fault=fault)
    for tag, lba in [('mbr', 0), ('ebr', tables[-1]), ('root-end', first + 418)]:
        write_fixture(bad, plan['disk_bytes'], sectors)
        change(bad, lba)
        check('different-' + tag, clone=bad, error='FR_DIFFERENT', failed_lba=lba)

    # Change a disposable medium while the guest is stopped at the target prompt.
    other = work / 'source.raw'
    for both in (False, True):
        write_fixture(bad, plan['disk_bytes'], sectors)
        write_fixture(other, plan['disk_bytes'], sectors)

        def change_at_prompt(q, prompt):
            if prompt == ui['FR_CONFIRM']:
                q.call('stop')
                change(bad, first + 9)
                if both:
                    change(other, first + 9)
                q.call('cont')

        check('changed-' + ('both' if both else 'backup'), key='1', changed_after=True, source=other,
              clone=bad, error='FP_CHANGED' if both else 'FR_DIFFERENT',
              failed_lba=None if both else first + 9, hook=change_at_prompt)


def run(qemu, bios):
    plan = load_plan(ROOT / 'profiles/rb-8g-chs255.json')
    artifacts = builds()
    out = ROOT / 'build/fat-review'
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        bundle, shipped, raw, sectors = package(work, plan, artifacts)
        hashes = {p: sha256(p) for p in shipped.rglob('*') if p.is_file()}
        for name in (SYSTEM, CLONE):
            compare(shipped / name, raw)
        for lang in LANGUAGES:
            campaign(qemu, bios, work, shipped, lang, artifacts[lang][1], plan, sectors)
        for p, before in hashes.items():
            if sha256(p) != before:
                raise ValueError('Guest changed released ' + p.name)
        for name in (SYSTEM, CLONE):
            compare(shipped / name, raw)
        bundle.replace(out / KIT)
        print(f'{KIT} {sha256(out / KIT)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(Path(shutil.which(args.qemu) or args.qemu).resolve(strict=True), args.bios)
