"""Build owned HDD fixtures under build/, never install onto existing media."""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import zlib

try:
    from .journal_fixtures import JOURNAL_CASES, mutate as mutate_journal_fixture
    from .journal_records import model_header as journal_model_header, io_model_header, allocate as allocate_journal, baseline as journal_baseline
    from .audit_fixtures import AUDIT_CASES, mutate_audit_fixture
    from .state_records import encode as encode_state, model_header as state_model_header
    from .config_fixtures import CONFIG_CASES, mutate_config_fixture
    from .state_fixtures import STATE_CASES, mutate_state_fixture
    from .profile_fixtures import PROFILE_CASES, mutate_profile_fixture
    from .visibility_fixtures import VISIBILITY_CASES, mutate_visibility_fixture
    from .config_records import install_records, model_header, encode as encode_config, layout_crc, CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID
    from .build_abi_probe import inspect_map, prepare_output
    from .retroboot_layout import chs, load_plan, validate_plan
    from .setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify
    from .handoff_fixtures import HANDOFF_CASES, FAULTS, assembler_header, c_header, mutate_handoff_fixture
    from .volume_fixtures import VOLUME_CASES, mutate_volume_fixture
    from .scan_fixtures import SCAN_CASES, mutate_scan_fixture
    from .ui_text import LANGUAGES, catalog_metadata, load_catalog, output_name, render_header
except ImportError:
    from journal_fixtures import JOURNAL_CASES, mutate as mutate_journal_fixture
    from journal_records import model_header as journal_model_header, io_model_header, allocate as allocate_journal, baseline as journal_baseline
    from audit_fixtures import AUDIT_CASES, mutate_audit_fixture
    from state_records import encode as encode_state, model_header as state_model_header
    from config_fixtures import CONFIG_CASES, mutate_config_fixture
    from state_fixtures import STATE_CASES, mutate_state_fixture
    from profile_fixtures import PROFILE_CASES, mutate_profile_fixture
    from visibility_fixtures import VISIBILITY_CASES, mutate_visibility_fixture
    from config_records import install_records, model_header, encode as encode_config, layout_crc, CLUSTERS, STATE_CLUSTERS, FIXTURE_MEDIA_ID, TEST_INSTALL_ID
    from build_abi_probe import inspect_map, prepare_output
    from retroboot_layout import chs, load_plan, validate_plan
    from setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify
    from handoff_fixtures import HANDOFF_CASES, FAULTS, assembler_header, c_header, mutate_handoff_fixture
    from volume_fixtures import VOLUME_CASES, mutate_volume_fixture
    from scan_fixtures import SCAN_CASES, mutate_scan_fixture
    from ui_text import LANGUAGES, catalog_metadata, load_catalog, output_name, render_header

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
    "hdd-old-header": "RB HEADER ERROR",
    "hdd-bss-overlap": "RB HEADER ERROR",
    "hdd-bss-overflow": "RB HEADER ERROR",
    "hdd-bss-empty": "RB HEADER ERROR",
    "hdd-stack-contract": "RB HEADER ERROR",
    "hdd-header-flags": "RB HEADER ERROR",
    "hdd-c-bss-fault": "RB C STARTUP ERROR",
    "hdd-c-data-fault": "RB C STARTUP ERROR",
    "hdd-c-stack-fault": "RB C STARTUP ERROR",
    "hdd-c-context-fault": "RB C STARTUP ERROR",
    "hdd-menu-model": "RB HDD PASS",
    "hdd-scan-model": "RB HDD PASS",
    "hdd-volume-model": "RB HDD PASS",
    "hdd-handoff-model": "RB HDD PASS",
    "hdd-config-model": "RB HDD PASS",
    "hdd-state-model": "RB HDD PASS",
    "hdd-visibility-model": "RB HDD PASS",
    "hdd-profile-model": "RB HDD PASS",
    "hdd-audit-model": "RB HDD PASS",
    "hdd-journal-model": "RB HDD PASS",
    "hdd-journal-io-model": "RB HDD PASS",
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


