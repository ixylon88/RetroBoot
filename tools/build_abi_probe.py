"""Build a BIOS ABI test floppy using regular output files below build/."""

import argparse
import json
import os
import re
import stat
import struct
import subprocess
import sys
from pathlib import Path

try:
    from .setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify
except ImportError:
    from setup_toolchain import LOCK, ROOT, TOOLCHAIN, sha256, verify

IMAGE_BYTES = 1_474_560
MAX_PAYLOAD = 17 * 512
HEADER_NAMES = ("header_bytes", "entry", "bss_begin", "bss_end", "load_segment",
                "stack_low", "stack_top", "file_end", "version", "data_word", "bss_word")


def prepare_output(path):
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("Build output directories must not be symlinks")
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if not stat.S_ISREG(child.lstat().st_mode):
            raise ValueError(f"Non-regular build output: {child}")


def inspect_payload(data):
    if len(data) < 32 or data[:10] != b"\xeb\x1eRBABI01\0":
        raise ValueError("Invalid ABI probe header or entry jump")
    h = dict(zip(HEADER_NAMES, struct.unpack_from("<11H", data, 10)))
    if (h["header_bytes"], h["entry"], h["version"]) != (32, 32, 1):
        raise ValueError("Unsupported ABI probe format")
    if (h["load_segment"], h["stack_low"], h["stack_top"]) != (0x1000, 0xE000, 0xFFFE):
        raise ValueError("Memory contract differs from the phase-2 probe")
    if not (32 < len(data) == h["file_end"] <= MAX_PAYLOAD
            and h["file_end"] <= h["bss_begin"] < h["bss_end"] <= h["stack_low"]):
        raise ValueError("Invalid file/BSS/stack bounds or payload exceeds one track")
    if not (32 <= h["data_word"] <= len(data) - 2
            and h["bss_begin"] <= h["bss_word"] <= h["bss_end"] - 2):
        raise ValueError("Probe variables lie outside their declared regions")
    return h


def make_image(boot, payload):
    inspect_payload(payload)
    if len(boot) != 512 or boot[510:] != b"\x55\xaa":
        raise ValueError("Invalid 512-byte boot sector")
    # A5 padding preserves the poisoned BSS even in the last loaded sector.
    padded = payload + b"\xa5" * (-len(payload) % 512)
    return boot + padded + bytes(IMAGE_BYTES - 512 - len(padded))


def inspect_map(path, header):
    segments = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"(\S+)\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})", line)
        if match:
            name, kind, group, address, size = match.groups()
            if group != "DGROUP":
                raise ValueError(f"Unexpected segment group: {group}")
            segments[name] = (kind, int(address, 16), int(size, 16))
    expected = {"_TEXT": "CODE", "CONST": "DATA", "CONST2": "DATA",
                "_DATA": "DATA", "_BSS": "BSS", "STACK": "STACK"}
    if {name: values[0] for name, values in segments.items()} != expected:
        raise ValueError(f"Unexpected linked segments: {sorted(segments)}")
    if segments["_TEXT"][1] != 0 or segments["STACK"] != ("STACK", 0xE000, 0x1FFE):
        raise ValueError("Linker did not respect the code/stack locations")
    spans = sorted((start, start + size, name) for name, (_, start, size) in segments.items() if size)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError("Linked segments overlap")
    if segments["_BSS"][1] != header["bss_begin"]:
        raise ValueError("Header and linker disagree on BSS")
    if segments["_BSS"][1] + segments["_BSS"][2] > header["bss_end"]:
        raise ValueError("Startup would not clear all linked BSS")
    return {name: {"class": kind, "start": start, "size": size}
            for name, (kind, start, size) in segments.items()}


