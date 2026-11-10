"""Owned, explicitly authorized T07 fixture; no arbitrary OS entry point."""
import struct

LBA = 131072
SECTORS = 5073
DISK_ID = 0x52425431
IMAGE_BYTES = 128 * 1024 * 1024
FAULTS = {name: i for i, name in enumerate(
    ("ds", "es", "ss", "sp", "si", "dl", "df", "if", "entry"), 1)}
HANDOFF_CASES = {
    "retroboot-handoff": {},
    "handoff-signature": {"status": 3, "detail": 2},
    "handoff-bpb": {"status": 3, "detail": 10},
    "handoff-code": {"status": 4, "detail": 0},
    "handoff-chs-entry": {"status": 1, "detail": 0},
    "handoff-inactive": {"status": 1, "detail": 0},
    "handoff-tables": {"status": 2, "detail": 5},
    "handoff-identity": {"status": 2, "detail": 3},
    "handoff-ebr": {"status": 2, "detail": 2},
    "handoff-io": {"status": 3, "detail": 1, "fault_once": False},
    "handoff-retry": {"fault_once": True},
    **{"handoff-register-" + name: {"register_fault": name} for name in FAULTS},
}


def entry_bytes():
    def chs(lba):
        cylinder, remainder = divmod(lba, 255 * 63)
        head, sector = divmod(remainder, 63)
        return bytes((head, sector + 1 | ((cylinder >> 8) << 6), cylinder & 255))
    return struct.pack("<B3sB3sII", 0x80, chs(LBA), 0x06, chs(LBA + SECTORS - 1), LBA, SECTORS)


def assembler_header():
    return (f"%define RB_TEST_LBA {LBA}\n%define RB_TEST_ENTRY_BYTES "
            + ",".join(str(b) for b in entry_bytes()) + "\n")


def c_header(vbr):
    if len(vbr) != 512 or vbr[510:] != b"\x55\xaa":
        raise ValueError("Invalid handoff test VBR")
    lines = ["/* Generated test-only binding; never an OS authorization. */",
             f"#define RB_TEST_DISK_ID 0x{DISK_ID:08X}UL"]
    for name, data in (("entry", entry_bytes()), ("vbr", vbr)):
        lines += [f"static const rb_u8 rb_test_{name}[{len(data)}] = {{"]
        lines += ["    " + ",".join(f"0x{b:02X}" for b in data[i:i + 16]) + ","
                  for i in range(0, len(data), 16)]
        lines += ["};"]
    return "\n".join(lines) + "\n"


def mutate_handoff_fixture(size, source, name, vbr):
    if size != 64 * 1024 * 1024 or name not in HANDOFF_CASES:
        raise ValueError("Unknown handoff fixture or unexpected base image")
    c_header(vbr)
    extents, mbr, sector = dict(source), bytearray(source[0]), bytearray(vbr)
    mbr[446:462] = entry_bytes()
    if name == "handoff-signature": sector[510] = 0
    elif name == "handoff-bpb": struct.pack_into("<I", sector, 28, LBA + 1)
    elif name == "handoff-code": sector[509] ^= 1
    elif name == "handoff-chs-entry": mbr[447] ^= 1
    elif name == "handoff-inactive": mbr[446] = 0
    elif name == "handoff-tables": mbr[450] = 0x83
    elif name == "handoff-identity": mbr[440] ^= 1
    elif name == "handoff-ebr":
        ebr = bytearray(source[63 * 512]); ebr[510] = 0
        extents[63 * 512] = bytes(ebr)
    extents[0], extents[LBA * 512] = bytes(mbr), bytes(sector)
    return IMAGE_BYTES, extents
