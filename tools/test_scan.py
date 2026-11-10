"""Exercise partition faults and pagination through the normal BIOS menu."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from .build_hdd import ROOT, prepare_output, sha256
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from .test_menu import Qmp, check_screen, expected_partitions, wait_marker
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, expected_partitions, wait_marker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--bios", type=Path)
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError("qemu-system-i386 not found")
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent / "share/seabios/bios-256k.bin").resolve()
    if not bios.is_file() or not bios.with_name("vgabios-stdvga.bin").is_file():
        raise ValueError("SeaBIOS and its standard VGA ROM must be present; use --bios")
    source, output = ROOT / "build/hdd", ROOT / "build/scan"
    prepare_output(output)
    result_file = output / "scan-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for name in ("stage2.bin", "int13-0.rom", "int13-1.rom"):
        if sha256(source / name) != manifest["artifacts"][name]["sha256"]:
            raise ValueError(f"Changed scan test component: {name}")
    payload = (source / "stage2.bin").read_bytes()
    memory = manifest["memory"]["normal"]
    events = output / "ide-events.txt"
    events.write_text("ide_sector_read\nide_sector_write\nblk_co_pwritev\n", encoding="ascii")
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "c", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9", "-qmp", "stdio"]
    results, pairs = [], {}
    for fixture, expected in manifest["scan_cases"].items():
        for mode, rom in (("EDD", 0), ("CHS", 1)):
            name = fixture + "-" + mode.lower()
            image = source / (fixture + ".img")
            before = sha256(image)
            if before != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError(f"Unexpected scan fixture: {fixture}")
            with image.open("rb") as stream:
                mbr = stream.read(512)
            partitions = expected_partitions(image) if expected["status"] == 0 else None
            log, trace, error = (output / (name + suffix) for suffix in (".log", ".trace", "-stderr.log"))
            log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
            drive = str(image)
            if "fault_once" in expected:
                config = output / (name + ".conf")
                config.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                                  'sector = "63"\nonce = "' + ("on" if expected["fault_once"] else "off") + '"\n',
                                  encoding="ascii")
                drive = f"blkdebug:{config}:{image}"
            invocation = command + ["-drive", f"file={drive.replace(',', ',,')},format=raw,if=none,id=rb,snapshot=on,rerror=report",
                                    "-device", "ide-hd,drive=rb,bus=ide.0,unit=0",
                                    "-option-rom", str(source / f"int13-{rom}.rom"),
                                    "-debugcon", "file:" + str(log), "-trace",
                                    f"events={str(events).replace(',', ',,')},file={str(trace).replace(',', ',,')}"]
            actions = [(None, 0, 0, 0), ("f2", 2, 1, 0)]
            if fixture == "scan-many":
                actions += [("pgdn", 2, 1, 1), ("pgdn", 2, 1, 2), ("pgdn", 2, 1, 2),
                            ("pgup", 2, 1, 1), ("pgup", 2, 1, 0), ("pgup", 2, 1, 0)]
            actions += [("esc", 0, 1, 0), ("f8", 3, 2, 0), ("esc", 0, 2, 0), ("f2", 2, 1, 0)]
            screens = []
            with error.open("w", encoding="utf-8") as errors, subprocess.Popen(
                    invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=errors, text=True, bufsize=1) as process:
                try:
                    qmp = Qmp(process)
                    wait_marker(process, log, "RB MENU READY")
                    for serial, (key, view, selected, page) in enumerate(actions):
                        if key is not None:
                            qmp.call("send-key", {"keys": [{"type": "qcode", "data": key}], "hold-time": 30})
                            time.sleep(0.05)
                            wait_marker(process, log, f"RB MENU {serial:04X} view={view:04X} selected={selected:04X} page={page:04X}")
                        qmp.call("stop")
                        vram, ram = (output / f"{name}-{serial:02d}{suffix}.bin" for suffix in ("-vga", "-ram"))
                        qmp.call("pmemsave", {"val": 0xB8000, "size": 4000, "filename": str(vram)})
                        qmp.call("pmemsave", {"val": 0x10000, "size": 0x10000, "filename": str(ram)})
                        data = ram.read_bytes()
                        check_runtime_memory(data, payload, memory, mode)
                        offset = memory["symbols"]["_rb_boot"]
                        rows = check_screen(vram.read_bytes(), view, selected, mode, mbr, data[offset:offset + 12],
                                            partitions=partitions, page=page, status=expected["status"],
                                            error_lba=expected["lba"], error_slot=expected["slot"])
                        (output / f"{name}-{serial:02d}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
                        if serial == 1 or page != 0:
                            qmp.call("screendump", {"filename": str(output / f"{name}-{serial:02d}.png"), "format": "png"})
                        screens.append({"key": key, "view": view, "selected": selected, "page": page,
                                        "vga_sha256": sha256(vram)})
                        qmp.call("cont")
                    qmp.call("quit")
                    if process.wait(timeout=5) != 0:
                        raise ValueError("QEMU did not exit cleanly")
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            text = log.read_text(encoding="utf-8")
            check_c_status(text, mode)
            calls = check_bios_route(text, mode)
            matches = re.findall(r"^RB SCAN status=([0-9A-F]{4}) count=([0-9A-F]{4}) ebr=([0-9A-F]{4}) lba=([0-9A-F]{8}) slot=([0-9A-F]{4})$", text, re.MULTILINE)
            if len(matches) != 2:
                raise ValueError("Each campaign must complete two explicit scans")
            for match in matches:
                status, count, ebrs, lba, slot = (int(value, 16) for value in match)
                if (status, lba, slot) != (expected["status"], expected["lba"], expected["slot"]):
                    raise ValueError(f"Wrong scan result for {name}: {match}")
                if status == 0 and (count, ebrs) != (expected["count"], expected["ebr_count"]):
                    raise ValueError("Incorrect number of partitions/EBRs")
            trace_text = trace.read_text(encoding="utf-8")
            check_trace(trace_text)
            lbas = read_lbas(trace_text)
            boot_calls = check_bios_route(text.split("RB SCAN BEGIN", 1)[0], mode)
            boot_reads = 1 + boot_calls.count("42" if mode == "EDD" else "02")
            second_reads = [0, 63] if expected.get("fault_once") else expected["reads"]
            scan_reads = expected["reads"] + second_reads
            if lbas[boot_reads:] != scan_reads:
                raise ValueError(f"Unexpected scan sector sequence in {name}: {lbas[boot_reads:]}")
            if sha256(image) != before:
                raise ValueError("Scanner changed its source image")
            pairs.setdefault(fixture, {})[mode] = lbas
            results.append({"name": name, "mode": mode, "status": expected["status"],
                            "screens": screens, "read_lbas": lbas, "scan_read_lbas": scan_reads,
                            "bios_calls_after_probe": calls, "image_unchanged": True, "block_writes": 0})
            print(f"{name}: status {expected['status']}, {len(screens)} VGA/keyboard states; bounded reads, no writes", flush=True)
    if any(routes["EDD"] != routes["CHS"] for routes in pairs.values()):
        raise ValueError("Scanner EDD/CHS sector sequences differ")
    report = {"qemu_version": subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0],
              "qemu_sha256": sha256(qemu), "bios_sha256": sha256(bios),
              "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "cpu": "486", "ram_mib": 16, "cases": results}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f"Partition scan test: {error}", file=sys.stderr)
        sys.exit(1)
