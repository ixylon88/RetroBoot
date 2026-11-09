"""Build owned HDD fixtures under build/, never install onto existing media."""

import argparse
import json
import struct
import subprocess
import sys
import zlib

try:
    from .build_abi_probe import prepare_output
    from .retroboot_layout import chs, load_plan, validate_plan
    from .setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256
except ImportError:
    from build_abi_probe import prepare_output
    from retroboot_layout import chs, load_plan, validate_plan
    from setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256

SECTOR = 512
COMPACT_BYTES = 64 * 1024 * 1024
STAGE2_MAX = 0xC000
GEOMETRY = (1024, 255, 63)
CASES = {
    "hdd-fragmented": "RB HDD PASS",
    "hdd-contiguous": "RB HDD PASS",
    "hdd-boundaries": "RB HDD PASS",
    "hdd-reference": "RB HDD PASS",
    "hdd-bad-vbr": "RB MBR ERROR",
    "hdd-outside-disk": "RB MBR ERROR",
    "hdd-bad-bootstrap": "RB VBR ERROR",
    "hdd-bootstrap-count": "RB VBR ERROR",
    "hdd-bad-bpb": "RB BPB ERROR",
    "hdd-bpb-overflow": "RB VBR ERROR",
    "hdd-bpb-beyond-disk": "RB BPB ERROR",
    "hdd-missing": "RB FILE MISSING",
    "hdd-too-large": "RB FILE SIZE ERROR",
    "hdd-short-chain": "RB FAT CHAIN ERROR",
    "hdd-long-chain": "RB FAT CHAIN ERROR",
    "hdd-loop": "RB FAT CHAIN ERROR",
    "hdd-bad-cluster": "RB FAT CHAIN ERROR",
    "hdd-free-cluster": "RB FAT CHAIN ERROR",
    "hdd-fat-range": "RB FAT CHAIN ERROR",
    "hdd-fat-copies": "RB FAT COPIES ERROR",
    "hdd-bad-header": "RB HEADER ERROR",
    "hdd-bad-crc": "RB CRC ERROR",
    "hdd-last-fragment": "RB CRC ERROR",
}


def seal_sum(data, offset):
    """Place the negated little-endian word sum at an aligned checksum slot."""
    if len(data) % 2 or offset % 2 or not 0 <= offset <= len(data) - 2:
        raise ValueError("Invalid checksum bounds")
    result = bytearray(data)
    struct.pack_into("<H", result, offset, 0)
    total = sum(struct.unpack(f"<{len(result) // 2}H", result))
    struct.pack_into("<H", result, offset, -total & 0xFFFF)
    return bytes(result)


def seal_stage2(data):
    if (not 33 <= len(data) <= STAGE2_MAX or data[:6] != b"\xeb\x1eRBS1"
            or struct.unpack_from("<H", data, 6)[0] != 32
            or struct.unpack_from("<I", data, 8)[0] != len(data)
            or struct.unpack_from("<3H", data, 16) != (0x1000, 32, 1)):
        raise ValueError("Invalid stage2 header or memory budget")
    result = bytearray(data)
    struct.pack_into("<I", result, 12, zlib.crc32(data[32:]))
    return bytes(result)


def patch_mbr(sector, code, vbr_lba):
    if (len(sector) != 512 or sector[510:] != b"\x55\xaa"
            or len(code) != 440 or code[432:436] != b"RBM1"
            or not 0 < vbr_lba <= 0xFFFFFFFF):
        raise ValueError("Invalid MBR template, parameter or code budget")
    patched = bytearray(code)
    struct.pack_into("<I", patched, 436, vbr_lba)
    # Disk signature, reserved bytes, all four entries and 55AA survive exactly.
    return bytes(patched) + sector[440:]


def partition_entry(ptype, start, count, relative=None):
    if not (0 < start < start + count <= 0x100000000):
        raise ValueError("Invalid partition bounds")
    first = bytes.fromhex(chs(start, GEOMETRY)["encoded_hex"])
    last = bytes.fromhex(chs(start + count - 1, GEOMETRY)["encoded_hex"])
    return struct.pack("<B3sB3sII", 0, first, ptype, last,
                       start if relative is None else relative, count)