def inspect_stage2(data):
    if (not 33 <= len(data) <= STAGE2_MAX or data[:6] != b"\xeb\x1eRBS2"
            or struct.unpack_from("<H", data, 6)[0] != 32
            or struct.unpack_from("<I", data, 8)[0] != len(data)
            or struct.unpack_from("<3H", data, 16) != (0x1000, 32, 2)):
        raise ValueError("Invalid stage2 header or memory budget")
    bss_begin, bss_end, stack_low, stack_top, flags = struct.unpack_from("<5H", data, 22)
    if (not len(data) <= bss_begin < bss_end <= 0xE000
            or (stack_low, stack_top, flags) != (0xE000, 0xFFFE, 0)):
        raise ValueError("Invalid stage2 BSS/stack bounds or flags")
    return {"file_bytes": len(data), "bss_begin": bss_begin, "bss_end": bss_end,
            "stack_low": stack_low, "stack_top": stack_top}


def seal_stage2(data):
    inspect_stage2(data)
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


def fixture(parts, case, language="en"):
    """Describe a sparse new image. No external destination or input disk."""
    size, admin, extents = layout(case in ("hdd-reference", "retroboot-reference"))
    start, count, fat = admin["start_lba"], admin["sectors"], admin["fat"]
    spc, spf = fat["sectors_per_cluster"], fat["sectors_per_fat"]
    cluster_bytes = spc * SECTOR
    root_lba = start + 1 + 2 * spf
    data_lba = root_lba + 32
    bootstrap, stage2 = parts["bootstrap"], bytearray(parts["stage2"])
    if len(bootstrap) > 16 * SECTOR or len(bootstrap) % SECTOR:
        raise ValueError("Invalid contiguous bootstrap length")
    boot_clusters = list(range(2, 2 + (len(bootstrap) + cluster_bytes - 1) // cluster_bytes))
    needed = (len(stage2) + cluster_bytes - 1) // cluster_bytes
    stage_clusters = [20 + index if case == "hdd-contiguous" else
                      20 + index * 10 if index % 2 == 0 else 200 + index * 100
                      for index in range(needed)]
    if case == "hdd-boundaries":
        stage_clusters[:2] = [25, 151]  # LBAs 503/1007: track/cylinder edges, 16/63
    if not 2 * cluster_bytes < len(stage2) <= STAGE2_MAX or len(boot_clusters) > 4:
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
        struct.pack_into("<H", table, stage_clusters[-1] * 2, 31000)
    table2 = bytearray(table)
    if case == "hdd-fat-copies":
        struct.pack_into("<H", table2, stage_clusters[0] * 2, 0xFFFF)
    root = bytearray(32 * SECTOR)
    root[:32] = directory_entry(b"RBBOOT  SYS", 2, len(bootstrap))
    # Exercise deleted entries, directory/LFN skipping and a second root sector.
    for index in range(1, 20):
        root[index * 32] = 0xE5
    if case.startswith("hdd-"):
        # Explicit loader campaigns retain directory/LFN skip challenges.
        # Released diagnostic media use the canonical eight-file root.
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
    if case == "hdd-old-header":
        stage2[2:6] = b"RBS1"
        struct.pack_into("<H", stage2, 20, 1)
    header_faults = {"hdd-bss-overlap": (22, len(stage2) - 1),
                     "hdd-bss-overflow": (24, 0xE002),
                     "hdd-bss-empty": (24, struct.unpack_from("<H", stage2, 22)[0]),
                     "hdd-stack-contract": (28, 0xFFFC), "hdd-header-flags": (30, 1)}
    if case in header_faults:
        struct.pack_into("<H", stage2, *header_faults[case])
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
    state = encode_state(disk_id=struct.unpack_from("<I", extents[0], 440)[0], layout=layout_crc(extents),
                         admin_start=start, admin_sectors=count)
    return size, allocate_journal(install_records(extents, admin, language=language, state_records=(state, state)), admin)


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


def build_stage2(destination, nasm, wcc, wlink):
    """Link the production C entry and explicit, CRC-valid startup fault builds."""
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"WCC", "WLINK", "WATCOM", "INCLUDE", "LIB", "LIBPATH"}}

    def run(*args):
        result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        if result.returncode or "Warning!" in result.stdout or "Warning!" in result.stderr:
            raise ValueError(f"Build failed: {args[0]}\n{result.stdout}{result.stderr}")

    (destination / "config_fixture.h").write_text(model_header(), encoding="ascii")
    (destination / "journal_io_fixture.h").write_text(io_model_header(), encoding="ascii")
    (destination / "journal_fixture.h").write_text(journal_model_header(), encoding="ascii")
    (destination / "handoff_fixture.inc").write_text(assembler_header(), encoding="ascii")
    test_vbr = destination / "handoff-vbr.bin"
    run(nasm, "-Werror", "-f", "bin", "-I", "./", "-I", str(destination) + "/",
        "tests/handoff/vbr.asm", "-o", test_vbr)
    (destination / "handoff_fixture.h").write_text(c_header(test_vbr.read_bytes()), encoding="ascii")
    (destination / "state_fixture.h").write_text(state_model_header(test_vbr.read_bytes()), encoding="ascii")
    run(wcc, "-q", "-3", "-ms", "-ecc", "-s", "-zl", "-zld", "-w4", "-wx",
        "-dRB_HANDOFF_TEST=1", "-i=include", "-i=" + str(destination),
        "-fo=" + str(destination / "menu-handoff.obj"), "core/menu.c")
    for fault in (0, *FAULTS.values()):
        run(nasm, "-Werror", "-f", "obj", "-I", "./", f"-DRB_HANDOFF_FAULT={fault}",
            "bios/handoff.asm", "-o", destination / f"handoff-{fault}.obj")

    for name, source in (("stage2-c", "core/stage2.c"), ("menu", "core/menu.c"),
                         ("menu-model", "core/menu_model.c"), ("menu-selftest", "tests/menu/model.c"),
                         ("partitions", "core/partitions.c"), ("scan-selftest", "tests/partitions/model.c"),
                         ("volume", "core/volume.c"), ("volume-selftest", "tests/partitions/volume.c"),
                         ("handoff", "core/handoff.c"), ("handoff-test", "core/handoff_test.c"),
                         ("handoff-selftest", "tests/handoff/model.c"),
                         ("config", "core/config.c"), ("config-io", "core/config_io.c"),
                         ("record-io", "core/record_io.c"), ("state", "core/state.c"), ("state-check", "core/state_check.c"),
                         ("config-selftest", "tests/config/model.c"), ("state-selftest", "tests/state/model.c"),
                         ("visibility", "core/visibility.c"), ("visibility-selftest", "tests/visibility/model.c"),
                         ("profile-test", "core/profile_test.c"), ("profile-test-run", "core/profile_test_run.c"),
                         ("profile-selftest", "tests/profile/model.c"),
                         ("admin-audit", "core/admin_audit.c"), ("audit-selftest", "tests/audit/model.c"),
                         ("journal", "core/journal.c"), ("journal-io", "core/journal_io.c"),
                         ("journal-selftest", "tests/journal/model.c"), ("journal-io-selftest", "tests/journal/io.c")):
        run(wcc, "-q", "-3", "-ms", "-ecc", "-s", "-zl", "-zld", "-w4", "-wx",
            "-i=include", "-i=" + str(destination),
            "-fo=" + str(destination / (name + ".obj")), source)
    for name in ("ui", "disk"):
        run(nasm, "-Werror", "-f", "obj", "-I", "./", f"bios/{name}.asm", "-o", destination / (name + ".obj"))
    for name in ("abi", "arith", "end"):
        run(nasm, "-Werror", "-f", "obj", "-I", "./", "-DRB_HDD_FIXTURE=1", f"runtime/{name}.asm",
            "-o", destination / (name + ".obj"))
    payloads, memory, artifacts = {}, {}, {}
    variants = {"normal": [], "test": ["-DRB_TEST=1"],
                "bss-fault": ["-DRB_TEST=1", "-DRB_SKIP_BSS_CLEAR=1"],
                "stack-fault": ["-DRB_TEST=1", "-DRB_BAD_STACK_GUARD=1"],
                "context-fault": ["-DRB_TEST=1", "-DRB_BAD_BOOT_CONTEXT=1"],
                "menu-model": ["-DRB_TEST=1", "-DRB_MENU_MODEL_TEST=1"],
                "scan-model": ["-DRB_TEST=1", "-DRB_SCAN_MODEL_TEST=1"],
                "volume-model": ["-DRB_TEST=1", "-DRB_VOLUME_MODEL_TEST=1"],
                "handoff-model": ["-DRB_TEST=1", "-DRB_HANDOFF_MODEL_TEST=1"],
                "config-model": ["-DRB_TEST=1", "-DRB_CONFIG_MODEL_TEST=1"],
                "state-model": ["-DRB_TEST=1", "-DRB_STATE_MODEL_TEST=1"],
                "visibility-model": ["-DRB_TEST=1", "-DRB_VISIBILITY_MODEL_TEST=1"],
                "profile-model": ["-DRB_TEST=1", "-DRB_PROFILE_MODEL_TEST=1"],
                "audit-model": ["-DRB_TEST=1", "-DRB_AUDIT_MODEL_TEST=1"],
                "journal-io-model": ["-DRB_TEST=1", "-DRB_JOURNAL_IO_TEST=1"],
                "journal-model": ["-DRB_TEST=1", "-DRB_JOURNAL_MODEL_TEST=1"],
                "handoff": [], **{"handoff-" + name: [] for name in FAULTS}}
    for variant, defines in variants.items():
        stem = "stage2" + ("" if variant == "normal" else "-" + variant)
        obj, binary, mapfile = (destination / (stem + suffix) for suffix in (".obj", ".bin", ".map"))
        run(nasm, "-Werror", "-f", "obj", "-I", "./", *defines, "core/start.asm", "-o", obj)
        handoff = variant == "handoff" or variant in {"handoff-" + name for name in FAULTS}
        linked_objects = [obj, destination / "stage2-c.obj",
                          destination / "menu-model.obj", destination / "ui.obj", destination / "abi.obj",
                          destination / "partitions.obj", destination / "disk.obj", destination / "volume.obj", destination / "arith.obj",
                          destination / "config.obj", destination / "config-io.obj", destination / "record-io.obj",
                          destination / "state.obj", destination / "state-check.obj", destination / "visibility.obj"]
        # Test-only startup/model variants never enter the UI. Exclude its
        # unused code and journal scratch while preserving the same core objects.
        if "-DRB_TEST=1" not in defines:
            linked_objects.extend([destination / ("menu-handoff.obj" if handoff else "menu.obj"),
                                   destination / "journal.obj", destination / "journal-io.obj"])
        if variant == "menu-model":
            linked_objects.append(destination / "menu-selftest.obj")
        if variant == "scan-model":
            linked_objects.append(destination / "scan-selftest.obj")
        if variant == "volume-model":
            linked_objects.append(destination / "volume-selftest.obj")
        if variant == "config-model":
            linked_objects.append(destination / "config-selftest.obj")
        if variant == "state-model":
            linked_objects.append(destination / "state-selftest.obj")
        if variant == "visibility-model":
            linked_objects.append(destination / "visibility-selftest.obj")
        linked_objects.append(destination / "admin-audit.obj")
        if variant == "audit-model":
            linked_objects.append(destination / "audit-selftest.obj")
        if variant == "journal-model":
            linked_objects.extend([destination / "journal.obj", destination / "journal-selftest.obj"])
        if variant == "journal-io-model":
            linked_objects.extend([destination / "journal.obj", destination / "journal-io.obj", destination / "journal-io-selftest.obj"])
        if handoff or variant == "profile-model":
            linked_objects.append(destination / "profile-test.obj")
        if variant == "profile-model":
            linked_objects.append(destination / "profile-selftest.obj")
        if handoff or variant == "handoff-model":
            linked_objects.append(destination / "handoff.obj")
        if variant == "handoff-model":
            linked_objects.append(destination / "handoff-selftest.obj")
        if handoff:
            linked_objects.extend([destination / "handoff-test.obj", destination / "profile-test-run.obj",
                destination / f"handoff-{FAULTS.get(variant.removeprefix('handoff-'), 0)}.obj"])
        linked_objects.append(destination / "end.obj")
        objects = ",".join(str(path) for path in linked_objects)
        run(wlink, "@core/stage2.wlink", "name", binary, "option", "map=" + str(mapfile), "file", objects)
        linked = binary.read_bytes()
        header = inspect_stage2(linked)
        segments = inspect_map(mapfile, header)
        symbols = {name: int(address, 16) for address, name in re.findall(
            r"^([0-9a-fA-F]{8})[+*]?\s+(\w+)\s*$", mapfile.read_text(encoding="utf-8"), re.MULTILINE)}
        required = ("rb_entry", "rb_file_end", "rb_bss_begin", "rb_bss_end",
                    "_rb_initialized_word", "_rb_initialized_long", "_rb_boot",
                    "_rb_bss_word", "_rb_bss_long", "_rb_bss_array")
        if not all(name in symbols for name in required):
            raise ValueError("Missing Stage 2 map symbols")
        symbols = {name: symbols[name] for name in required}
        if (symbols["rb_entry"] != 32 or symbols["rb_file_end"] != len(linked)
                or symbols["rb_bss_begin"] != header["bss_begin"]
                or symbols["rb_bss_end"] != header["bss_end"]
                or any(s["start"] + s["size"] > len(linked)
                       for s in segments.values() if s["class"] in {"CODE", "DATA"})):
            raise ValueError("Stage 2 header, file and map disagree")
        for name, size in (("_rb_initialized_word", 2), ("_rb_initialized_long", 4)):
            if not 32 <= symbols[name] <= len(linked) - size:
                raise ValueError("Initialized C data outside loaded file")
        for name, size in (("_rb_boot", 12), ("_rb_bss_word", 2),
                           ("_rb_bss_long", 4), ("_rb_bss_array", 17)):
            if not header["bss_begin"] <= symbols[name] <= header["bss_end"] - size:
                raise ValueError("C variable outside cleared BSS")
        # The end object emits padding so that BSS follows the entire file.
        if not 4096 < len(linked) <= STAGE2_MAX:
            raise ValueError("C payload exceeds the Stage 2 memory budget")
        payloads[variant] = seal_stage2(linked)
        binary.write_bytes(payloads[variant])
        memory[variant] = {"header": header, "fixture_padding_bytes": 4096,
                           "segments": segments, "symbols": symbols}
        artifacts[binary.name] = {"bytes": len(linked), "sha256": sha256(binary)}
    bad_data = bytearray(payloads["test"])
    struct.pack_into("<H", bad_data, memory["test"]["symbols"]["_rb_initialized_word"], 0xDEAD)
    payloads["data-fault"] = seal_stage2(bad_data)
    binary = destination / "stage2-data-fault.bin"
    binary.write_bytes(payloads["data-fault"])
    artifacts[binary.name] = {"bytes": len(bad_data), "sha256": sha256(binary)}
    artifacts[test_vbr.name] = {"bytes": 512, "sha256": sha256(test_vbr)}
    return payloads, memory, artifacts


