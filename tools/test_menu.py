"""Exercise the normal HDD menu through real emulated keys and VGA memory."""

import argparse
import json
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from .ui_text import LANGUAGES, checked_catalog, output_name, ERROR_KEYS, VOLUME_KEYS
    from .build_hdd import ROOT, prepare_output, sha256
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
except ImportError:
    from ui_text import LANGUAGES, checked_catalog, output_name, ERROR_KEYS, VOLUME_KEYS
    from build_hdd import ROOT, prepare_output, sha256
    from test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas


class Qmp:
    def __init__(self, process):
        self.process, self.responses, self.serial = process, queue.Queue(), 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        try:
            greeting = self.responses.get(timeout=5)
        except queue.Empty as error:
            raise ValueError("QMP greeting timed out") from error
        if not greeting or "QMP" not in greeting:
            raise ValueError("Missing QMP greeting")
        self.call("qmp_capabilities")

    def read(self):
        try:
            for line in self.process.stdout:
                if line.strip():
                    self.responses.put(json.loads(line))
        except (ValueError, OSError) as error:
            self.responses.put({"error": str(error)})
        finally:
            self.responses.put(None)

    def call(self, command, arguments=None):
        self.serial += 1
        request = {"execute": command, "id": self.serial}
        if arguments is not None:
            request["arguments"] = arguments
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                response = self.responses.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty as error:
                raise ValueError(f"QMP {command} timed out") from error
            if response is None or "error" in response:
                raise ValueError(f"QMP {command} failed: {response}")
            if response.get("id") == self.serial:
                return response["return"]
        raise ValueError(f"QMP {command} timed out")


def wait_marker(process, log, marker):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        if marker in text:
            return text
        if process.poll() is not None:
            raise ValueError(f"Guest exited before {marker!r}: {text}")
        time.sleep(0.01)
    raise ValueError(f"Menu did not reach {marker!r}")


def screen_rows(data):
    if len(data) != 4000:
        raise ValueError("Expected an 80x25 VGA text page")
    return [data[row * 160:(row + 1) * 160:2].decode("cp437") for row in range(25)]


def expected_partitions(image):
    """Read display values from known-valid fixtures, without judging validity."""
    def record(block, slot, table=0, logical=0, base=0):
        raw = block[446 + 16 * slot:462 + 16 * slot]
        start, count = struct.unpack_from("<II", raw, 8)
        return {"kind": "L" if logical else "P", "slot": logical or slot + 1,
                "flag": raw[0], "type": raw[4], "start": base + start,
                "sectors": count, "table": table}

    with image.open("rb") as stream:
        mbr = stream.read(512)
        entries = [record(mbr, slot) for slot in range(4)]
        extended = [p for p in entries if p["type"] in (5, 15)]
        if not extended:
            return entries
        base = current = extended[0]["start"]
        visited = set()
        while current not in visited and len(visited) < 16:
            visited.add(current)
            stream.seek(current * 512)
            block = stream.read(512)
            if block[450]:
                entries.append(record(block, 0, current, len(entries) - 3, current))
            if not block[466]:
                return entries
            current = base + struct.unpack_from("<I", block, 470)[0]
    raise ValueError("Display oracle only accepts bounded known-valid fixtures")


