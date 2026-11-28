"""Cold-boot the released test disk under FreeDOS and independently inspect DOS file I/O."""
import argparse
from collections import Counter
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_dos_guest import DISK, FLOPPY, KIT, OUT, catalog, marker
from build_hdd import SECTOR
from setup_toolchain import sha256
from test_fat_format_plan import GEOMETRY, LANGUAGES
from test_fat_format_write import FAT16, FAT32
from test_menu import Qmp, screen_rows, wait_marker


def payload(slot):
    return bytes(((i % 256 ^ (i % 1024 // 256)) + i // 1024 + slot) % 256 for i in range(96 * 1024 + 17))


def boot(qemu, bios, work, disk, floppy, lang, ref, name, keys, outcome, *, writes=False):
    ui = catalog(lang)
    log, trace = work / 'debug.log', work / 'ide.trace'
    log.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    cylinders, heads, spt = GEOMETRY
    fmt = 'vdi' if disk.suffix == '.vdi' else 'raw'
    args = [qemu, '-L', str(bios.parent), '-bios', bios, '-machine', 'pc-i440fx-8.2,accel=tcg',
            '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-display', 'none',
            '-boot', 'a', '-nic', 'none', '-monitor', 'none', '-serial', 'none', '-qmp', 'stdio',
            '-global', 'isa-debugcon.iobase=0xe9', '-debugcon', 'file:' + str(log),
            '-trace', f'enable=ide_sector_write,file={trace}',
            '-drive', f'file={floppy},if=floppy,id=floppy,format=raw,readonly=on',
            '-drive', f'file={disk},if=none,id=target,format={fmt},cache=writethrough',
            '-device', f'ide-hd,drive=target,bus=ide.0,unit=0,lcyls={cylinders},lheads={heads},lsecs={spt}']
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1) as proc:
        try:
            q = Qmp(proc)
            visits = Counter()
            for prompt, key in keys:
                visits[prompt] += 1
                wait_marker(proc, log, ui[prompt] + '\n', timeout=25, encoding='cp437', occurrence=visits[prompt])
                q.call('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 30})
            wait_marker(proc, log, ui['restart'] + '\n', encoding='cp437')
            q.call('stop')
            vga = work / 'vga.bin'
            q.call('pmemsave', {'val': 0xb8000, 'size': 4000, 'filename': str(vga)})
            screen = '\n'.join(screen_rows(vga.read_bytes()))
            transcript = log.read_text(encoding='cp437').splitlines()
            if any(line not in screen or line not in transcript for line in outcome):
                raise ValueError(f'{name}: missing {outcome} in {transcript}')
            stats = {s['device']: s['stats'] for s in q.call('query-blockstats') if s.get('device')}
            if stats['floppy']['wr_bytes']:
                raise ValueError(f'{name}: guest wrote to the floppy')
            q.call('quit')
            if proc.wait(timeout=5):
                raise ValueError(f'{name}: QEMU exited with an error')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    spans = [(int(lba), int(n)) for lba, n in re.findall(
        r'ide_sector_write sector=(\d+) nsectors=(\d+)', trace.read_text())]
    if (sum(n for lba, n in spans) * SECTOR != stats['target']['wr_bytes']
            or bool(spans) != writes or any(n < 1 or lba < ref.start or lba + n > ref.start + ref.length
                                            for lba, n in spans)):
        raise ValueError(f'{name}: unexpected physical HDD writes {spans}')
    print(f'{lang} P{ref.slot} {name}: {", ".join(outcome)}, {sum(n for _, n in spans)} sectors written', flush=True)


def convert_raw(vdi, raw):
    subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', vdi, raw], check=True)


def host_inspect(work, disk, ref, present):
    raw, part = work / 'check.raw', work / 'volume.raw'
    convert_raw(disk, raw)
    subprocess.run(['dd', 'if=' + str(raw), 'of=' + str(part), 'bs=1M', 'iflag=skip_bytes,count_bytes,fullblock',
                    f'skip={ref.start * SECTOR}', f'count={ref.length * SECTOR}', 'conv=sparse', 'status=none'],
                   check=True)
    subprocess.run(['fsck.fat', '-n', part], check=True)
    guard = subprocess.check_output(['mtype', '-i', part, '::RBT11.ID'])
    if guard != marker(ref.slot):
        raise ValueError('Volume identifier changed')
    listing = subprocess.check_output(['mdir', '-b', '-i', part, '::'], text=True).upper().splitlines()
    names = sorted(name.rsplit('/', 1)[-1] for name in listing)
    expected = ['RBT11.DAT', 'RBT11.ID'] if present else ['RBT11.ID']
    if names != expected:
        raise ValueError(f'Unexpected P{ref.slot} root directory: {names}')
    if present and subprocess.check_output(['mtype', '-i', part, '::RBT11.DAT']) != payload(ref.slot):
        raise ValueError(f'Host readback disagrees on P{ref.slot}')
    with part.open('rb') as stream:
        if ref.bits == 32:
            primary = stream.read(3 * SECTOR)
            stream.seek(6 * SECTOR)
            backup = stream.read(3 * SECTOR)
            # DOS can update the primary FSInfo hints independently. The other
            # bytes in the three-sector record must still match the backup.
            hints = SECTOR + 488
            if primary[:hints] != backup[:hints] or primary[hints + 8:] != backup[hints + 8:]:
                raise ValueError('FAT32 primary and backup boot records disagree')
            for record in (primary, backup):
                info = record[SECTOR:2 * SECTOR]
                free, next_free = struct.unpack_from('<II', info, 488)
                if (info[:4] != b'RRaA' or info[484:488] != b'rrAa' or info[508:] != b'\x00\x00\x55\xaa'
                        or (free != 0xffffffff and free > 392819)
                        or (next_free != 0xffffffff and not 2 <= next_free <= 392820)):
                    raise ValueError('Invalid FAT32 FSInfo signatures or allocation hints')
        reserved, fat_size = (1, 193) if ref.bits == 16 else (32, 3075)
        stream.seek(reserved * SECTOR)
        if stream.read(fat_size * SECTOR) != stream.read(fat_size * SECTOR):
            raise ValueError('DOS left different FAT copies')


def run(qemu, bios, work, kit):
    with zipfile.ZipFile(kit) as archive:
        archive.extractall(work)
    originals = {p: sha256(p) for p in work.rglob('*') if p.is_file()}
    for lang, folder in LANGUAGES.items():
        ui, floppy = catalog(lang), work / folder / FLOPPY
        disk = work / 'working.vdi'
        shutil.copyfile(work / DISK, disk)
        for ref in (FAT16, FAT32):
            select = [('select', str(ref.slot))]
            write = select + [('write_menu', 'w')]
            read = select + [('write_menu', 'v')]

            def case(name, keys, outcome, **kwargs):
                boot(qemu, bios, work, disk, floppy, lang, ref, name, keys, outcome, **kwargs)

            case('create', write, ['RB DOS WRITE PASS'], writes=True)
            if lang == 'en':
                host_inspect(work, disk, ref, True)
            case('no overwrite', write, [ui['create_bad'], 'RB DOS BLOCKED'])
            case('cold read and keep', read + [('delete_menu', 'esc')], ['RB DOS READ PASS', 'RB DOS END'])
            case('cold read and delete', read + [('delete_menu', 'd')],
                 ['RB DOS READ PASS', 'RB DOS DELETE PASS'], writes=True)
            if lang == 'en':
                host_inspect(work, disk, ref, False)
            case('deleted file absent', read, [ui['file_bad'], 'RB DOS BLOCKED'])

    # Preserve independently planted data on every refusal, including a mismatched
    # marker on a volume that still has the expected serial and vice versa.
    for ref in (FAT16, FAT32):
        disk, floppy = work / 'changed.raw', work / 'English' / FLOPPY
        ui = catalog('en')
        select = [('select', str(ref.slot))]
        select_read = select + [('write_menu', 'v')]
        image = f'{disk}@@{ref.start * SECTOR}'
        content = payload(ref.slot)
        for name, data in (('truncated', content[:-1]), ('trailing byte', content + b'X'),
                           ('changed block', content[:65536] + bytes([content[65536] ^ 1]) + content[65537:])):
            convert_raw(work / DISK, disk)
            other = work / 'other.bin'
            other.write_bytes(data)
            subprocess.run(['mcopy', '-i', image, other, '::RBT11.DAT'], check=True)
            boot(qemu, bios, work, disk, floppy, 'en', ref, name, select_read, [ui['file_bad'], 'RB DOS BLOCKED'])
            if subprocess.check_output(['mtype', '-i', image, '::RBT11.DAT']) != data:
                raise ValueError('Refusal changed the pre-existing file')
        convert_raw(work / DISK, disk)
        subprocess.run(['mattrib', '-i', image, '-r', '::RBT11.ID'], check=True)
        other.write_bytes(marker(3 - ref.slot))
        subprocess.run(['mcopy', '-o', '-i', image, other, '::RBT11.ID'], check=True)
        boot(qemu, bios, work, disk, floppy, 'en', ref, 'wrong identifier', select, [ui['target_bad'], 'RB DOS BLOCKED'])
        subprocess.run(['mdel', '-i', image, '::RBT11.ID'], check=True)
        boot(qemu, bios, work, disk, floppy, 'en', ref, 'missing identifier', select, [ui['target_bad'], 'RB DOS BLOCKED'])
        convert_raw(work / DISK, disk)
        with disk.open('r+b') as stream:
            for relative in ((0,) if ref.bits == 16 else (0, 6)):
                stream.seek((ref.start + relative) * SECTOR + (39 if ref.bits == 16 else 67))
                stream.write(b'NOPE')
        boot(qemu, bios, work, disk, floppy, 'en', ref, 'wrong serial', select, [ui['target_bad'], 'RB DOS BLOCKED'])
    # INSTALL runs the same .COM without /BOOT as an ordinary DOS child.
    # Its return lets the kernel start its configured shell for the second menu.
    child_boot = work / 'child.img'
    shutil.copyfile(work / 'English' / FLOPPY, child_boot)
    config = work / 'FDCONFIG.SYS'
    config.write_bytes(b'INSTALL=A:\\RBT11.COM\r\nSHELL=A:\\RBT11.COM /BOOT\r\n')
    subprocess.run(['mcopy', '-o', '-i', child_boot, config, '::FDCONFIG.SYS'], check=True)
    disk = work / 'child.vdi'
    shutil.copyfile(work / DISK, disk)
    boot(qemu, bios, work, disk, child_boot, 'en', FAT16, 'ordinary DOS child returns',
         [('select', '1'), ('write_menu', 'w'), ('select', '1'), ('write_menu', 'v'), ('delete_menu', 'd')],
         ['RB DOS WRITE PASS', 'RB DOS READ PASS', 'RB DOS DELETE PASS'], writes=True)
    if any(sha256(p) != digest for p, digest in originals.items()):
        raise ValueError('A delivered kit member changed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(dir=OUT) as folder:
        run(shutil.which(args.qemu) or args.qemu, args.bios, Path(folder), OUT / KIT)
