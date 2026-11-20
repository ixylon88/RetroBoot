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


def allocate_profile(boot, set_cluster):
    """Reserve the final, otherwise free FAT12 cluster of a newly built boot image."""
    image = bytearray(boot)
    fat = bytearray(image[SECTOR:10 * SECTOR])
    at = PROFILE_CLUSTER + PROFILE_CLUSTER // 2
    if (len(image) != FLOPPY_BYTES or image[PROFILE_ENTRY - 32:PROFILE_ENTRY - 21] != b'RBRESCUEBIN'
            or any(image[PROFILE_ENTRY:PROFILE_ENTRY + 32]) or any(image[-SECTOR:])
            or fat != image[10 * SECTOR:19 * SECTOR] or struct.unpack_from('<H', fat, at)[0] & 0xfff):
        raise ValueError('A fresh RetroBoot target image with a free profile cluster is required')
    set_cluster(fat, PROFILE_CLUSTER, 0xfff)
    image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat
    image[PROFILE_ENTRY:PROFILE_ENTRY + 12] = FILE_NAME + b'\x01'
    struct.pack_into('<HI', image, PROFILE_ENTRY + 26, PROFILE_CLUSTER, SECTOR)
    return bytes(image)


def field(value, width):
    data = value.encode('ascii')
    if not data.strip(b' ') or len(data) > width or any(b < 32 or b > 126 for b in data):
        raise ValueError(f'Expected a printable, nonblank ATA field of at most {width} characters')
    return data.ljust(width, b' ')


def sealed(data):
    body = data.ljust(508, b'\0')
    return body + struct.pack('<I', zlib.crc32(body))


def prepare_pair(boot, model, serial, sectors, target_id, carrier_id):
    at = PROFILE_CLUSTER + PROFILE_CLUSTER // 2
    if (len(boot) != FLOPPY_BYTES or boot[PROFILE_ENTRY:PROFILE_ENTRY + 12] != FILE_NAME + b'\x01'
            or struct.unpack_from('<HI', boot, PROFILE_ENTRY + 26) != (PROFILE_CLUSTER, SECTOR)
            or any(struct.unpack_from('<H', boot, fat + at)[0] & 0xfff != 0xfff for fat in (SECTOR, 10 * SECTOR))
            or boot[-SECTOR:] != EMPTY_PROFILE):
        raise ValueError('Expected a blank mbr-target.img template')
    if not 0 < sectors < 1 << 48 or any(len(i) != 16 or not any(i) for i in (target_id, carrier_id)) or target_id == carrier_id:
        raise ValueError('Invalid ATA capacity or enrollment identities')
    profile = sealed(struct.pack('<8s16sQ16s', b'RBTARG01', target_id, sectors, carrier_id)
                     + field(serial, 20) + field(model, 40))
    carrier = sealed(b'RBMEDIA1' + carrier_id) + bytes(FLOPPY_BYTES - SECTOR)
    return boot[:-SECTOR] + profile, carrier


def write_pair(template, output, model, serial, sectors):
    boot, carrier = prepare_pair(template.read_bytes(), model, serial, sectors, uuid.uuid4().bytes, uuid.uuid4().bytes)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        archive = Path(directory) / 'pair.zip'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('mbr-target.img', boot)
            bundle.writestr('mbr-original-data.img', carrier)
        if os.name == 'nt':
            os.rename(archive, output)
        else:
            os.link(archive, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('template', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--sectors', type=int, required=True, help='Number of 512-byte logical sectors')
    parser.add_argument('--output', type=Path, required=True, help='New ZIP file for this enrollment')
    args = parser.parse_args()
    try:
        write_pair(args.template, args.output, args.model, args.serial, args.sectors)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'RetroBoot: {exc}\n')


if __name__ == '__main__':
    main()
