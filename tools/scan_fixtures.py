"""Owned partition-table mutations; all fixtures still use the normal loader/menu."""

import struct


def case(status, lba=0, slot=0, reads=(0,), **extra):
    return {"status": status, "lba": lba, "slot": slot, "reads": list(reads), **extra}


LONG_EBRS = [63] + [128600 + index * 20 for index in range(15)]
TAIL_LIMIT = 128 * 16 * 63  # stays inside the compact fixture's BIOS CHS reach
SCAN_CASES = {
    "scan-empty": case(0, count=4, ebr_count=0),
    "scan-primary-overlap": case(9, slot=4),
    "scan-primary-overflow": case(7, slot=1),
    "scan-unknown-type": case(5, slot=1),
    "scan-double-active": case(4, slot=2),
    "scan-multiple-extended": case(10, slot=4),
    "scan-ebr-signature": case(2, 63, reads=(0, 63)),
    "scan-ebr-loop": case(12, 63, reads=(0, 63)),
    "scan-ebr-outside": case(8, 63, 2, (0, 63)),
    "scan-logical-overlap": case(9, 100, 1, (0, 63, 100)),
    "scan-ebr-in-data": case(9, 200, reads=(0, 63)),
    "scan-extra-slot": case(11, 63, 3, (0, 63)),
    "scan-many": case(0, reads=(0, *LONG_EBRS), count=20, ebr_count=16),
    "scan-limit": case(13, 128900, reads=(0, *LONG_EBRS)),
    "scan-ebr-io": case(1, 63, reads=(0, 63, 63, 63), fault_once=False),
    "scan-ebr-retry": case(0, reads=(0, 63, 63), count=5, ebr_count=1, fault_once=True),
}


def entry(block, slot, ptype, start, sectors, flag=0):
    """CHS bytes intentionally zero: the scanner must use checked LBA values."""
    offset = 446 + slot * 16
    block[offset:offset + 16] = struct.pack("<B3sB3sII", flag, bytes(3), ptype, bytes(3), start, sectors)


def mutate_scan_fixture(size, original, name):
    if name not in SCAN_CASES:
        raise ValueError("Unknown partition scan fixture")
    extents = dict(original)
    mbr, ebr = bytearray(extents[0]), bytearray(extents[63 * 512])
    if name == "scan-empty":
        mbr[446:510] = bytes(64)
    elif name == "scan-primary-overlap":
        entry(mbr, 0, 0x06, 63, 100)
    elif name == "scan-primary-overflow":
        entry(mbr, 0, 0x06, 0xFFFFFFF0, 32)
    elif name == "scan-unknown-type":
        entry(mbr, 0, 0xEE, 1, 62)
    elif name == "scan-double-active":
        entry(mbr, 0, 0x06, 1, 20, 0x80)
        entry(mbr, 1, 0x07, 21, 20, 0x80)
    elif name == "scan-multiple-extended":
        entry(mbr, 0, 0x05, 1, 20)
    elif name == "scan-ebr-signature":
        ebr[510] = 0
    elif name == "scan-ebr-loop":
        entry(ebr, 1, 0x05, 0, 128520)
    elif name == "scan-ebr-outside":
        entry(ebr, 1, 0x05, 131072, 1)
    elif name == "scan-logical-overlap":
        entry(ebr, 1, 0x05, 37, 128483)
        second = bytearray(512)
        second[510:] = b"\x55\xaa"
        entry(second, 0, 0x06, 27, 50)
        extents[100 * 512] = bytes(second)
    elif name == "scan-ebr-in-data":
        entry(ebr, 1, 0x05, 137, 128383)
    elif name == "scan-extra-slot":
        entry(ebr, 2, 0x06, 1, 1)
    elif name in ("scan-many", "scan-limit"):
        # Keep the complete real FAT16 admin volume, place extra tiny logical
        # extents in the unused tail of the compact disk, and enlarge only P4.
        limit = TAIL_LIMIT
        if limit > size // 512:
            raise ValueError("Compact scan fixture is too small")
        entry(mbr, 3, 0x05, 63, limit - 63)
        ebrs = LONG_EBRS + ([128900] if name == "scan-limit" else [])
        for index, lba in enumerate(ebrs):
            block = ebr if index == 0 else bytearray(512)
            block[510:] = b"\x55\xaa"
            if index:
                entry(block, 0, 0x06, 1, 10)
            if index + 1 < len(ebrs):
                following = ebrs[index + 1]
                entry(block, 1, 0x05, following - 63, limit - following)
            if index:
                extents[lba * 512] = bytes(block)
    extents[0], extents[63 * 512] = bytes(mbr), bytes(ebr)
    return extents