def build(output, language="en"):
    if output not in ("hdd", "hdd-repeat"):
        raise ValueError("Output must be hdd or hdd-repeat")
    header = render_header(load_catalog(language), language)
    destination = ROOT / "build" / output_name(output, language)
    prepare_output(destination)
    (destination / "ui_text.h").write_text(header, encoding="ascii", newline="\n")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    nasm = TOOLCHAIN / ("nasm-" + lock["nasm"]["version"]) / "nasm"
    wcc, wlink = (TOOLCHAIN / "watcom" / name for name in ("wcc", "wlink"))
    for name, path in (("wcc", wcc), ("wlink", wlink)):
        verify(path, lock["open_watcom"]["executables"][name])
    version = subprocess.check_output([str(nasm), "-v"], text=True).strip()
    if version.split()[:3] != ["NASM", "version", lock["nasm"]["version"]]:
        raise ValueError(f"Unexpected assembler: {version}")
    stage2, memory, artifacts = build_stage2(destination, nasm, wcc, wlink)
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
        for name in ("mbr", "vbr", "bootstrap"):
            path = destination / (name + ("-test" if test else "") + ".bin")
            subprocess.run([str(nasm), "-Werror", "-f", "bin", "-I", "./",
                            *(["-DRB_TEST=1"] if test else []), f"boot/{name}.asm", "-o", str(path)],
                           cwd=ROOT, check=True)
            data = path.read_bytes()
            if name == "bootstrap":
                data = bytearray(data)
                struct.pack_into("<H", data, 6, len(data))
                data = seal_sum(data, 8)
            path.write_bytes(data)
            parts[name] = data
            artifacts[path.name] = {"bytes": len(data), "sha256": sha256(path)}
        for case in (CASES if test else ("retroboot-hdd", "retroboot-reference", *SCAN_CASES, *VOLUME_CASES, *HANDOFF_CASES, *CONFIG_CASES, *STATE_CASES, *VISIBILITY_CASES, *PROFILE_CASES, *AUDIT_CASES, *JOURNAL_CASES)):
            variant = case.removeprefix("hdd-c-") if case.startswith("hdd-c-") else "test" if test else "normal"
            if case == "hdd-menu-model":
                variant = "menu-model"
            if case == "hdd-scan-model":
                variant = "scan-model"
            if case == "hdd-volume-model":
                variant = "volume-model"
            if case == "hdd-handoff-model":
                variant = "handoff-model"
            if case == "hdd-config-model":
                variant = "config-model"
            if case == "hdd-state-model":
                variant = "state-model"
            if case == "hdd-audit-model":
                variant = "audit-model"
            if case == "hdd-journal-io-model":
                variant = "journal-io-model"
            if case == "hdd-journal-model":
                variant = "journal-model"
            if case == "hdd-profile-model":
                variant = "profile-model"
            if case == "hdd-visibility-model":
                variant = "visibility-model"
            if case in PROFILE_CASES:
                variant = "handoff"
            if case in HANDOFF_CASES:
                fault = HANDOFF_CASES[case].get("register_fault")
                variant = "handoff" + ("-" + fault if fault else "")
            parts["stage2"] = stage2[variant]
            path = destination / (case + ".img")
            size, extents = fixture(parts, case, language)
            if case in JOURNAL_CASES:
                size, extents = mutate_journal_fixture(size, extents, case)
            if case in AUDIT_CASES:
                size, extents = mutate_audit_fixture(size, extents, case)
            if case in SCAN_CASES:
                extents = mutate_scan_fixture(size, extents, case)
            if case in VOLUME_CASES:
                size, extents = mutate_volume_fixture(size, extents, case)
            if case in HANDOFF_CASES:
                size, extents = mutate_handoff_fixture(size, extents, case, (destination / "handoff-vbr.bin").read_bytes())
            if case in CONFIG_CASES:
                size, extents = mutate_config_fixture(size, extents, case, (destination / "handoff-vbr.bin").read_bytes(), language)
            if case in STATE_CASES:
                size, extents = mutate_state_fixture(size, extents, case, (destination / "handoff-vbr.bin").read_bytes(), language)
            if case in PROFILE_CASES:
                size, extents = mutate_profile_fixture(size, extents, case, (destination / "handoff-vbr.bin").read_bytes(), language)
            if case in VISIBILITY_CASES:
                size, extents = mutate_visibility_fixture(size, extents, case, (destination / "handoff-vbr.bin").read_bytes(), language)
            if case == "retroboot-handoff":
                record = encode_config(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126,
                    admin_sectors=128457, language=language, media_id=FIXTURE_MEDIA_ID, profiles=[dict(id=1, name="Test VBR",
                    slot=1, type=6, start=131072, sectors=5073, installed=2, approved=1, install_id=TEST_INSTALL_ID)])
                for cluster in CLUSTERS: extents[(411 + (cluster - 2) * 4) * 512] = record
                state = encode_state(disk_id=0x52425431, layout=layout_crc(extents), admin_start=126,
                    admin_sectors=128457, installations=[dict(install_id=TEST_INSTALL_ID, slot=1, type=6,
                    start=131072, sectors=5073, phase=6, vbr_crc=zlib.crc32((destination / "handoff-vbr.bin").read_bytes()))])
                for cluster in STATE_CLUSTERS: extents[(411 + (cluster - 2) * 4) * 512] = state
            if case in ("retroboot-hdd", "retroboot-reference", "retroboot-handoff"):
                extents = journal_baseline(extents, size, struct.unpack_from("<I", extents[0], 436)[0])
            write_fixture(path, size, extents)
            artifacts[path.name] = {"bytes": size, "sha256": sha256(path)}
    manifest = {"format_version": 2, "purpose": "phase-5-read-only-partition-scan-fixtures",
                "toolchain": lock, "host_executable_sha256": {
                    "nasm": sha256(nasm), "wcc": sha256(wcc), "wlink": sha256(wlink)},
                "memory": memory, "artifacts": artifacts, "scan_cases": SCAN_CASES,
                "ui": catalog_metadata(language), "volume_cases": VOLUME_CASES, "handoff_cases": HANDOFF_CASES, "config_cases": CONFIG_CASES, "state_cases": STATE_CASES, "visibility_cases": VISIBILITY_CASES, "profile_cases": PROFILE_CASES, "audit_cases": AUDIT_CASES, "journal_cases": JOURNAL_CASES}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built {destination.name} ({language}, CP437): MBR 440, VBR 512, bootstrap {len(parts['bootstrap'])}, normal C stage2 {len(stage2['normal'])} bytes", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--language", choices=LANGUAGES, default="en")
    args = parser.parse_args()
    first = build("hdd", args.language)
    if args.repeat and first != build("hdd-repeat", args.language):
        raise ValueError("Repeated HDD builds differ")
    if args.repeat:
        print("Reproducibility: all HDD binaries, images and manifests are identical")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"HDD build: {error}", file=sys.stderr)
        sys.exit(1)
