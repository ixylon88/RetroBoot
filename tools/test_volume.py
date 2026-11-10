"""Exercise read-only FAT header inspection through real BIOS keyboard input."""

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
    from .ui_text import LANGUAGES, checked_catalog, output_name
    from .volume_fixtures import FIRST_LBA
except ImportError:
    from build_hdd import ROOT, prepare_output, sha256
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
    from test_menu import Qmp, check_screen, expected_partitions, wait_marker
    from ui_text import LANGUAGES, checked_catalog, output_name
    from volume_fixtures import FIRST_LBA


def expected_volume(partitions, index, fixture, spec):
    p = partitions[index]
    result = dict(p, logical=p["kind"] == "L", status=0, bits=16,
                  cluster_bytes=2048, total=128457, clusters=32043, data_lba=p["start"] + 285)
    if fixture == "retroboot-reference" and index != 5:
        result["status"] = 2  # reference OS/data volumes are unformatted placeholders
    elif fixture.startswith("volume-"):
        if index == 0:
            result.update(cluster_bytes=512, total=5073, clusters=5000, data_lba=131145)
        elif index == 1:
            result.update(bits=32, cluster_bytes=512, total=71126, clusters=70000, data_lba=141126)
        elif index == 2:
            result["status"] = 16  # type 07 is not proof of an NTFS filesystem
        if index == spec.get("target"):
            result["status"] = spec["status"]
    return result