def build(output):
    # Deliberately no user-supplied disk/image path. Output stays under build/.
    if output not in ("abi", "abi-repeat"):
        raise ValueError("Output must be abi or abi-repeat")
    destination = ROOT / "build" / output
    prepare_output(destination)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    nasm = TOOLCHAIN / ("nasm-" + lock["nasm"]["version"]) / "nasm"
    wcc, wlink = (TOOLCHAIN / "watcom" / name for name in ("wcc", "wlink"))
    for name, path in (("wcc", wcc), ("wlink", wlink)):
        verify(path, lock["open_watcom"]["executables"][name])
    version = subprocess.check_output([str(nasm), "-v"], text=True).strip()
    if version.split()[:3] != ["NASM", "version", lock["nasm"]["version"]]:
        raise ValueError(f"Unexpected assembler: {version}")
    # Do not inherit compiler/linker option variables or installed library paths.
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"WCC", "WLINK", "WATCOM", "INCLUDE", "LIB", "LIBPATH"}}

    def run(*args):
        result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        if result.returncode or "Warning!" in result.stdout or "Warning!" in result.stderr:
            raise ValueError(f"Build failed: {args[0]}\n{result.stdout}{result.stderr}")

    common = ["-q", "-3", "-ms", "-ecc", "-s", "-zl", "-zld", "-w4", "-wx", "-i=include"]
    run(wcc, *common, "-fo=" + str(destination / "probe.obj"), "tests/abi/probe.c")
    for name in ("helpers", "end"):
        source = "runtime/abi.asm" if name == "helpers" else "runtime/end.asm"
        run(nasm, "-Werror", "-f", "obj", "-I", "./", source, "-o", destination / (name + ".obj"))
    artifacts, memory = {}, None
    for variant, defines in (("abi-probe", []), ("abi-probe-bss-fault", ["-DRB_SKIP_BSS_CLEAR=1"])):
        obj, binary, mapfile = (destination / (variant + suffix) for suffix in (".obj", ".bin", ".map"))
        run(nasm, "-Werror", "-f", "obj", "-I", "./", *defines, "tests/abi/start.asm", "-o", obj)
        objects = ",".join(str(path) for path in (obj, destination / "probe.obj", destination / "helpers.obj", destination / "end.obj"))
        run(wlink, "@tests/abi/probe.wlink", "name", binary, "option", "map=" + str(mapfile), "file", objects)
        payload = binary.read_bytes()
        header = inspect_payload(payload)
        layout = inspect_map(mapfile, header)
        if memory is None:
            memory = {"header": header, "segments": layout}
        boot = destination / (variant + "-boot.bin")
        run(nasm, "-Werror", "-f", "bin", "-I", "./", "-DRB_PROBE_SECTORS=" + str((len(payload) + 511) // 512),
            "tests/abi/boot.asm", "-o", boot)
        image = destination / (variant + ".img")
        image.write_bytes(make_image(boot.read_bytes(), payload))
        for path in (binary, boot, image):
            artifacts[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    run(wcc, *common, "-fo=" + str(destination / "missing-runtime.obj"), "tests/abi/missing_runtime.c")
    rejected = subprocess.run([str(wlink), "@tests/abi/probe.wlink", "name",
                               str(destination / "must-not-link.bin"), "file",
                               objects + "," + str(destination / "missing-runtime.obj")],
                              cwd=ROOT, env=env, capture_output=True, text=True)
    diagnostics = rejected.stdout + rejected.stderr
    (destination / "negative-link.log").write_text(diagnostics, encoding="utf-8")
    (destination / "must-not-link.bin").unlink(missing_ok=True)
    if rejected.returncode == 0 or "rb_missing_runtime" not in diagnostics:
        raise ValueError("Unresolved runtime dependency was not rejected as expected")
    bad_data = bytearray((destination / "abi-probe.bin").read_bytes())
    struct.pack_into("<H", bad_data, memory["header"]["data_word"], 0xDEAD)
    bad_image = destination / "abi-probe-data-fault.img"
    bad_image.write_bytes(make_image((destination / "abi-probe-boot.bin").read_bytes(), bad_data))
    artifacts[bad_image.name] = {"bytes": bad_image.stat().st_size, "sha256": sha256(bad_image)}
    manifest = {"format_version": 1, "purpose": "phase-2-abi-probe-only", "toolchain": lock,
                "host_executable_sha256": {"nasm": sha256(nasm), "wcc": sha256(wcc), "wlink": sha256(wlink)},
                "undefined_runtime_rejected": True,
                "memory": memory, "artifacts": artifacts}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Built {output}: {memory['header']['file_end']} payload bytes; BSS and stack bounds verified")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", action="store_true", help="build twice and compare all binary artifacts")
    args = parser.parse_args()
    first = build("abi")
    if args.repeat:
        second = build("abi-repeat")
        if first != second:
            raise ValueError("Repeated builds differ")
        print("Reproducibility: all binary artifacts and manifests are identical")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"ABI build: {error}", file=sys.stderr)
        sys.exit(1)
