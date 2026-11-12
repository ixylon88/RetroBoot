"""Boot HDD fixtures in disposable QEMU overlays; verify diagnostics and I/O."""

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .ui_text import LANGUAGES, checked_catalog, output_name
    from .build_hdd import CASES, ROOT, prepare_output, sha256
except ImportError:
    from ui_text import LANGUAGES, checked_catalog, output_name
    from build_hdd import CASES, ROOT, prepare_output, sha256


def check_result(name, code, output, marker, stopped_after_marker=False):
    positive = marker == "RB HDD PASS"
    expected = 0 if stopped_after_marker else 33 if positive else 35
    if code != expected or marker not in output:
        raise ValueError(f"{name}: expected {marker!r} / exit {expected}, got {code}:\n{output}")
    if positive and ("ERROR" in output or "MISSING" in output):
        raise ValueError(f"{name}: contradictory success/error markers")
    if not positive and ("RB HDD PASS" in output or "Stage 2 ready" in output):
        raise ValueError(f"{name}: invalid handoff after an error")


def check_c_status(output, mode):
    if ("C entry, data, BSS, pointers and integer calls OK" not in output
            or f"BIOS disk path: {mode}" not in output
            or f"BIOS disk path: {'CHS' if mode == 'EDD' else 'EDD'}" in output):
        raise ValueError("Missing C startup evidence or wrong BIOS mode handed to C")


def check_runtime_memory(data, payload, memory, mode):
    """Inspect the normal image's actual RAM after C returns successfully."""
    if len(data) != 0x10000 or data[:len(payload)] != payload:
        raise ValueError("Loaded Stage 2 differs byte-for-byte from the built file")
    header, symbols = memory["header"], memory["symbols"]
    start, end = header["bss_begin"], header["bss_end"]
    boot = data[symbols["_rb_boot"]:symbols["_rb_boot"] + 12]
    drive, selected, low, high = struct.unpack("<HHII", boot)
    if (drive, selected) != (0x80, 1 if mode == "EDD" else 0) or not (low or high):
        raise ValueError("Incorrect C boot context in guest RAM")
    expected = bytearray(end - start)
    offset = symbols["_rb_boot"] - start
    expected[offset:offset + 12] = boot
    struct.pack_into("<H", expected, symbols["_rb_bss_word"] - start, 0xBEAD)
    if data[start:end] != expected:
        raise ValueError("C BSS contents differ from initialized runtime state")
    if struct.unpack_from("<H", data, header["stack_low"])[0] != 0xA55A:
        raise ValueError("C stack guard was overwritten")
    return hashlib.sha256(data[:len(payload)]).hexdigest()


def check_trace(trace, fault_sector=None, expected_reads=None):
    first_read = re.search(r"ide_sector_read sector=0 nsectors=1\b", trace)
    if not first_read:
        raise ValueError("Missing IDE read trace; cannot verify the test")
    # QEMU creates the snapshot's qcow2 header before reading the MBR. From
    # that first boot read onward, any block write (PIO or DMA) is a failure.
    if "ide_sector_write" in trace or "blk_co_pwritev" in trace[first_read.start():]:
        raise ValueError("Unexpected guest disk write")
    if fault_sector is not None:
        reads = len(re.findall(rf"ide_sector_read sector={fault_sector} nsectors=1\b", trace))
        if reads != expected_reads:
            raise ValueError(f"Expected {expected_reads} read attempts at LBA {fault_sector}, got {reads}")


def check_bios_route(log, mode):
    calls = re.findall(r"^@([0-9A-F]{2})$", log, re.MULTILINE)
    if calls.count("41") != 1:
        raise ValueError("Missing or repeated EDD capability probe")
    calls = calls[calls.index("41") + 1:]
    expected_init, forbidden = ("48", {"02", "08"}) if mode == "EDD" else ("08", {"42", "48"})
    if not calls or calls[0] != expected_init or forbidden.intersection(calls):
        raise ValueError(f"Unexpected {mode} BIOS route: {calls}")
    return calls


def read_lbas(trace):
    reads = [(int(lba), int(count)) for lba, count in
             re.findall(r"ide_sector_read sector=(\d+) nsectors=(\d+)", trace)]
    if not reads or any(count != 1 for _, count in reads):
        raise ValueError("Expected single-sector BIOS reads")
    return [lba for lba, _ in reads]


def save_guest_memory(process, output, size):
    # QMP over pipes also works on hosts that disallow local sockets. Commands
    # are processed in order; pmemsave completes before the orderly quit.
    requests = [{"execute": "qmp_capabilities", "id": "capabilities"},
                {"execute": "stop", "id": "stop"},
                {"execute": "pmemsave", "id": "memory", "arguments": {
                    "val": 0x10000, "size": size, "filename": str(output)}},
                {"execute": "quit", "id": "quit"}]
    text, error = process.communicate(input="".join(json.dumps(r) + "\n" for r in requests), timeout=5)
    responses = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not responses or "QMP" not in responses[0] or any("error" in r for r in responses):
        raise ValueError(f"QMP failed: {text}\n{error}")
    completed = {r.get("id") for r in responses if "return" in r}
    if not {"capabilities", "stop", "memory"} <= completed:
        raise ValueError(f"Incomplete QMP memory capture: {text}")
    return process.returncode, error