def actions_for(fixture, spec):
    actions = [(None, 0, None)]
    if spec.get("table_status"):
        return actions + [("f3", 2, None), ("esc", 0, None), ("f8", 3, None),
                          ("f3", 2, None), ("f2", 2, None)]
    if spec.get("empty"):
        return actions + [("f3", 4, None), ("left", 4, None), ("right", 4, None),
                          ("f3", 4, None), ("esc", 0, None), ("f2", 2, None)]
    if fixture == "retroboot-reference":
        actions += [("f3", 4, 0), ("left", 4, 6), ("left", 4, 5), ("f3", 4, 5)]
    elif fixture == "retroboot-hdd":
        actions += [("f3", 4, 4), ("right", 4, 4), ("left", 4, 4), ("f3", 4, 4)]
    elif fixture == "volume-headers":
        actions += [("f3", 4, 0), ("right", 4, 1), ("right", 4, 2),
                    ("right", 4, 4), ("right", 4, 0), ("left", 4, 4), ("f3", 4, 4)]
    else:
        actions += [("f3", 4, 0)]
        if spec["target"] == 1:
            actions += [("right", 4, 1)]
        actions += [("f3", 4, spec["target"])]
    return actions + [("esc", 0, None), ("f8", 3, None),
                      ("f3", 4, 4 if fixture == "retroboot-hdd" else 0), ("f2", 2, None)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--bios", type=Path)
    parser.add_argument("--language", choices=LANGUAGES, default="en")
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError("qemu-system-i386 not found")
    qemu = Path(executable).resolve()
    bios = (args.bios or qemu.parent.parent / "share/seabios/bios-256k.bin").resolve()
    if not bios.is_file() or not bios.with_name("vgabios-stdvga.bin").is_file():
        raise ValueError("SeaBIOS and its VGA ROM must be present; use --bios")
    source = ROOT / "build" / output_name("hdd", args.language)
    output = ROOT / "build" / output_name("volume", args.language)
    prepare_output(output)
    result_file = output / "volume-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    strings = checked_catalog(manifest, args.language)
    for name in ("stage2.bin", "int13-0.rom", "int13-1.rom"):
        if sha256(source / name) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Changed volume test component: " + name)
    payload, memory = (source / "stage2.bin").read_bytes(), manifest["memory"]["normal"]
    events = output / "ide-events.txt"
    events.write_text("ide_sector_read\nide_sector_write\nblk_co_pwritev\n", encoding="ascii")
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "c", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9", "-qmp", "stdio"]
    fixtures = dict(manifest["volume_cases"], **{"retroboot-hdd": {}, "retroboot-reference": {}})
    results, pairs = [], {}
    for fixture, original_spec in fixtures.items():
        geometry = ",lcyls=973,lheads=255,lsecs=63" if fixture == "retroboot-reference" else ""
        campaigns = [("EDD", 0, geometry, original_spec), ("CHS", 1, geometry, original_spec)]
        if fixture == "retroboot-reference":
            campaigns.append(("CHS", 1, "", {"table_status": 8}))
        for mode, rom, geometry, spec in campaigns:
            name = fixture + "-" + mode.lower() + ("-short" if spec.get("table_status") == 8 else "")
            image = source / (fixture + ".img")
            before = sha256(image)
            if before != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError("Changed volume fixture: " + fixture)
            with image.open("rb") as stream:
                mbr = stream.read(512)
            partitions = None if spec.get("table_status") else expected_partitions(image)
            table_reads = [0] + ([p["table"] for p in partitions[4:]] if partitions else [])
            log, trace, error = (output / (name + suffix) for suffix in (".log", ".trace", "-stderr.log"))
            log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
            drive = str(image)
            if "fault_once" in spec:
                config = output / (name + ".conf")
                config.write_text('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                                  f'sector = "{FIRST_LBA}"\nonce = "' + ("on" if spec["fault_once"] else "off") + '"\n',
                                  encoding="ascii")
                drive = f"blkdebug:{config}:{image}"
            invocation = command + ["-drive", f"file={drive.replace(',', ',,')},format=raw,if=none,id=rb,snapshot=on,rerror=report",
                                    "-device", "ide-hd,drive=rb,bus=ide.0,unit=0" + geometry,
                                    "-option-rom", str(source / f"int13-{rom}.rom"),
                                    "-debugcon", "file:" + str(log), "-trace",
                                    f"events={str(events).replace(',', ',,')},file={str(trace).replace(',', ',,')}"]
            screens, expected_reads, volume_markers = [], [], []
            selected, empty_count, scan_count, failed_once = 0, 0, 0, False
            with error.open("w", encoding="utf-8") as errors, subprocess.Popen(
                    invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=errors, text=True, bufsize=1) as process:
                try:
                    qmp = Qmp(process)
                    wait_marker(process, log, "RB MENU READY")
                    for serial, (key, view, index) in enumerate(actions_for(fixture, spec)):
                        volume = expected_volume(partitions, index, fixture, spec) if index is not None else None
                        if key in ("f2", "f3"):
                            selected = 1; scan_count += 1; expected_reads.extend(table_reads)
                        elif key == "f8":
                            selected = 2
                        if view == 4 and key in ("f3", "left", "right"):
                            if volume is None:
                                empty_count += 1
                            else:
                                if volume["type"] not in (7, 23):
                                    attempts = 1
                                    if "fault_once" in spec and volume["start"] == FIRST_LBA:
                                        attempts = 3 if not spec["fault_once"] else 1 if failed_once else 2
                                        failed_once = True
                                    expected_reads.extend([volume["start"]] * attempts)
                                volume_markers.append((index, volume["status"], volume["start"],
                                                       0 if volume["status"] else volume["bits"]))
                        if key is not None:
                            qmp.call("send-key", {"keys": [{"type": "qcode", "data": key}], "hold-time": 30})
                            time.sleep(0.05)
                            wait_marker(process, log, f"RB MENU {serial:04X} view={view:04X} selected={selected:04X} page=0000")
                        qmp.call("stop")
                        vram, ram = (output / f"{name}-{serial:02d}{suffix}.bin" for suffix in ("-vga", "-ram"))
                        qmp.call("pmemsave", {"val": 0xB8000, "size": 4000, "filename": str(vram)})
                        qmp.call("pmemsave", {"val": 0x10000, "size": 0x10000, "filename": str(ram)})
                        data = ram.read_bytes()
                        check_runtime_memory(data, payload, memory, mode)
                        offset = memory["symbols"]["_rb_boot"]
                        table_status = spec.get("table_status", 0)
                        rows = check_screen(vram.read_bytes(), view, selected, mode, mbr, data[offset:offset + 12], strings,
                                            partitions=partitions, volume=volume, status=table_status,
                                            error_slot=4 if table_status == 8 else 1 if table_status else 0)
                        (output / f"{name}-{serial:02d}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
                        if serial == 1 or (view == 4 and fixture in ("volume-headers", "retroboot-reference", "volume-fat32")):
                            qmp.call("screendump", {"filename": str(output / f"{name}-{serial:02d}.png"), "format": "png"})
                        screens.append({"key": key, "view": view, "volume_index": index,
                                        "volume_status": volume["status"] if volume else None,
                                        "vga_sha256": sha256(vram)})
                        qmp.call("cont")
                    qmp.call("quit")
                    if process.wait(timeout=5) != 0:
                        raise ValueError("QEMU did not exit cleanly")
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            text = log.read_text(encoding="utf-8")
            if text.count(f"RB UI {args.language} CP437") != 1:
                raise ValueError("Wrong volume test language")
            check_c_status(text, mode)
            calls = check_bios_route(text, mode)
            markers = [tuple(int(x, 16) for x in m) for m in re.findall(
                r"^RB VOLUME index=([0-9A-F]{4}) status=([0-9A-F]{4}) lba=([0-9A-F]{8}) fat=([0-9A-F]{4})$", text, re.MULTILINE)]
            if markers != volume_markers or text.count("RB VOLUME EMPTY") != empty_count:
                raise ValueError("Incorrect volume results: " + name)
            scans = re.findall(r"^RB SCAN status=([0-9A-F]{4})", text, re.MULTILINE)
            if len(scans) != scan_count or any(int(s, 16) != spec.get("table_status", 0) for s in scans):
                raise ValueError("Missing fresh partition validation")
            trace_text = trace.read_text(encoding="utf-8")
            check_trace(trace_text)
            lbas = read_lbas(trace_text)
            boot_calls = check_bios_route(text.split("RB SCAN BEGIN", 1)[0], mode)
            boot_reads = 1 + boot_calls.count("42" if mode == "EDD" else "02")
            if lbas[boot_reads:] != expected_reads:
                raise ValueError(f"Wrong volume read bounds/retries in {name}: {lbas[boot_reads:]}, expected {expected_reads}")
            if sha256(image) != before:
                raise ValueError("Volume check changed its source image")
            if spec.get("table_status") != 8:
                pairs.setdefault(fixture, {})[mode] = lbas
            results.append({"name": name, "mode": mode, "geometry": geometry, "screens": screens,
                            "read_lbas": lbas, "volume_read_lbas": expected_reads,
                            "bios_calls_after_probe": calls, "image_unchanged": True, "block_writes": 0})
            print(f"{name}: {len(screens)} VGA/keyboard states; exact bounded reads, no writes", flush=True)
    if any(routes["EDD"] != routes["CHS"] for routes in pairs.values()):
        raise ValueError("Volume EDD/CHS read sequences differ")
    report = {"ui": manifest["ui"], "qemu_version": subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0],
              "qemu_sha256": sha256(qemu), "bios_sha256": sha256(bios),
              "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "cpu": "486", "ram_mib": 16, "cases": results}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as error:
        print(f"Volume header test: {error}", file=sys.stderr)
        sys.exit(1)
