"""Bind a FAT format floppy to one original metadata range on a matched disk pair."""
import struct
import zlib

from build_rescue import fat12_set
from prepare_mbr_target import SECTOR, WITNESS_CLUSTER, WITNESS_ENTRY, fat_link, sealed, set_entry

TICKET_CLUSTER = WITNESS_CLUSTER - 1
TICKET_LBA = TICKET_CLUSTER + 31


def ticketed_floppy(floppy, plan, backup, slot, heads, spt):
    if not 1 <= slot <= 4:
        raise ValueError('Expected a primary slot from 1 to 4')
    volume = plan['primary'][slot - 1]
    fat = volume['fat']
    bits = fat['bits']
    fixed = 33 if bits == 16 else 32 + fat['sectors_per_cluster']
    count = fixed + 2 * fat['sectors_per_fat']
    if bits not in (16, 32) or not 0 < count <= min(1024 if bits == 16 else 65535, volume['sectors']):
        raise ValueError('Unsupported FAT metadata range')
    start, digest = volume['start_lba'], [0, 0]

    def sector(lba):
        backup.seek(lba * SECTOR)
        data = backup.read(SECTOR)
        if len(data) != SECTOR:
            raise ValueError('Short read of original disk')
        return data

    def bind(lba, data):
        for i, part in enumerate((data[:508], data[508:])):
            digest[i] = zlib.crc32(struct.pack('<III', digest[i], lba, zlib.crc32(part)))

    mbr = sector(0)
    bind(0, mbr)
    for logical in plan['logical']:
        lba = logical['ebr_lba']
        bind(lba, sector(lba))
    if any(sector(start)):
        raise ValueError('The approved original boot sector must be empty')
    if bits == 32 and any(sector(start + 6)):
        raise ValueError('The approved original FAT32 backup boot sector must be empty')

    # The primary and optional backup VBR are known to be zero and are omitted.
    def bind_occupied(lba):
        data = sector(lba)
        if any(data):
            bind(lba, data)

    for lba in range(start + 1, start + count):
        if bits == 16 or lba != start + 6:
            bind_occupied(lba)
    disk_id, = struct.unpack_from('<I', mbr, 440)
    ticket = sealed(struct.pack('<8s5I2H2I2H', f'RBFMT{bits}1'.encode('ascii'), zlib.crc32(floppy[-512:-4]),
                                disk_id, start, volume['sectors'], count, slot, fat['sectors_per_cluster'],
                                *digest, heads, spt))
    entry, offset = WITNESS_ENTRY + 32, TICKET_LBA * SECTOR
    image = bytearray(floppy)
    fat12 = image[SECTOR:10 * SECTOR]
    if (image[-512:-504] != b'RBTARG03' or fat12 != image[10 * SECTOR:19 * SECTOR]
            or fat_link(fat12, TICKET_CLUSTER) or any(image[offset:offset + SECTOR])
            or any(image[entry:entry + 32])):
        raise ValueError('Expected an enrolled pair with a free ticket cluster and directory entry')
    fat12_set(fat12, TICKET_CLUSTER, 0xfff)
    image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat12
    set_entry(image, entry, f'RBFMT{bits} BIN'.encode('ascii'), 1, TICKET_CLUSTER, 1)
    image[offset:offset + SECTOR] = ticket
    return bytes(image)
