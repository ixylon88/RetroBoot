"""Boot HDD fixtures in disposable QEMU overlays; verify diagnostics and I/O."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_hdd import CASES, ROOT, prepare_output, sha256
except ImportError:
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


def run_until_marker(command, log, marker):
    """The hardware-facing image halts instead of accessing QEMU's exit port."""
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                output = log.read_text(encoding="utf-8") if log.exists() else ""
                if marker in output:
                    process.terminate()
                    _, error = process.communicate(timeout=5)
                    return process.returncode, error
                if process.poll() is not None:
                    _, error = process.communicate()
                    return process.returncode, error
                time.sleep(0.02)
            raise ValueError("Timed out waiting for the uninstrumented HDD image")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--bios", type=Path)
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError("qemu-system-i386 not found; install qemu-system-x86")
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent / "share/seabios/bios-256k.bin").resolve()
    if not bios.is_file() or not bios.with_name("vgabios-stdvga.bin").is_file():
        raise ValueError("SeaBIOS and its VGA ROM must be present; use --bios")
    directory = ROOT / "build/hdd"
    prepare_output(directory)
    result_file = directory / "boot-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    events = directory / "ide-events.txt"
    events.write_text("ide_sector_read\nide_sector_write\nblk_co_pwritev\n", encoding="ascii")
    version = subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0]
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "c", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    scenarios = [(name, name, marker, None) for name, marker in CASES.items()]
    scenarios += [("retroboot-hdd", "retroboot-hdd", "RB HDD PASS", None),
                  ("hdd-io-retry", "hdd-fragmented", "RB HDD PASS", True),
                  ("hdd-io-failure", "hdd-fragmented", "RB READ ERROR", False)]
    cases = []
    for name, source, marker, once in scenarios:
        image, log, trace = (directory / (name + suffix) for suffix in (".img", ".log", ".trace"))
        image = directory / (source + ".img")
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
        invocation = command + ["-drive", f"file={drive.replace(',', ',,')},format=raw,if=ide,snapshot=on,rerror=report",
                                "-debugcon", "file:" + str(log), "-trace",
                                f"events={str(events).replace(',', ',,')},file={str(trace).replace(',', ',,')}"]
        uninstrumented = name == "retroboot-hdd"
        if uninstrumented:
            code, error = run_until_marker(invocation, log, marker)
        else:
            result = subprocess.run(invocation, capture_output=True, text=True, timeout=30)
            code, error = result.returncode, result.stderr
        output = log.read_text(encoding="utf-8") if log.exists() else ""
        check_result(name, code, output + error, marker, uninstrumented)
        check_trace(trace.read_text(encoding="utf-8"), 483 if once is not None else None,
                    2 if once else 3)
        if sha256(image) != before:
            raise ValueError(f"Image changed during boot: {image.name}")
        cases.append({"name": name, "image": image.name, "exit_code": code,
                      "stopped_after_marker": uninstrumented, "expected_result": marker,
                      "image_unchanged": True, "block_writes": 0, "log": output})
        print(f"{name}: {marker}; no block writes; source unchanged", flush=True)
    report = {"qemu_version": version, "qemu_sha256": sha256(qemu),
              "bios_sha256": sha256(bios), "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "accelerator": "tcg", "cpu": "486",
              "ram_mib": 16, "disk_access": "EDD, IDE, disposable snapshot overlay", "cases": cases}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"HDD boot test: {error}", file=sys.stderr)
        sys.exit(1)
