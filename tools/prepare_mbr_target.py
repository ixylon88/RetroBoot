"""Prepare an external boot and recovery pair for one independently identified ATA disk."""
import argparse
import os
from pathlib import Path
import struct
import tempfile
import uuid
import zipfile
import zlib

SECTOR = 512
FLOPPY_BYTES = 2880 * SECTOR
PROFILE_ENTRY = 19 * SECTOR + 64
PROFILE_CLUSTER = 2848
FILE_NAME = b'RBTARGETBIN'
EMPTY_PROFILE = bytes(SECTOR)
WITNESS_ENTRY = PROFILE_ENTRY + 32
WITNESS_CLUSTER = PROFILE_CLUSTER - 5
WITNESS_NAME = b'RBWITNESBIN'
WITNESS_START = (WITNESS_CLUSTER + 31) * SECTOR


def fat_link(fat, cluster):
    pair = struct.unpack_from('<H', fat, cluster + cluster // 2)[0]
    return pair >> 4 if cluster & 1 else pair & 0xfff


def set_entry(image, offset, name, attributes, start, length):
    image[offset:offset + 12] = name + bytes([attributes])
    struct.pack_into('<HI', image, offset + 26, start, length * SECTOR)


def allocate_profile(boot, set_cluster):
    """Reserve fixed, disjoint FAT12 files for the boot profile and witness."""
    image = bytearray(boot)
    fat = bytearray(image[SECTOR:10 * SECTOR])
    if (len(image) != FLOPPY_BYTES or image[PROFILE_ENTRY - 32:PROFILE_ENTRY - 21] != b'RBRESCUEBIN'
            or any(image[PROFILE_ENTRY:WITNESS_ENTRY + 32]) or any(image[WITNESS_START:])
            or fat != image[10 * SECTOR:19 * SECTOR]
            or any(fat_link(fat, c) for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER + 1))):
        raise ValueError('A fresh RetroBoot target image with six free final clusters is required')
    for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER):
        set_cluster(fat, c, 0xfff if c == PROFILE_CLUSTER - 1 else c + 1)
    set_cluster(fat, PROFILE_CLUSTER, 0xfff)
    image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat
    set_entry(image, PROFILE_ENTRY, FILE_NAME, 1, PROFILE_CLUSTER, 1)
    set_entry(image, WITNESS_ENTRY, WITNESS_NAME, 0x20, WITNESS_CLUSTER, 5)
    return bytes(image)


def field(value, width):
    data = value.encode('ascii')
    if not data.strip(b' ') or len(data) > width or any(b < 32 or b > 126 for b in data):
        raise ValueError(f'Expected a printable, nonblank ATA field of at most {width} characters')
    return data.ljust(width, b' ')


def sealed(data):
    body = data.ljust(508, b'\0')
    return body + struct.pack('<I', zlib.crc32(body))


