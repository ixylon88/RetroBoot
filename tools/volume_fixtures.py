"""Owned 128 MiB header fixtures; no OS code or filesystem contents implied."""

import struct

VOLUME_BYTES = 128 * 1024 * 1024
FIRST_LBA = 131072
SECOND_LBA = 140000
VOLUME_CASES = {
    "volume-headers": {"status": 0, "target": 0},
    "volume-signature": {"status": 2, "target": 0},
    "volume-jump": {"status": 3, "target": 0},
    "volume-sector": {"status": 4, "target": 0},
    "volume-cluster": {"status": 5, "target": 0},
    "volume-reserved": {"status": 6, "target": 0},
    "volume-fats": {"status": 7, "target": 0},
    "volume-root": {"status": 8, "target": 0},
    "volume-total": {"status": 9, "target": 0},
    "volume-hidden": {"status": 10, "target": 0},
    "volume-layout": {"status": 11, "target": 0},
    "volume-type": {"status": 12, "target": 0},
    "volume-fat-small": {"status": 13, "target": 0},
    "volume-fat32": {"status": 14, "target": 1},
    "volume-media": {"status": 17, "target": 0},
    "volume-io": {"status": 1, "target": 0, "fault_once": False},
    "volume-retry": {"status": 0, "target": 0, "fault_once": True},
    "volume-bad-tables": {"table_status": 5},
    "volume-no-data": {"empty": True},
}


def header(bits, start):
    """Deliberately header-only fixtures: no FAT, directory or boot program."""
    block = bytearray(512)
    block[:3] = bytes((0xEB, 60 if bits == 16 else 88, 0x90))
    block[3:11] = b"RBTEST  "
    struct.pack_into("<HBHBHHB", block, 11, 512, 1, 1 if bits == 16 else 32,
                     2, 512 if bits == 16 else 0, 0, 0xF8)
    struct.pack_into("<H", block, 22, 20 if bits == 16 else 0)
    struct.pack_into("<II", block, 28, start, 5073 if bits == 16 else 71126)
    if bits == 32:
        struct.pack_into("<IHHIHH", block, 36, 547, 0, 0, 2, 1, 6)
    block[510:] = b"\x55\xaa"
    return block


def mutate_volume_fixture(size, source, name):
    if name not in VOLUME_CASES or size != 64 * 1024 * 1024:
        raise ValueError("Unknown volume fixture or unexpected base image")
    extents = dict(source)
    mbr = bytearray(source[0])
    # All three test volumes follow the complete original extended container.
    for slot, kind, start, length in ((0, 0x06, FIRST_LBA, 5073),
                                     (1, 0x0B, SECOND_LBA, 71126),
                                     (2, 0x07, 220000, 8192)):
        struct.pack_into("<B3sB3sII", mbr, 446 + slot * 16, 0, b"\xfe\xff\xff",
                         kind, b"\xfe\xff\xff", start, length)
    first, second = header(16, FIRST_LBA), header(32, SECOND_LBA)
    if name == "volume-signature": first[510] = 0
    elif name == "volume-jump": first[0] = 0
    elif name == "volume-sector": struct.pack_into("<H", first, 11, 4096)
    elif name == "volume-cluster": first[13] = 3
    elif name == "volume-reserved": struct.pack_into("<H", first, 14, 0)
    elif name == "volume-fats": first[16] = 0
    elif name == "volume-root": struct.pack_into("<H", first, 17, 0)
    elif name == "volume-total": struct.pack_into("<I", first, 32, 5074)
    elif name == "volume-hidden": struct.pack_into("<I", first, 28, FIRST_LBA + 1)
    elif name == "volume-layout": struct.pack_into("<H", first, 22, 3000)
    elif name == "volume-type": first[13] = 2
    elif name == "volume-fat-small": struct.pack_into("<H", first, 22, 19)
    elif name == "volume-fat32": struct.pack_into("<H", second, 40, 0x82)
    elif name == "volume-media": first[21] = 0
    elif name == "volume-bad-tables": mbr[450] = 0x83
    elif name == "volume-no-data": mbr[446:510] = bytes(64)
    extents.update({0: bytes(mbr), FIRST_LBA * 512: bytes(first), SECOND_LBA * 512: bytes(second)})
    return VOLUME_BYTES, extents
