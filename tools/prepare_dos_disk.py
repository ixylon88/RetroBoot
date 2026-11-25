"""Create a prepared RetroBoot disk from a local, installed MS-DOS hard disk."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile
import zlib

try:
    from . import config_records, journal_records, state_records
except ImportError:
    import config_records
    import journal_records
    import state_records

SECTOR = 512
SYSTEM_FILES = {b'IO      SYS', b'MSDOS   SYS', b'COMMAND COM'}


def word(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def dword(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def read_sector(stream, lba):
    stream.seek(lba * SECTOR)
    data = stream.read(SECTOR)
    if len(data) != SECTOR:
        raise ValueError('Incomplete disk sector')
    return data


def dos_volume(stream, size, *, prepared=False):
    mbr = read_sector(stream, 0)
    if size % SECTOR or mbr[510:] != b'\x55\xaa':
        raise ValueError('A complete raw MBR hard disk is required')
    slots = [mbr[446+i*16:462+i*16] for i in range(4)]
    used = [i for i, entry in enumerate(slots) if any(entry)]
    active = [i for i in used if (slots[i][0], slots[i][4]) == (0x80, 6)]
    if len(active) != 1:
        raise ValueError('Expected one active DOS FAT16 primary (type 06h)')
    slot = active[0]
    if prepared:
        extended = 3 if slot != 3 else 2
        if set(used) != {slot, extended} or (slots[extended][0], slots[extended][4]) != (0, 5):
            raise ValueError('Expected a RetroBoot-prepared DOS disk with one management volume')
    elif len(used) != 1:
        raise ValueError('Expected one DOS primary and three empty MBR slots')
    start, length = struct.unpack_from('<II', slots[slot], 8)
    if not start or not 0 < length < 0x400000 or start + length > size // SECTOR:
        raise ValueError('DOS system partition is outside its supported extent')
    vbr = read_sector(stream, start)
    clustersize, reserved, fats, roots = vbr[13], word(vbr, 14), vbr[16], word(vbr, 17)
    small, large, fatsize = word(vbr, 19), dword(vbr, 32), word(vbr, 22)
    spt, heads = struct.unpack_from('<HH', vbr, 24)
    root_sectors = (roots * 32 + SECTOR - 1) // SECTOR
    data_start = reserved + fats * fatsize + root_sectors
    total = small or large
    if (vbr[510:] != b'\x55\xaa' or not (vbr[0] == 0xe9 or vbr[:3:2] == b'\xeb\x90')
            or word(vbr, 11) != SECTOR or dword(vbr, 28) != start or vbr[21] != 0xf8
            or not 0 < clustersize <= 64 or clustersize & (clustersize-1) or not reserved
            or not 1 <= fats <= 2 or not roots or not fatsize or small and large
            or not data_start < total <= length or not 1 <= spt <= 63 or not 1 <= heads <= 256
            or start + length > 1024 * heads * spt):
        raise ValueError('Invalid or incompatible DOS FAT16 boot sector or CHS geometry')
    clusters = (total - data_start) // clustersize
    if not 4085 <= clusters < 65525 or fatsize * 256 < clusters + 2:
        raise ValueError('DOS volume is outside FAT16 cluster bounds')

    stream.seek((start + reserved + fats * fatsize) * SECTOR)
    root = stream.read(roots * 32)
    found = set()
    for offset in range(0, len(root), 32):
        entry = root[offset:offset+32]
        if entry[0] == 0:
            break
        if (entry[0] != 0xe5 and not entry[11] & 0x18 and entry[:11] in SYSTEM_FILES
                and 2 <= word(entry, 26) < clusters + 2 and dword(entry, 28)):
            found.add(entry[:11])
    if found != SYSTEM_FILES:
        raise ValueError('The DOS root must contain IO.SYS, MSDOS.SYS and COMMAND.COM')
    return mbr, slot, start, length, vbr


def partition(kind, start, count, relative, heads, spt):
    def chs(lba):
        cylinder, tail = divmod(lba, heads * spt)
        if cylinder > 1023:
            return b'\xfe\xff\xff'
        head, sector = divmod(tail, spt)
        return bytes((head, (sector+1) | (cylinder >> 2 & 0xc0), cylinder & 255))
    return struct.pack('<B3sB3sII', 0, chs(start), kind, chs(start+count-1), relative, count)


def prepare_copy(disk, kit, countdown=10):
    """The caller owns this new raw output. The source device is never opened here."""
    size = disk.seek(0, os.SEEK_END)
    mbr, slot, start, length, original = dos_volume(disk, size)
    spt, heads = struct.unpack_from('<HH', original, 24)
    with zipfile.ZipFile(kit) as bundle:
        bootcode = bundle.read('mbr.bin')
        volume = bytearray(bundle.read('admin.bin'))
        language = bundle.read('language.txt').decode('ascii')
    if (len(bootcode) != 440 or bootcode[432:436] != b'RBM1'
            or volume[62:66] != b'RBV1' or language not in ('en', 'de')):
        raise ValueError('Invalid RetroBoot disk template')
    # Only the new copy grows. The DOS partition stays at its original CHS/LBA.
    ebr_lba = ((size // SECTOR + spt - 1) // spt) * spt
    admin = ebr_lba + spt
    count = dword(volume, 32)
    total = ((admin + count + 2047) // 2048) * 2048
    if total > 0xffffffff:
        raise ValueError('Prepared disk exceeds 32-bit LBA addressing')
    media = uuid.uuid4().bytes
    disk_id = dword(mbr, 440) or dword(media, 0) or 1
    install_id = int.from_bytes(media[8:], 'little') or 1
    mbr = bytearray(bootcode + mbr[440:])
    struct.pack_into('<II', mbr, 436, admin, disk_id)
    extended_slot = 3 if slot != 3 else 2
    offset = 446 + extended_slot * 16
    mbr[offset:offset+16] = partition(5, ebr_lba, spt+count, ebr_lba, heads, spt)
    ebr = bytearray(SECTOR)
    ebr[446:462] = partition(0x16, admin, count, spt, heads, spt)
    ebr[510:] = b'\x55\xaa'

    data_offset = dword(volume, 66) - dword(volume, 28)
    struct.pack_into('<I', volume, 28, admin)
    struct.pack_into('<I', volume, 66, admin + data_offset)
    struct.pack_into('<H', volume, 72, 0)
    struct.pack_into('<H', volume, 72, -sum(struct.unpack_from('<256H', volume)) & 0xffff)
    binding = dict(disk_id=disk_id, media_id=media, admin_start=admin, admin_sectors=count,
                   layout=config_records.layout_crc({0:mbr, ebr_lba*SECTOR:ebr}))
    entry = dict(slot=slot+1, type=6, start=start, sectors=length, install_id=install_id)
    config = config_records.encode(**binding, profiles=[dict(entry, id=1, name='MS-DOS 6.22',
                                   installed=2, approved=1)], default_id=1, countdown=countdown, language=language)
    state = state_records.encode(**binding, installations=[dict(entry, phase=6, vbr_crc=zlib.crc32(original))])
    journal = journal_records.encode(**binding, before=bytes(mbr), after=bytes(mbr), sequence=1,
                                     phase=journal_records.EMPTY, capacity=total)
    for clusters, record in ((config_records.CLUSTERS, config), (config_records.STATE_CLUSTERS, state),
                             (journal_records.CLUSTERS, journal)):
        for cluster in clusters:
            offset = (data_offset + (cluster-2)*volume[13])*SECTOR
            if not SECTOR <= offset <= len(volume) - len(record):
                raise ValueError('Invalid RetroBoot record allocation')
            volume[offset:offset+len(record)] = record
    disk.truncate(total * SECTOR)
    for lba, data in ((ebr_lba, ebr), (admin, volume), (0, mbr)):
        disk.seek(lba * SECTOR)
        disk.write(data)
    return total, heads, spt


def set_vdi_geometry(path, sectors, heads, spt):
    # VDIHEADER1PLUS stores the BIOS logical geometry after its four UUIDs.
    # A newly converted disk otherwise lets VirtualBox guess from the MBR,
    # which can change the DOS sector translation when capacity grows.
    with path.open('r+b') as vdi:
        header = vdi.read(SECTOR)
        if (len(header) != SECTOR or struct.unpack_from('<II', header, 64) != (0xbeda107f, 0x10001)
                or dword(header, 72) != 400 or dword(header, 76) not in (1, 2)
                or dword(header, 340) < SECTOR or struct.unpack_from('<Q', header, 368)[0] != sectors * SECTOR
                or dword(header, 468) != SECTOR or heads > 255):
            raise ValueError('Unsupported VirtualBox output header or DOS BIOS geometry')
        vdi.seek(456)
        geometry = struct.pack('<III', min(1024, sectors // (heads * spt)), heads, spt)
        vdi.write(geometry)
        vdi.flush()
        os.fsync(vdi.fileno())
        vdi.seek(456)
        if vdi.read(len(geometry)) != geometry:
            raise ValueError('VirtualBox geometry readback failed')


def vboxmanage():
    executable = shutil.which('VBoxManage')
    if not executable:
        candidates = [Path(os.environ.get('VBOX_MSI_INSTALL_PATH', '')) / 'VBoxManage.exe',
                      Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Oracle/VirtualBox/VBoxManage.exe',
                      Path('/Applications/VirtualBox.app/Contents/MacOS/VBoxManage')]
        executable = next((str(p.resolve()) for p in candidates if p.is_absolute() and p.is_file()), None)
    if not executable:
        raise ValueError('VBoxManage was not found. Install VirtualBox or add VBoxManage to PATH.')
    return executable


def check_image(source):
    if source.suffix.lower() not in ('.img', '.raw', '.vdi', '.vhd', '.vmdk') or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError('A local DOS disk image file is required')


def clone_raw(source, raw):
    if source.suffix.lower() in ('.img', '.raw'):
        shutil.copyfile(source, raw)
    else:
        subprocess.run([vboxmanage(), 'clonemedium', 'disk', str(source.resolve()), str(raw),
                        '--format', 'RAW'], check=True)


@contextmanager
def open_reference(source, directory):
    check_image(source)
    if source.suffix.lower() in ('.img', '.raw'):
        with source.open('rb') as stream:
            yield stream
    else:
        with tempfile.TemporaryDirectory(dir=directory) as work:
            raw = Path(work) / 'reference.raw'
            clone_raw(source, raw)
            with raw.open('rb') as stream:
                yield stream


def write_disk_copy(source, output, edit):
    check_image(source)
    if output.suffix.lower() not in ('.img', '.raw', '.vdi'):
        raise ValueError('Output must be a new VDI or raw disk image')
    if os.path.lexists(output):
        raise FileExistsError(f'Output already exists: {output}')
    convert_output = output.suffix.lower() == '.vdi'
    vbox = vboxmanage() if convert_output else None
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        raw = Path(tmp) / 'copy.raw'
        clone_raw(source, raw)
        with raw.open('r+b') as disk:
            geometry = edit(disk)
        if geometry is None:
            return False
        finished = raw
        if convert_output:
            finished = Path(tmp) / 'copy.vdi'
            subprocess.run([vbox, 'convertfromraw', str(raw), str(finished), '--format', 'VDI'], check=True)
            set_vdi_geometry(finished, *geometry)
        # Create the output name only after conversion has succeeded. Both files
        # are on the same volume. A concurrent run cannot replace an existing disk.
        if os.name == 'nt':
            os.rename(finished, output)
        else:
            os.link(finished, output)
    return True


def make_disk(source, output, kit, countdown):
    write_disk_copy(source, output, lambda disk: prepare_copy(disk, kit, countdown))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Powered-off local disk image')
    parser.add_argument('--output', type=Path, help='New VDI or raw output image')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--countdown', type=int, choices=range(61), metavar='0..60', default=10,
                       help='Initial countdown for a newly prepared DOS disk')
    group.add_argument('--set-countdown', nargs='?', const='ask', metavar='0..60',
                       help='Change the countdown on a copy of an already prepared RetroBoot DOS disk')
    group.add_argument('--recover-countdown', action='store_true',
                       help='Restore a damaged countdown copy from its valid peer on a new disk')
    group.add_argument('--require-recovery', action='store_true',
                       help='Block boot of a prepared DOS installation on a new disk copy')
    group.add_argument('--confirm-verification', type=Path, metavar='REFERENCE',
                       help='Approve an observed verification boot on a new copy using a matching pre-trial disk')
    args = parser.parse_args()
    kit = Path(sys.argv[0])
    try:
        if args.set_countdown is None and not (args.recover_countdown or args.require_recovery or args.confirm_verification):
            output = args.output or Path('RetroBoot-DOS.vdi')
            make_disk(args.source, output.absolute(), kit, args.countdown)
        else:
            from prepared_countdown import change_countdown, recover_countdown
            with zipfile.ZipFile(kit) as bundle:
                language = bundle.read('language.txt').decode('ascii')
            if args.confirm_verification:
                from prepared_install_state import confirm_verification
                output = (args.output or Path('RetroBoot-DOS-Ready.vdi')).absolute()
                with open_reference(args.confirm_verification, output.parent) as reference:
                    if not write_disk_copy(args.source, output, lambda disk: confirm_verification(disk, reference, language)):
                        return
                print('DOS-Start freigegeben und geprüft.' if language == 'de' else 'DOS boot approved and verified.')
            elif args.require_recovery:
                from prepared_install_state import require_recovery
                output = args.output or Path('RetroBoot-DOS-Blocked.vdi')
                if not write_disk_copy(args.source, output.absolute(), lambda disk: require_recovery(disk, language)):
                    return
                print('Startsperre gespeichert und geprüft.' if language == 'de' else 'Boot block saved and verified.')
            elif args.recover_countdown:
                output = args.output or Path('RetroBoot-DOS-Recovered.vdi')
                if not write_disk_copy(args.source, output.absolute(), lambda disk: recover_countdown(disk, language)):
                    return
            else:
                seconds = None if args.set_countdown == 'ask' else int(args.set_countdown)
                if seconds is not None and not 0 <= seconds <= 60:
                    raise ValueError('Countdown must be between 0 and 60 seconds')
                output = args.output or Path('RetroBoot-DOS-Countdown.vdi')
                write_disk_copy(args.source, output.absolute(), lambda disk: change_countdown(disk, seconds, language))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f'RetroBoot: {error}\n')
    print(output.resolve())