def check_screen(data, view, selected, mode, mbr, boot, strings, partitions=None, page=0,
                 status=0, error_lba=0, error_slot=0, volume=None):
    rows = screen_rows(data)

    def at(row, column, key):
        expected = strings[key]
        if rows[row][column:column + len(expected)] != expected:
            raise ValueError(f"Wrong localized VGA text: {key} at {row},{column}")

    if "RetroBoot" not in rows[2]:
        raise ValueError("Missing menu frame or keyboard help")
    at(2, 65, "READ_ONLY")
    at(21, 4, "KEY_HELP")
    at(22, 4, "FUNCTION_HELP")
    if view in (1, 2):
        row = 15 if view == 1 else 19
        if mode == "CHS":
            at(row, 4, "CHS_HEADS")
            at(row, 24, "CHS_SECTORS")
        else:
            at(row, 4, "EDD_GEOMETRY")
    if view == 0:
        at(5, 4, "BOOT_MENU")
        at(6, 4, "NO_PROFILES")
        at(7, 4, "AUTO_OFF")
        at(17, 4, "DRIVE")
        at(18, 4, "ROUTE_" + mode)
        if rows[17][19:22] != f"{struct.unpack_from('<H', boot)[0]:02X}h":
            raise ValueError("Wrong boot drive on menu")
        for index, key in enumerate(("SYSTEM_INFO", "PARTITIONS", "RECOVERY")):
            row = 9 + index * 2
            at(row, 8, key)
            attributes = data[row * 160 + 9:row * 160 + 150:2]
            if attributes != bytes([0x70 if index == selected else 0x17]) * 71:
                raise ValueError("Incorrect menu label or selection highlight")
            if rows[row][5] != (">" if index == selected else " "):
                raise ValueError("Selection arrow disagrees with highlight")
    elif view == 1:
        for row, key in ((5, "SYSTEM_INFO"), (7, "DRIVE_HEX"), (8, "ROUTE"),
                         (10, "REACHABLE"), (13, "DISK_ID"), (18, "BOOT_SNAPSHOT")):
            at(row, 4, key)
        drive, _, low, high = struct.unpack("<HHII", boot)
        if (rows[7][29:31] != f"{drive:02X}" or rows[8][29:32] != mode
                or rows[11][6:23] != f"{high:08X}:{low:08X}"
                or rows[13][29:37] != f"{struct.unpack_from('<I', mbr, 440)[0]:08X}"):
            raise ValueError("System information differs from boot context/MBR")
    elif view == 2:
        at(5, 4, "PARTITION_TITLE")
        if status:
            for row, key in ((8, "SCAN_FAILED"), (10, ERROR_KEYS[status]), (12, "LBA_HEX"),
                             (13, "ENTRY"), (16, "NO_CHANGES"), (18, "SCAN_HELP")):
                at(row, 4, key)
            if (rows[12][23:31] != f"{error_lba:08X}"
                    or rows[6][4:74].strip() or rows[7][4:74].strip()):
                raise ValueError("Missing scan error/LBA or unsafe partial success display")
            expected_slot = str(error_slot) if error_slot else strings["WHOLE_SECTOR"]
            if rows[13][23:23 + len(expected_slot)] != expected_slot:
                raise ValueError("Wrong failing partition entry")
        else:
            at(6, 4, "SCAN_OK")
            at(7, 4, "TABLE_HEADER")
            at(18, 4, "PAGE")
            at(18, 20, "PAGING")
            if partitions is None:
                raise ValueError("Missing structural result or display oracle")
            for index in range(8):
                row = rows[9 + index]
                if page * 8 + index >= len(partitions):
                    if row[4:62].strip():
                        raise ValueError("Stale partition row after page change")
                    continue
                p = partitions[page * 8 + index]
                if (row[4:7].strip() != f"{p['kind']}{p['slot']}"
                        or row[10:12] != f"{p['flag']:02X}" or row[16:18] != f"{p['type']:02X}"
                        or row[23:31] != f"{p['start']:08X}" or row[39:47] != f"{p['sectors']:08X}"
                        or row[54:62] != f"{p['table']:08X}"):
                    raise ValueError(f"Displayed partition {page * 8 + index} differs from source sectors")
            if rows[18][10:12].strip() != str(page + 1) or rows[18][14:16].strip() != str((len(partitions) + 7) // 8):
                raise ValueError("Incorrect partition pagination")
    elif view == 3:
        for row, key in ((5, "RECOVERY"), (8, "RECOVERY_MISSING"),
                         (10, "RECOVERY_PAGES"), (13, "RECOVERY_READ_ONLY")):
            at(row, 4, key)
    elif view == 4:
        at(5, 4, "VOLUME_TITLE")
        at(6, 4, "VOLUME_SCOPE")
        at(19, 4, "VOLUME_HELP")
        if volume is None:
            at(8, 4, "VOLUME_NONE")
            if any(row[4:78].strip() for row in rows[9:18]):
                raise ValueError("Empty volume list contains stale details")
        else:
            at(8, 4, "VOLUME_ENTRY")
            at(8, 45, "VOLUME_PTYPE")
            at(9, 4, "VOLUME_LBA")
            at(11, 4, VOLUME_KEYS[volume["status"]])
            label = ("L" if volume["logical"] else "P") + str(volume["slot"])
            if (rows[8][29:29 + len(label)] != label or rows[8][54:56] != f'{volume["type"]:02X}'
                    or rows[9][29:37] != f'{volume["start"]:08X}'):
                raise ValueError("Wrong selected volume identity")
            if volume["status"]:
                if any(row[4:78].strip() for row in rows[13:18]):
                    raise ValueError("Failed volume check displays stale successful metadata")
            else:
                for row, key in ((13, "VOLUME_KIND"), (14, "VOLUME_BYTES"), (15, "VOLUME_TOTAL_LABEL"),
                                 (16, "VOLUME_CLUSTERS"), (17, "VOLUME_DATA")):
                    at(row, 4, key)
                if (rows[13][29:34] != f'FAT{volume["bits"]}'
                        or rows[14][29:34].strip() != str(volume["cluster_bytes"])
                        or rows[15][29:37] != f'{volume["total"]:08X}'
                        or rows[16][29:37] != f'{volume["clusters"]:08X}'
                        or rows[17][29:37] != f'{volume["data_lba"]:08X}'):
                    raise ValueError("Wrong FAT header arithmetic displayed")
    else:
        raise ValueError("Unknown menu view")
    return rows


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
        raise ValueError("SeaBIOS and its standard VGA ROM must be present; use --bios")
    source = ROOT / "build" / output_name("hdd", args.language)
    output = ROOT / "build" / output_name("menu", args.language)
    prepare_output(output)
    result_file = output / "menu-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    strings = checked_catalog(manifest, args.language)
    payload = (source / "stage2.bin").read_bytes()
    if sha256(source / "stage2.bin") != manifest["artifacts"]["stage2.bin"]["sha256"]:
        raise ValueError("Stage 2 differs from manifest")
    for name in ("int13-0.rom", "int13-1.rom"):
        if sha256(source / name) != manifest["artifacts"][name]["sha256"]:
            raise ValueError(f"Test ROM differs from manifest: {name}")
    events = output / "ide-events.txt"
    events.write_text("ide_sector_read\nide_sector_write\nblk_co_pwritev\n", encoding="ascii")
    command = [str(qemu), "-L", str(bios.parent), "-bios", str(bios),
               "-machine", "pc-i440fx-8.2,accel=tcg", "-cpu", "486", "-m", "16",
               "-nodefaults", "-vga", "std", "-boot", "c", "-display", "none",
               "-monitor", "none", "-serial", "none", "-nic", "none", "-no-reboot",
               "-global", "isa-debugcon.iobase=0xe9", "-qmp", "stdio"]
    # Keyboard input is delivered through QEMU's real PS/2 device, not a BIOS stub.
    actions = [("up", 0, 2), ("down", 0, 0), ("down", 0, 1), ("ret", 2, 1),
               ("esc", 0, 1), ("f8", 3, 2), ("esc", 0, 2), ("f2", 2, 1),
               ("esc", 0, 1), ("a", 0, 1), ("esc", 0, 1), ("up", 0, 0),
               ("ret", 1, 0), ("esc", 0, 0)]
    results, pairs = [], {}
    for image_name in ("retroboot-hdd", "retroboot-reference"):
        geometry = ",lcyls=973,lheads=255,lsecs=63" if image_name == "retroboot-reference" else ""
        campaigns = [("EDD", 0, geometry, 0), ("CHS", 1, geometry, 0)]
        if image_name == "retroboot-reference":
            campaigns.append(("CHS", 1, "", 8))  # automatic geometry is one cylinder too short for P4
        for mode, rom, geometry, expected_status in campaigns:
            name = image_name + "-menu-" + mode.lower()
            if expected_status:
                name += "-short-geometry"
            image = source / (image_name + ".img")
            before = sha256(image)
            if before != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError("Unexpected menu image content")
            with image.open("rb") as stream:
                mbr = stream.read(512)
            partitions = expected_partitions(image) if not expected_status else None
            log, trace, error = (output / (name + suffix) for suffix in (".log", ".trace", "-stderr.log"))
            log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
            invocation = command + ["-drive", f"file={str(image).replace(',', ',,')},format=raw,if=none,id=rb,snapshot=on",
                                    "-device", "ide-hd,drive=rb,bus=ide.0,unit=0" + geometry,
                                    "-option-rom", str(source / f"int13-{rom}.rom"),
                                    "-debugcon", "file:" + str(log), "-trace",
                                    f"events={events},file={trace}"]
            screens = []
            with error.open("w", encoding="utf-8") as errors, subprocess.Popen(
                    invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=errors, text=True, bufsize=1) as process:
                try:
                    qmp = Qmp(process)
                    wait_marker(process, log, "RB MENU READY")
                    for serial, (key, view, selected) in enumerate([(None, 0, 0)] + actions):
                        if key is not None:
                            qmp.call("send-key", {"keys": [{"type": "qcode", "data": key}], "hold-time": 30})
                            time.sleep(0.05)  # release before another press, including a repeated key
                            wait_marker(process, log, f"RB MENU {serial:04X} view={view:04X} selected={selected:04X}")
                        qmp.call("stop")
                        vram, ram = (output / f"{name}-{serial:02d}{suffix}.bin" for suffix in ("-vga", "-ram"))
                        qmp.call("pmemsave", {"val": 0xB8000, "size": 4000, "filename": str(vram)})
                        qmp.call("pmemsave", {"val": 0x10000, "size": 0x10000, "filename": str(ram)})
                        data = ram.read_bytes()
                        memory = manifest["memory"]["normal"]
                        check_runtime_memory(data, payload, memory, mode)
                        boot_offset = memory["symbols"]["_rb_boot"]
                        rows = check_screen(vram.read_bytes(), view, selected, mode, mbr,
                                            data[boot_offset:boot_offset + 12], strings, partitions=partitions,
                                            status=expected_status, error_slot=4 if expected_status else 0)
                        text_file = output / f"{name}-{serial:02d}.txt"
                        text_file.write_text("\n".join(rows) + "\n", encoding="utf-8")
                        if serial in (0, 3, 4, 6, 8, 13):
                            qmp.call("screendump", {"filename": str(output / f"{name}-{serial:02d}.png"), "format": "png"})
                        screens.append({"key": key, "view": view, "selected": selected, "vga_sha256": sha256(vram)})
                        qmp.call("cont")
                    qmp.call("quit")
                    if process.wait(timeout=5) != 0:
                        raise ValueError("QEMU did not exit cleanly")
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            text = log.read_text(encoding="utf-8")
            if text.count(f"RB UI {args.language} CP437") != 1:
                raise ValueError("Wrong menu language marker")
            check_c_status(text, mode)
            calls = check_bios_route(text, mode)
            scan_statuses = re.findall(r"^RB SCAN status=([0-9A-F]{4})", text, re.MULTILINE)
            if scan_statuses != [f"{expected_status:04X}"] * 2:
                raise ValueError("Wrong number/result of menu partition scans")
            trace_text = trace.read_text(encoding="utf-8")
            check_trace(trace_text)
            lbas = read_lbas(trace_text)
            if not expected_status:
                pairs.setdefault(image_name, {})[mode] = lbas
            if sha256(image) != before:
                raise ValueError("Menu changed its source image")
            results.append({"name": name, "mode": mode, "geometry": geometry,
                            "scan_status": expected_status, "screens": screens, "read_lbas": lbas,
                            "bios_calls_after_probe": calls, "image_unchanged": True, "block_writes": 0})
            print(f"{name}: {len(screens)} VGA/keyboard states verified; no disk writes", flush=True)
    if any(routes["EDD"] != routes["CHS"] for routes in pairs.values()):
        raise ValueError("Menu EDD/CHS sector sequences differ")
    report = {"ui": manifest["ui"], "qemu_version": subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0],
              "qemu_sha256": sha256(qemu), "bios_sha256": sha256(bios),
              "vga_bios_sha256": sha256(bios.with_name("vgabios-stdvga.bin")),
              "machine": "pc-i440fx-8.2", "cpu": "486", "ram_mib": 16, "cases": results}
    result_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, queue.Empty, subprocess.SubprocessError) as error:
        print(f"Menu test: {error}", file=sys.stderr)
        sys.exit(1)