def run_until_marker(command, log, marker, output, size):
    """Stop the normal image externally; it never uses QEMU's exit port."""
    with subprocess.Popen(command + ["-qmp", "stdio"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                message = log.read_text(encoding="utf-8") if log.exists() else ""
                if marker in message:
                    return save_guest_memory(process, output, size)
                if process.poll() is not None:
                    _, error = process.communicate()
                    return process.returncode, error
                time.sleep(0.02)
            raise ValueError("Timed out waiting for the uninstrumented HDD image")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


@dataclass(frozen=True)
class BootCase:
    name: str
    source: str
    marker: str
    mode: str = "EDD"
    rom: int | None = 0
    once: bool | None = None
    geometry: str = ""
    pair: str = ""


def scenarios():
    cases = []
    sources = [(name, name, marker, None) for name, marker in CASES.items()]
    sources += [("retroboot-hdd", "retroboot-hdd", "RB HDD PASS", None),
                ("hdd-io-retry", "hdd-fragmented", "RB HDD PASS", True),
                ("hdd-io-failure", "hdd-fragmented", "RB READ ERROR", False)]
    for mode, rom in (("EDD", 0), ("CHS", 1)):
        for name, source, marker, once in sources:
            geometry = ",cyls=130,heads=16,secs=63,bios-chs-trans=none" if name == "hdd-boundaries" else ""
            cases.append(BootCase(name + "-" + mode.lower(), source, marker, mode, rom, once, geometry, name))
    for name, rom, mode, marker in (
            ("bad-edd-signature", 2, "CHS", "RB HDD PASS"),
            ("missing-edd-read-bit", 3, "CHS", "RB HDD PASS"),
            ("chs-geometry-error", 4, "CHS", "RB MBR ERROR"),
            ("chs-zero-sectors", 5, "CHS", "RB MBR ERROR"),
            ("edd-parameter-error", 6, "EDD", "RB MBR ERROR"),
            ("edd-sector-size", 7, "EDD", "RB MBR ERROR"),
            ("edd-short-parameters", 8, "EDD", "RB MBR ERROR")):
        cases.append(BootCase(name, "hdd-fragmented", marker, mode, rom))
    cases += [BootCase("chs-unreachable-vbr", "hdd-reference", "RB MBR ERROR", "CHS", 1,
                       geometry=",cyls=1024,heads=16,secs=63,bios-chs-trans=none"),
              BootCase("chs-unreachable-volume", "hdd-fragmented", "RB BPB ERROR", "CHS", 1,
                       geometry=",cyls=128,heads=16,secs=63,bios-chs-trans=none"),
              BootCase("retroboot-hdd-bare", "retroboot-hdd", "RB HDD PASS", rom=None)]
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--bios", type=Path)
    parser.add_argument("--language", choices=LANGUAGES, default="en")
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError("qemu-system-i386 not found; install qemu-system-x86")
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent / "share/seabios/bios-256k.bin").resolve()
    if not bios.is_file() or not bios.with_name("vgabios-stdvga.bin").is_file():
        raise ValueError("SeaBIOS and its VGA ROM must be present; use --bios")
    directory = ROOT / "build" / output_name("hdd", args.language)
    prepare_output(directory)
    result_file = directory / "boot-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    checked_catalog(manifest, args.language)
    events = directory / "ide-events.txt"
    events.write_text("ide_sector_read\nide_sector_write\nblk_co_pwritev\n", encoding="ascii")
    version = subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0]
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "c", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    for name, info in manifest["artifacts"].items():
        if name.endswith((".bin", ".rom")) and sha256(directory / name) != info["sha256"]:
            raise ValueError(f"Unexpected binary/ROM content: {name}")
    expected_memory = (directory / "stage2.bin").read_bytes()
    cases, pairs = [], {}
    for case in scenarios():
        name, marker, once = case.name, case.marker, case.once
        log, trace = (directory / (name + suffix) for suffix in (".log", ".trace"))
        image = directory / (case.source + ".img")
        before = sha256(image)
        if before != manifest["artifacts"][image.name]["sha256"]:
            raise ValueError(f"Unexpected image content: {image.name}; rebuild first")
        log.unlink(missing_ok=True)
        trace.unlink(missing_ok=True)
        drive = str(image)
        if once is not None:
            # First stage2 data sector in the compact fixture. The trace must
            # prove two attempts for a transient fault, three for a lasting one.
            config = directory / (name + ".conf")
            config.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                              'sector = "483"\nonce = "' + ("on" if once else "off") + '"\n', encoding="ascii")
            drive = f"blkdebug:{config}:{image}"
        # IDE requires a writable frontend. QEMU snapshot mode opens the source
        # read-only and redirects possible writes into a temporary overlay.
        invocation = command + ["-drive", f"file={drive.replace(',', ',,')},format=raw,if=none,id=rb,snapshot=on,rerror=report",
                                "-device", "ide-hd,drive=rb,bus=ide.0,unit=0" + case.geometry,
                                "-debugcon", "file:" + str(log), "-trace",
                                f"events={str(events).replace(',', ',,')},file={str(trace).replace(',', ',,')}"]
        if case.rom is not None:
            invocation += ["-option-rom", str(directory / f"int13-{case.rom}.rom")]
        uninstrumented = case.source == "retroboot-hdd"
        memory_hash = None
        if uninstrumented:
            dump = directory / (name + "-memory.bin")
            dump.unlink(missing_ok=True)
            code, error = run_until_marker(invocation, log, marker, dump, 0x10000)
        else:
            result = subprocess.run(invocation, capture_output=True, text=True, timeout=30)
            code, error = result.returncode, result.stderr
        output = log.read_text(encoding="utf-8") if log.exists() else ""
        check_result(name, code, output + error, marker, uninstrumented)
        if case.source == "hdd-menu-model" and "RB MENU MODEL PASS" not in output:
            raise ValueError(f"{name}: native menu model tests did not pass")
        if case.source == "hdd-scan-model" and "RB SCAN MODEL PASS" not in output:
            raise ValueError(f"{name}: native partition parser tests did not pass")
        if case.source == "hdd-volume-model" and "RB VOLUME MODEL PASS" not in output:
            raise ValueError(f"{name}: native volume parser tests did not pass")
        if case.source == "hdd-handoff-model" and "RB HANDOFF MODEL PASS" not in output:
            raise ValueError(f"{name}: native handoff preparation tests did not pass")
        if marker == "RB HDD PASS" or case.source == "hdd-c-stack-fault":
            check_c_status(output, case.mode)
        if case.source == "hdd-config-model" and "RB CONFIG MODEL PASS" not in output:
            raise ValueError(f"{name}: native configuration model tests did not pass")
        if case.source == "hdd-state-model" and "RB STATE MODEL PASS" not in output:
            raise ValueError(f"{name}: native installation-state tests did not pass")
        if case.source == "hdd-profile-model" and "RB PROFILE MODEL PASS" not in output:
            raise ValueError("Missing native profile-test evidence")
        if case.source == "hdd-visibility-model" and "RB VISIBILITY MODEL PASS" not in output:
            raise ValueError(f"{name}: native visibility tests did not pass")
        causes = {"hdd-c-bss-fault": "C BSS ERROR", "hdd-c-data-fault": "C data ERROR",
                  "hdd-c-context-fault": "C context ERROR"}
        if case.source in causes and causes[case.source] not in output:
            raise ValueError(f"{name}: missing specific C failure diagnostic")
        if uninstrumented:
            memory_hash = check_runtime_memory(dump.read_bytes(), expected_memory,
                                               manifest["memory"]["normal"], case.mode)
        trace_text = trace.read_text(encoding="utf-8")
        check_trace(trace_text, 483 if once is not None else None, 2 if once else 3)
        calls = check_bios_route(output, case.mode) if case.rom is not None else []
        lbas = read_lbas(trace_text)
        if case.pair:
            pairs.setdefault(case.pair, {})[case.mode] = lbas
        if case.pair == "hdd-boundaries" and not all(lba in lbas for lba in (503, 504, 1007, 1008)):
            raise ValueError("Track/cylinder boundary reads were not exercised")
        if sha256(image) != before:
            raise ValueError(f"Image changed during boot: {image.name}")
        cases.append({"name": name, "image": image.name, "exit_code": code,
                      "stopped_after_marker": uninstrumented, "expected_result": marker,
                      "mode": case.mode, "bios_calls_after_probe": calls,
                      "loaded_stage2_sha256": memory_hash, "read_lbas": lbas,
                      "c_runtime_memory_verified": uninstrumented,
                      "image_unchanged": True, "block_writes": 0, "log": output})
        print(f"{name}: {marker}; no block writes; source unchanged", flush=True)
    for name, routes in pairs.items():
        if set(routes) != {"EDD", "CHS"} or routes["EDD"] != routes["CHS"]:
            raise ValueError(f"{name}: EDD and CHS read different sector sequences")
    report = {"ui": manifest["ui"], "qemu_version": version, "qemu_sha256": sha256(qemu),
              "bios_sha256": sha256(bios), "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "accelerator": "tcg", "cpu": "486",
              "ram_mib": 16, "disk_access": "EDD and CHS, IDE, disposable snapshot overlay",
              "identical_sector_sequence_pairs": len(pairs), "cases": cases}
    print(f"EDD/CHS: {len(pairs)} identical sector sequences; Stage 2, C BSS and stack guard verified in RAM", flush=True)
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"HDD boot test: {error}", file=sys.stderr)
        sys.exit(1)
