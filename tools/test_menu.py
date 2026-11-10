"""Exercise the normal HDD menu through real emulated keys and VGA memory."""

import argparse
import json
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from .build_hdd import ROOT, prepare_output, sha256
    from .test_hdd import check_bios_route, check_c_status, check_runtime_memory, check_trace, read_lbas
except ImportError:
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


def check_screen(data, view, selected, mode, mbr, boot):
    rows = screen_rows(data)
    if "RetroBoot" not in rows[2] or "Nur lesen" not in rows[2] or "Esc: Menue" not in rows[21]:
        raise ValueError("Missing menu frame or keyboard help")
    if view == 0:
        if "Keine Startprofile eingerichtet." not in rows[6] or "Automatischer Start: aus" not in rows[7]:
            raise ValueError("Menu must not invent boot profiles or arm automatic start")
        if f"BIOS-Leseweg: {mode}" not in rows[18]:
            raise ValueError("Wrong BIOS route on menu")
        if rows[17][19:22] != f"{struct.unpack_from('<H', boot)[0]:02X}h":
            raise ValueError("Wrong boot drive on menu")
        for index, label in enumerate(("Systeminformationen", "MBR-Partitionen", "Recovery-Hinweise")):
            row = 9 + index * 2
            attributes = data[row * 160 + 9:row * 160 + 150:2]
            if label not in rows[row] or attributes != bytes([0x70 if index == selected else 0x17]) * 71:
                raise ValueError("Incorrect menu label or selection highlight")
            if rows[row][5] != (">" if index == selected else " "):
                raise ValueError("Selection arrow disagrees with highlight")
    elif view == 1:
        drive, _, low, high = struct.unpack("<HHII", boot)
        if (rows[7][29:31] != f"{drive:02X}" or rows[8][29:32] != mode
                or rows[11][6:23] != f"{high:08X}:{low:08X}"
                or rows[13][29:37] != f"{struct.unpack_from('<I', mbr, 440)[0]:08X}"):
            raise ValueError("System information differs from boot context/MBR")
    elif view == 2:
        if "Primaere MBR-Eintraege" not in rows[5]:
            raise ValueError("Missing MBR view")
        for index in range(4):
            entry = mbr[446 + 16 * index:462 + 16 * index]
            start, count = struct.unpack_from("<II", entry, 8)
            row = rows[9 + index]
            if (row[5] != str(index + 1) or row[10:12] != f"{entry[0]:02X}"
                    or row[16:18] != f"{entry[4]:02X}" or row[23:31] != f"{start:08X}"
                    or row[39:47] != f"{count:08X}"):
                raise ValueError(f"Displayed primary slot {index + 1} differs from the source MBR")
    elif view == 3:
        if "Wiederherstellung ist noch nicht verfuegbar." not in rows[8]:
            raise ValueError("Recovery availability is not stated")
    else:
        raise ValueError("Unknown menu view")
    return rows


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
    source, output = ROOT / "build/hdd", ROOT / "build/menu"
    prepare_output(output)
    result_file = output / "menu-results.json"
    result_file.unlink(missing_ok=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
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
        for mode, rom in (("EDD", 0), ("CHS", 1)):
            name = image_name + "-menu-" + mode.lower()
            image = source / (image_name + ".img")
            before = sha256(image)
            if before != manifest["artifacts"][image.name]["sha256"]:
                raise ValueError("Unexpected menu image content")
            with image.open("rb") as stream:
                mbr = stream.read(512)
            log, trace, error = (output / (name + suffix) for suffix in (".log", ".trace", "-stderr.log"))
            log.unlink(missing_ok=True); trace.unlink(missing_ok=True)
            invocation = command + ["-drive", f"file={str(image).replace(',', ',,')},format=raw,if=none,id=rb,snapshot=on",
                                    "-device", "ide-hd,drive=rb,bus=ide.0,unit=0",
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
                        rows = check_screen(vram.read_bytes(), view, selected, mode, mbr, data[boot_offset:boot_offset + 12])
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
            check_c_status(text, mode)
            calls = check_bios_route(text, mode)
            trace_text = trace.read_text(encoding="utf-8")
            check_trace(trace_text)
            lbas = read_lbas(trace_text)
            pairs.setdefault(image_name, {})[mode] = lbas
            if sha256(image) != before:
                raise ValueError("Menu changed its source image")
            results.append({"name": name, "mode": mode, "screens": screens, "read_lbas": lbas,
                            "bios_calls_after_probe": calls, "image_unchanged": True, "block_writes": 0})
            print(f"{name}: {len(screens)} VGA/keyboard states verified; no disk writes", flush=True)
    if any(routes["EDD"] != routes["CHS"] for routes in pairs.values()):
        raise ValueError("Menu EDD/CHS sector sequences differ")
    report = {"qemu_version": subprocess.check_output([str(qemu), "--version"], text=True).splitlines()[0],
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