def prepare_pair(boot, model, serial, sectors, target_id, carrier_id, witness_id=None, *, recovery=None):
    at = PROFILE_CLUSTER + PROFILE_CLUSTER // 2
    if (len(boot) != FLOPPY_BYTES or boot[PROFILE_ENTRY:PROFILE_ENTRY + 12] != FILE_NAME + b'\x01'
            or struct.unpack_from('<HI', boot, PROFILE_ENTRY + 26) != (PROFILE_CLUSTER, SECTOR)
            or any(struct.unpack_from('<H', boot, fat + at)[0] & 0xfff != 0xfff for fat in (SECTOR, 10 * SECTOR))
            or boot[-SECTOR:] != EMPTY_PROFILE):
        raise ValueError('Expected a blank mbr-target.img template')
    if not 0 < sectors < 1 << 48 or any(len(i) != 16 or not any(i) for i in (target_id, carrier_id)) or target_id == carrier_id:
        raise ValueError('Invalid ATA capacity or enrollment identities')
    image = bytearray(boot)
    version = b'RBTARG01'
    suffix = b''
    if witness_id is not None:
        fats = (boot[SECTOR:10 * SECTOR], boot[10 * SECTOR:19 * SECTOR])
        if (len(witness_id) != 16 or not any(witness_id) or witness_id in (target_id, carrier_id)
                or boot[WITNESS_ENTRY:WITNESS_ENTRY + 12] != WITNESS_NAME + b'\x20'
                or struct.unpack_from('<HI', boot, WITNESS_ENTRY + 26) != (WITNESS_CLUSTER, 5 * SECTOR)
                or fats[0] != fats[1] or any(boot[WITNESS_START:])
                or any(fat_link(fats[0], c) != (0xfff if c == PROFILE_CLUSTER - 1 else c + 1)
                       for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER))):
            raise ValueError('Invalid or occupied witness enrollment')
        version, suffix = b'RBTARG02', witness_id
        image[WITNESS_START:WITNESS_START + SECTOR] = sealed(b'RBMEDIA1' + witness_id)
    source_fields = field(serial, 20) + field(model, 40)
    carrier_label = sealed(b'RBMEDIA1' + carrier_id)
    if recovery is not None:
        recovery_model, recovery_serial, recovery_sectors = recovery
        recovery_fields = field(recovery_serial, 20) + field(recovery_model, 40)
        if (witness_id is None or boot[3:11] != b'RBTARG03' or recovery_fields == source_fields
                or not 7 <= recovery_sectors < 1 << 48):
            raise ValueError('Expected a current template and a distinct recovery disk with at least seven sectors')
        version = b'RBTARG03'
        suffix += recovery_fields + struct.pack('<Q', recovery_sectors)
    image[-SECTOR:] = sealed(struct.pack('<8s16sQ16s', version, target_id, sectors, carrier_id)
                             + source_fields + suffix)
    return bytes(image), carrier_label if recovery else carrier_label.ljust(FLOPPY_BYTES, b'\0')


def write_pair(template, output, model, serial, sectors):
    image = template.read_bytes()
    # Old capture-only templates have an empty directory slot after RBTARGET.BIN.
    witness = uuid.uuid4().bytes
    if image[WITNESS_ENTRY:WITNESS_ENTRY + 32] == bytes(32):
        if (len(image) != FLOPPY_BYTES or any(image[WITNESS_START:])
                or any(fat_link(image[start:start + 9 * SECTOR], c)
                       for start in (SECTOR, 10 * SECTOR) for c in range(WITNESS_CLUSTER, PROFILE_CLUSTER))):
            raise ValueError('Missing witness directory entry on a used extent')
        witness = None
    boot, carrier = prepare_pair(image, model, serial, sectors, uuid.uuid4().bytes, uuid.uuid4().bytes, witness)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        archive = Path(directory) / 'pair.zip'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('mbr-target.img', boot)
            bundle.writestr('mbr-original-data.img', carrier)
        if os.name == 'nt':
            os.rename(archive, output)
        else:
            os.link(archive, output)


def write_disk_pair(template, output, model, serial, sectors, recovery):
    """Publish a new boot diskette and a sparse, dedicated raw recovery disk."""
    ids = [uuid.uuid4().bytes for _ in range(3)]
    boot, label = prepare_pair(template.read_bytes(), model, serial, sectors, *ids, recovery=recovery)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        stage = Path(directory)
        start = stage / 'mbr-target.img'
        disk = stage / 'mbr-recovery.img'
        with disk.open('xb') as image:
            image.write(label)
            image.truncate(recovery[2] * SECTOR)
        start.write_bytes(boot)
        output.mkdir()  # exclusive even when two preparations target the same directory
        try:
            disk.rename(output / disk.name)
            start.rename(output / start.name)
        except OSError:
            if not disk.exists():
                (output / disk.name).unlink()
            output.rmdir()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--sectors', type=int, required=True, help='Number of 512-byte logical sectors')
    parser.add_argument('--recovery-model')
    parser.add_argument('--recovery-serial')
    parser.add_argument('--recovery-sectors', type=int)
    parser.add_argument('--output', type=Path, required=True,
                        help='New ZIP for two diskettes, or new directory for a dedicated recovery disk')
    args = parser.parse_args()
    try:
        recovery = (args.recovery_model, args.recovery_serial, args.recovery_sectors)
        if all(v is None for v in recovery):
            write_pair(args.template, args.output, args.model, args.serial, args.sectors)
        elif any(v is None for v in recovery):
            parser.error('The recovery disk requires its model, serial and sector count')
        else:
            write_disk_pair(args.template, args.output, args.model, args.serial, args.sectors, recovery)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'RetroBoot: {exc}\n')


if __name__ == '__main__':
    main()
