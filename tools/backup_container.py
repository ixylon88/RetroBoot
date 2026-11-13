"""Inspect a bounded metadata container; never open a target disk or restore it."""
import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import stat
import struct
import sys
import zlib

SECTOR = 512
MAX_SECTORS = 2048
MAX_ENTRIES = 42
KINDS = ('', 'original-mbr', 'approved-mbr', 'ebr', 'boot-area',
         'config-a', 'config-b', 'state-a', 'state-b')
STATUSES = ('OK', 'IO', 'FORMAT', 'CRC', 'RANGE', 'ORDER', 'OVERLAP', 'MISSING')


class InvalidBackup(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__('Container rejected: ' + STATUSES[status])


@dataclass(frozen=True)
class Identity:
    generation: int
    disk_id: int
    layout_crc: int
    admin_start: int
    admin_sectors: int
    capacity: int
    media_id: bytes
    route: int = 1
    heads: int = 0
    sectors_per_track: int = 0


@dataclass(frozen=True)
class Chunk:
    kind: int
    index: int
    lba: int
    data: bytes
    owner_start: int = 0
    owner_sectors: int = 0


def inspect(data):
    """Check framing/integrity only; claimed identity is not a live-media match."""
    def require(condition, status):
        if not condition:
            raise InvalidBackup(status)

    require(5 * SECTOR <= len(data) <= MAX_SECTORS * SECTOR and len(data) % SECTOR == 0, 2)
    (magic, version, header, size, generation, disk_id, layout, admin, admin_size,
     count, stride, route, heads, spt, reserved, capacity, media, table_crc) = struct.unpack_from(
         '<8sHH6I6HQ16sI', data)
    require(magic == b'RBBAK\0\0\0' and version == 1 and header == SECTOR and size == len(data)
            and 0 < count <= MAX_ENTRIES and stride == 32 and reserved == 0 and not any(data[76:508]), 2)
    require(zlib.crc32(data[:508]) == struct.unpack_from('<I', data, 508)[0], 3)
    require(generation != 0 and disk_id != 0 and any(media) and route in (1, 2)
            and ((route == 1 and heads == spt == 0) or (1 <= heads <= 256 and 1 <= spt <= 63)), 2)

    def extent(start, length):
        return length > 0 and start + length <= min(0xFFFFFFFF, capacity)

    require(admin != 0 and extent(admin, admin_size), 4)
    require(route != 2 or capacity <= 1024 * heads * spt, 4)
    table = data[512:2560]
    require(not any(table[count * 32:]), 2)
    entries = []
    for i in range(count):
        kind, index, lba, sectors, file_sector, crc, owner, owner_size, flags = struct.unpack_from('<HH7I', table, i * 32)
        require(flags == 0, 2)
        entries.append(dict(kind=kind, index=index, lba=lba, sectors=sectors,
                            file_sector=file_sector, crc32=crc, owner_start=owner, owner_sectors=owner_size))
    require(zlib.crc32(table) == table_crc, 3)
    previous, next_index, next_sector, present = 0, 0, 5, set()
    for i, entry in enumerate(entries):
        kind, index = entry['kind'], entry['index']
        lba, sectors = entry['lba'], entry['sectors']
        owner, owner_size = entry['owner_start'], entry['owner_sectors']
        require(1 <= kind <= 8, 2)
        require(kind >= previous, 5)
        if kind != previous:
            next_index = 0
        require(index == next_index and index < (16 if kind == 3 else 20 if kind == 4 else 1), 5)
        previous, next_index = kind, next_index + 1
        present.add(kind)
        require(extent(lba, sectors) and entry['file_sector'] == next_sector
                and sectors <= len(data) // SECTOR - next_sector, 4)
        next_sector += sectors
        if kind <= 3:
            require(sectors == 1 and owner == owner_size == 0 and (lba == 0 if kind <= 2 else lba != 0), 4)
        else:
            require(owner != 0 and extent(owner, owner_size) and owner <= lba
                    and lba + sectors <= owner + owner_size, 4)
            if kind != 4:
                require(sectors == 1 and (owner, owner_size) == (admin, admin_size), 4)
        for other in entries[:i]:
            if kind == 2 and other['kind'] == 1:
                continue
            require(not (lba < other['lba'] + other['sectors'] and other['lba'] < lba + sectors), 6)
    require({1, 2, 4, 5, 6, 7, 8} <= present, 7)
    require(next_sector * SECTOR == len(data), 4)
    for entry in entries:
        begin = entry['file_sector'] * SECTOR
        require(zlib.crc32(data[begin:begin + entry['sectors'] * SECTOR]) == entry['crc32'], 3)
    identity = Identity(generation, disk_id, layout, admin, admin_size, capacity, media, route, heads, spt)
    return identity, entries


def encode(identity, chunks):
    """Serialize explicitly supplied bytes. No disk discovery or collection."""
    if not 0 < len(chunks) <= MAX_ENTRIES or len(identity.media_id) != 16:
        raise InvalidBackup(2)
    table = bytearray(2048)
    payload = bytearray()
    try:
        for i, chunk in enumerate(chunks):
            if not chunk.data or len(chunk.data) % SECTOR or 2560 + len(payload) + len(chunk.data) > MAX_SECTORS * SECTOR:
                raise InvalidBackup(4)
            struct.pack_into('<HH7I', table, i * 32, chunk.kind, chunk.index, chunk.lba,
                             len(chunk.data) // SECTOR, 5 + len(payload) // SECTOR,
                             zlib.crc32(chunk.data), chunk.owner_start, chunk.owner_sectors, 0)
            payload.extend(chunk.data)
        header = bytearray(SECTOR)
        struct.pack_into('<8sHH6I6HQ16sI', header, 0, b'RBBAK\0\0\0', 1, 512, 2560 + len(payload),
                         identity.generation, identity.disk_id, identity.layout_crc,
                         identity.admin_start, identity.admin_sectors, len(chunks), 32,
                         identity.route, identity.heads, identity.sectors_per_track, 0,
                         identity.capacity, identity.media_id, zlib.crc32(table))
        struct.pack_into('<I', header, 508, zlib.crc32(header[:508]))
    except (struct.error, OverflowError) as error:
        raise InvalidBackup(4) from error
    result = bytes(header + table + payload)
    inspect(result)
    return result


def inspect_file(path):
    # Reject device nodes/directories before reading, and cap reads even if a
    # regular file grows after stat. No path is ever opened for writing.
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('A regular container file is required')
    with path.open('rb') as stream:
        data = stream.read(MAX_SECTORS * SECTOR + 1)
    return inspect(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    identity, entries = inspect_file(args.file)
    fields = asdict(identity)
    fields['media_id'] = identity.media_id.hex()
    print(json.dumps(dict(validation='container-integrity-only', live_media_match=False,
                          restore_authorized=False, claimed_identity=fields, entries=entries), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