def layout(reference):
    """Return fixture size, admin geometry, and MBR/EBR metadata extents."""
    report = validate_plan(load_plan(ROOT / "profiles/rb-8g-chs255.json"))
    admin = next(v for v in report["volumes"] if v["role"] == "retroboot")
    mbr = bytearray(512)
    struct.pack_into("<I", mbr, 440, 0x52425431)
    mbr[510:] = b"\x55\xaa"
    ebrs = {}
    if reference:
        primaries = [v for v in report["volumes"] if v["kind"] == "primary"]
        logical = [v for v in report["volumes"] if v["kind"] == "logical"]
        extended = next(v for v in primaries if v["role"] == "extended")
        for v in primaries:
            offset = 446 + (v["slot"] - 1) * 16
            mbr[offset:offset + 16] = partition_entry(int(v["type_hex"], 16), v["start_lba"], v["sectors"])
        for i, v in enumerate(logical):
            ebr = bytearray(512)
            ebr[446:462] = partition_entry(int(v["type_hex"], 16), v["start_lba"], v["sectors"], v["data_relative_lba"])
            if i + 1 < len(logical):
                following = logical[i + 1]["ebr_lba"]
                ebr[462:478] = partition_entry(0x05, following,
                    extended["end_lba"] + 1 - following, following - extended["start_lba"])
            ebr[510:] = b"\x55\xaa"
            ebrs[v["ebr_lba"] * SECTOR] = bytes(ebr)
        size = report["disk_bytes"]
    else:
        admin = dict(admin, start_lba=126, ebr_lba=63)
        mbr[494:510] = partition_entry(0x05, 63, 63 + admin["sectors"])
        ebr = bytearray(512)
        ebr[446:462] = partition_entry(0x16, 126, admin["sectors"], 63)
        ebr[510:] = b"\x55\xaa"
        ebrs[63 * SECTOR] = bytes(ebr)
        size = COMPACT_BYTES
    return size, admin, {0: bytes(mbr), **ebrs}


def directory_entry(name, cluster, size):
    if len(name) != 11:
        raise ValueError("An exact 8.3 name is required")
    entry = bytearray(32)
    entry[:11], entry[11] = name, 0x20
    struct.pack_into("<HI", entry, 26, cluster, size)
    return bytes(entry)


