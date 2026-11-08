"""Boot the positive and negative ABI fixtures in QEMU, with no attached HDD."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .build_abi_probe import ROOT, prepare_output, sha256
except ImportError:
    from build_abi_probe import ROOT, prepare_output, sha256

CASES = (("abi-probe", 33, "RB ABI PASS"),
         ("abi-probe-bss-fault", 35, "C BSS FAIL"),
         ("abi-probe-data-fault", 35, "C data FAIL"))


def check_result(name, returncode, log, expected_code, marker):
    if returncode != expected_code or marker not in log:
        raise ValueError(f"{name}: expected exit {expected_code} and {marker!r}, got {returncode}:\n{log}")
    if expected_code != 33 and ("RB ABI PASS" in log or "RB ABI FAIL" not in log):
        raise ValueError(f"{name}: invalid negative-test result")
    if expected_code == 33 and "FAIL" in log:
        raise ValueError(f"{name}: success and failure markers were both present")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--bios", type=Path, help="SeaBIOS bios-256k.bin (VGA ROM in the same directory)")
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError("qemu-system-i386 not found; install qemu-system-x86")
    qemu = Path(executable).resolve()
    bios = args.bios or qemu.parent.parent / "share/seabios/bios-256k.bin"
    bios = bios.resolve()
    if not bios.is_file() or not bios.with_name("vgabios-stdvga.bin").is_file():
        raise ValueError("SeaBIOS and its standard VGA ROM must be present; use --bios")
    directory = ROOT / "build" / "abi"
    prepare_output(directory)
    result_file = directory / "boot-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    version = subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0]
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "a", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9",
               "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    cases = []
    for name, expected_code, marker in CASES:
        image, log = directory / (name + ".img"), directory / (name + ".log")
        before = sha256(image)
        if before != manifest["artifacts"][image.name]["sha256"]:
            raise ValueError(f"Unexpected image content: {image.name}; rebuild first")
        # QEMU treats commas specially inside -drive key/value arguments.
        drive_path = str(image).replace(",", ",,")
        log.unlink(missing_ok=True)
        result = subprocess.run(command + ["-drive", f"file={drive_path},format=raw,if=floppy,readonly=on",
                                            "-debugcon", "file:" + str(log)],
                                capture_output=True, text=True, timeout=30)
        output = log.read_text(encoding="utf-8") if log.exists() else ""
        check_result(name, result.returncode, output + result.stderr, expected_code, marker)
        if sha256(image) != before:
            raise ValueError(f"Image changed during boot: {image.name}")
        cases.append({"name": name, "exit_code": result.returncode,
                      "expected_result": marker, "image_unchanged": True, "log": output})
        print(f"{name}: expected result confirmed ({marker})")
    report = {"qemu_version": version, "qemu_sha256": sha256(qemu),
              "bios_sha256": sha256(bios), "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "accelerator": "tcg", "cpu": "486",
              "ram_mib": 16, "attached_hard_disks": 0, "cases": cases}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"ABI boot test: {error}", file=sys.stderr)
        sys.exit(1)
