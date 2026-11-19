"""Pre-enrolled removable-media fixtures for the cold-start MBR reader."""
from dataclasses import dataclass
import struct
import zlib

SECTOR = 512
WITNESS_LBA = 2876
TARGET = bytes(15) + b'\x11'
CARRIER = bytes(15) + b'\x22'
WITNESS = bytes(15) + b'\x33'
RESERVATION_CARRIER = bytes(15) + b'\x44'
RESERVATION_WITNESS = bytes(15) + b'\x55'
CAPACITY = 0x100040000
EMPTY = bytes(SECTOR)


def sector_body(version):
    data = bytearray(SECTOR)
    data[:4] = b'MBR!'
    data[77] = version
    data[440:444] = b'RB01'
    data[510:] = b'\x55\xaa'
    # Changing the bytes before this CRC and resealing preserves the CRC of
    # the whole sector. An exact comparison still distinguishes every version.
    struct.pack_into('<I', data, 428, zlib.crc32(data[:428]))
    return bytes(data)


@dataclass(frozen=True)
class Checkpoint:
    generation: int
    issued: int
    approved: int = 0
    previous: int = 0

    @property
    def payload(self):
        return sector_body(self.approved) if self.approved else EMPTY

    @property
    def slot(self):
        return 3 if self.generation % 2 else 5


ORIGIN = Checkpoint(1, 1)
EARLIER = Checkpoint(4, 3, 3)
CURRENT = Checkpoint(6, 5, 3)
NEXT = Checkpoint(7, 5, 5, 3)


def seal(data):
    result = bytearray(data)
    struct.pack_into('<I', result, 508, zlib.crc32(result[:508]))
    return bytes(result)


def label(endpoint):
    data = bytearray(SECTOR)
    data[:24] = b'RBMEDIA1' + endpoint
    return seal(data)


def header(magic, point, carrier_id=CARRIER):
    data = bytearray(SECTOR)
    struct.pack_into('<8s16sQ16s6I', data, 0, magic, TARGET, CAPACITY, carrier_id,
                     point.generation, point.issued, point.approved, point.previous,
                     zlib.crc32(sector_body(0)), zlib.crc32(point.payload) if point.approved else 0)
    return seal(data)


def put(image, sector, data):
    if len(data) != SECTOR or not 0 <= sector < len(image) // SECTOR:
        raise ValueError('Invalid fixture sector')
    image[sector * SECTOR:(sector + 1) * SECTOR] = data


def witness_floppy(boot, point=CURRENT, witness_id=WITNESS, carrier_id=CARRIER, *, approval_slot=False):
    """Allocate the final FAT12 clusters, including an optional second approval payload."""
    try:
        from .build_rescue import fat12_set
    except ImportError:
        from build_rescue import fat12_set
    if len(boot) != 2880 * SECTOR:
        raise ValueError('Expected a 1.44 MiB boot floppy')
    image = bytearray(boot)
    fat = bytearray(image[SECTOR:10 * SECTOR])
    sectors = 5 if approval_slot else 4
    base = 2880 - sectors
    first = base - 31
    root = 19 * SECTOR + 64
    owned = (image[root:root + 12] == b'RBWITNESBIN\x20'
             and struct.unpack_from('<HI', image, root + 26) == (first, sectors * SECTOR))
    if (image[root - 32:root - 21] != b'RBRESCUEBIN' or (image[root] and not owned)
            or fat != image[10 * SECTOR:19 * SECTOR]):
        raise ValueError('Expected the owned rescue boot fixture and an available witness entry')
    for cluster in range(first, first + sectors):
        link = 0xfff if cluster == first + sectors - 1 else cluster + 1
        pair = struct.unpack_from('<H', fat, cluster + cluster // 2)[0]
        current = (pair >> 4 if cluster & 1 else pair) & 0xfff
        if current != (link if owned else 0):
            raise ValueError('Unexpected allocation in witness extent')
        fat12_set(fat, cluster, link)
    image[SECTOR:10 * SECTOR] = image[10 * SECTOR:19 * SECTOR] = fat
    image[root:root + 12] = b'RBWITNESBIN\x20'
    struct.pack_into('<HI', image, root + 26, first, sectors * SECTOR)
    records = (EMPTY, EMPTY, EMPTY) if point is None else (
        header(b'RBWIT001', point, carrier_id), sector_body(0), point.payload)
    if approval_slot:
        records += (EMPTY,)
    for i, data in enumerate((label(witness_id), *records)):
        put(image, base + i, data)
    return bytes(image)


def stage(image, point, carrier_id=CARRIER):
    put(image, point.slot + 1, point.payload)
    put(image, point.slot, header(b'RBCMT001', point, carrier_id))


def carrier_images(carrier_id=CARRIER):
    """Keep the immutable original and alternate complete publication slots."""
    image = bytearray(2880 * SECTOR)
    put(image, 0, label(carrier_id))
    put(image, 1, header(b'RBORG001', ORIGIN, carrier_id))
    put(image, 2, sector_body(0))
    stage(image, ORIGIN, carrier_id)
    snapshots = {'original-only': bytes(image)}
    for point in (Checkpoint(2, 2), Checkpoint(3, 3), EARLIER, Checkpoint(5, 4, 3), CURRENT):
        stage(image, point, carrier_id)
        if point == EARLIER:
            snapshots['older'] = bytes(image)
    snapshots['current'] = bytes(image)
    stage(image, NEXT, carrier_id)
    snapshots['staged'] = bytes(image)
    return snapshots


def original_media():
    """Separately labelled, controlled media for first-install capture."""
    disk = bytearray(10080 * SECTOR)
    put(disk, 0, sector_body(0))
    put(disk, 10079, label(bytes(15) + b'\x61'))
    carrier = bytearray(2880 * SECTOR)
    put(carrier, 0, label(bytes(15) + b'\x62'))
    return {'mbr-original-hdd.img': bytes(disk), 'mbr-original-data.img': bytes(carrier)}