def fixture(parts, case):
    """Describe a sparse new image. No external destination or input disk."""
    size, admin, extents = layout(case == "hdd-reference")
    start, count, fat = admin["start_lba"], admin["sectors"], admin["fat"]
    spc, spf = fat["sectors_per_cluster"], fat["sectors_per_fat"]
    cluster_bytes = spc * SECTOR
    root_lba = start + 1 + 2 * spf
    data_lba = root_lba + 32
    bootstrap, stage2 = parts["bootstrap"], bytearray(parts["stage2"])
    if len(bootstrap) > 16 * SECTOR or len(bootstrap) % SECTOR:
        raise ValueError("Invalid contiguous bootstrap length")
    boot_clusters = list(range(2, 2 + (len(bootstrap) + cluster_bytes - 1) // cluster_bytes))
    stage_clusters = [20, 21, 22] if case == "hdd-contiguous" else [20, 300, 40]
    if case == "hdd-boundaries":
        stage_clusters = [25, 151, 40]  # LBAs 503/1007: track/cylinder edges, 16/63
    if len(stage2) != 5000 or len(boot_clusters) > 4:
        raise ValueError("Fixture allocation needs updating for changed payload sizes")
    table = bytearray(spf * SECTOR)
    struct.pack_into("<HH", table, 0, 0xFFF8, 0xFFFF)
    for chain in (boot_clusters, stage_clusters):
        for current, following in zip(chain, chain[1:] + [0xFFFF]):
            struct.pack_into("<H", table, current * 2, following)
    faults = {"hdd-short-chain": 0xFFFF, "hdd-loop": stage_clusters[0],
              "hdd-bad-cluster": 0xFFF7, "hdd-free-cluster": 0,
              "hdd-fat-range": fat["data_clusters"] + 2}
    if case in faults:
        struct.pack_into("<H", table, stage_clusters[0] * 2, faults[case])
    if case == "hdd-long-chain":
        struct.pack_into("<H", table, stage_clusters[-1] * 2, 41)
    table2 = bytearray(table)
    if case == "hdd-fat-copies":
        struct.pack_into("<H", table2, stage_clusters[0] * 2, 0xFFFF)
    root = bytearray(32 * SECTOR)
    root[:32] = directory_entry(b"RBBOOT  SYS", 2, len(bootstrap))
    # Exercise deleted entries, directory/LFN skipping and a second root sector.
    for index in range(1, 20):
        root[index * 32] = 0xE5
    root[32:64] = directory_entry(b"RBSTG2  BIN", 1, 0)
    root[43] = 0x10
    root[64:96] = directory_entry(b"RBSTG2  BIN", 1, 0)
    root[75] = 0x0F
    root[640:672] = directory_entry(b"RBSTG2  BIN", stage_clusters[0],
                                   STAGE2_MAX + 1 if case == "hdd-too-large" else len(stage2))
    if case == "hdd-missing":
        root[640] = 0xE5
    if case == "hdd-bad-header":
        struct.pack_into("<I", stage2, 8, len(stage2) - 1)
    if case == "hdd-bad-crc":
        stage2[100] ^= 1
    if case == "hdd-last-fragment":
        stage2[-1] ^= 1
    vbr = bytearray(parts["vbr"])
    vbr[13] = spc
    struct.pack_into("<H", vbr, 22, spf)
    struct.pack_into("<I", vbr, 28, start)
    struct.pack_into("<I", vbr, 32, count)
    struct.pack_into("<I", vbr, 66, data_lba)
    struct.pack_into("<H", vbr, 70, len(bootstrap) // SECTOR)
    if case == "hdd-bad-bpb":
        vbr[13] = 3
    if case == "hdd-bpb-overflow":
        struct.pack_into("<I", vbr, 32, 0xFFFFFFFF)
    if case == "hdd-bpb-beyond-disk":
        struct.pack_into("<I", vbr, 32, size // SECTOR)
    if case == "hdd-bootstrap-count":
        struct.pack_into("<H", vbr, 70, 0)
    vbr = bytearray(seal_sum(vbr, 72))
    if case == "hdd-bad-vbr":
        vbr[100] ^= 1
    if case == "hdd-bad-bootstrap":
        bootstrap = bytearray(bootstrap)
        bootstrap[100] ^= 1
    extents[0] = patch_mbr(extents[0], parts["mbr"], size // SECTOR if case == "hdd-outside-disk" else start)
    extents[start * SECTOR] = bytes(vbr)
    extents[(start + 1) * SECTOR] = bytes(table)
    extents[(start + 1 + spf) * SECTOR] = bytes(table2)
    extents[root_lba * SECTOR] = bytes(root)
    extents[data_lba * SECTOR] = bytes(bootstrap)
    for index, cluster in enumerate(stage_clusters):
        chunk = stage2[index * cluster_bytes:(index + 1) * cluster_bytes]
        extents[(data_lba + (cluster - 2) * spc) * SECTOR] = bytes(chunk)
    return size, extents


def write_fixture(path, size, extents):
    # The caller permits only fixed names in a checked build directory.
    previous_end = 0
    for offset, data in sorted(extents.items()):
        if offset < previous_end or not data or offset + len(data) > size:
            raise ValueError("Overlapping or out-of-bounds fixture extent")
        previous_end = offset + len(data)
    with path.open("wb") as stream:
        stream.truncate(size)
        for offset, data in sorted(extents.items()):
            stream.seek(offset)
            stream.write(data)


def build(output):
    if output not in ("hdd", "hdd-repeat"):
        raise ValueError("Output must be hdd or hdd-repeat")
    destination = ROOT / "build" / output
    prepare_output(destination)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    nasm = TOOLCHAIN / ("nasm-" + lock["nasm"]["version"]) / "nasm"
    version = subprocess.check_output([str(nasm), "-v"], text=True).strip()
    if version.split()[:3] != ["NASM", "version", lock["nasm"]["version"]]:
        raise ValueError(f"Unexpected assembler: {version}")
    artifacts = {}
    for mode in range(9):
        path = destination / f"int13-{mode}.rom"
        subprocess.run([str(nasm), "-Werror", "-f", "bin", f"-DRB_ROM_MODE={mode}",
                        "tests/bios/int13_rom.asm", "-o", str(path)], cwd=ROOT, check=True)
        rom = bytearray(path.read_bytes())
        if len(rom) != 512 or rom[:3] != b"\x55\xaa\x01":
            raise ValueError("Invalid test option ROM")
        rom[-1] = -sum(rom[:-1]) & 0xFF
        path.write_bytes(rom)
        artifacts[path.name] = {"bytes": len(rom), "sha256": sha256(path)}
    for test in (False, True):
        parts = {}
        for name in ("mbr", "vbr", "bootstrap", "stage2"):
            path = destination / (name + ("-test" if test else "") + ".bin")
            subprocess.run([str(nasm), "-Werror", "-f", "bin", "-I", "./",
                            *(["-DRB_TEST=1"] if test else []), f"boot/{name}.asm", "-o", str(path)],
                           cwd=ROOT, check=True)
            data = path.read_bytes()
            if name == "bootstrap":
                data = bytearray(data)
                struct.pack_into("<H", data, 6, len(data))
                data = seal_sum(data, 8)
            if name == "stage2":
                data = seal_stage2(data)
            path.write_bytes(data)
            parts[name] = data
            artifacts[path.name] = {"bytes": len(data), "sha256": sha256(path)}
        for case in (CASES if test else ("retroboot-hdd",)):
            path = destination / (case + ".img")
            size, extents = fixture(parts, case)
            write_fixture(path, size, extents)
            artifacts[path.name] = {"bytes": size, "sha256": sha256(path)}
    manifest = {"format_version": 1, "purpose": "phase-3-edd-chs-fat16-loader-fixtures",
                "nasm_source": lock["nasm"], "nasm_executable_sha256": sha256(nasm),
                "artifacts": artifacts}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built {output}: MBR 440, VBR 512, bootstrap {len(parts['bootstrap'])}, stage2 {len(parts['stage2'])} bytes", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", action="store_true")
    args = parser.parse_args()
    first = build("hdd")
    if args.repeat and first != build("hdd-repeat"):
        raise ValueError("Repeated HDD builds differ")
    if args.repeat:
        print("Reproducibility: all HDD binaries, images and manifests are identical")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"HDD build: {error}", file=sys.stderr)
        sys.exit(1)
