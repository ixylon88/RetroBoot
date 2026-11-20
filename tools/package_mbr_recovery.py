"""Package and boot the bilingual VirtualBox secondary IDE recovery disk test."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import uuid
import zipfile

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from prepare_dos_disk import set_vdi_geometry
from rescue_text import load_catalog
from test_mbr_recovery_disk import BACKUP, MODEL, OTHER, SECTORS

DISKS = (('Sicherung.vdi', '71717171-d413-4b6c-a375-146111111111', BACKUP),
         ('Vergleich.vdi', '71717171-d413-4b6c-a375-146122222222', OTHER))
LANGS = (('de', '-de', 'Deutsch'), ('en', '', 'English'))
INSTRUCTIONS = """RetroBoot – Sicherungsfestplatte prüfen / Verify a recovery disk

Deutsch
1. ZIP entpacken. Die ausgeschaltete BIOS-Test-VM erhält Sicherung.vdi am IDE-Controller
   als sekundären Master (Port 1, Gerät 0). Die Systemfestplatte kann abgezogen bleiben.
2. Deutsch/mbr-target.img in Laufwerk A einlegen, von A starten und V drücken.
   Es folgt RECOVERY MATCH, dann ORIGINAL REV 1 VERIFIED, APPROVED REV 2,
   LAST ISSUED 2 und RB ATA TARGET PASS. Die Startdiskette bleibt in A.
3. Für die Gegenprobe die VM ausschalten und Sicherung.vdi am selben Anschluss
   durch Vergleich.vdi ersetzen. Erneut von A starten und V drücken.
   Die andere Seriennummer führt zu RB ATA TARGET BLOCKED.

English
1. Extract the ZIP. In the powered-off BIOS test VM, attach Sicherung.vdi as the
   secondary IDE master (port 1, device 0). The source hard disk can stay disconnected.
2. Boot English/mbr-target.img in drive A and press V. RECOVERY MATCH is followed by
   ORIGINAL REV 1 VERIFIED, APPROVED REV 2, LAST ISSUED 2 and RB ATA TARGET PASS.
   The start diskette stays in A.
3. For the second run, power off and replace Sicherung.vdi with Vergleich.vdi at the
   same port. Boot from A and press V again. The different serial produces RB ATA TARGET BLOCKED.
"""


def make_vdis(converter, raw, work):
    base = work / 'base.vdi'
    subprocess.run([converter, 'convert', '-f', 'raw', '-O', 'vdi', raw, base], check=True)
    for name, value, _ in DISKS:
        dest = work / name
        shutil.copyfile(base, dest)
        with dest.open('r+b') as stream:
            h = stream.read(512)
            if struct.unpack_from('<II', h, 64) != (0xbeda107f, 0x10001):
                raise ValueError('Unsupported VDI signature')
            if struct.unpack_from('<I', h, 72)[0] == 384:
                if any(h[456:472]):
                    raise ValueError('Unexpected data in the VDI geometry extension')
                stream.seek(72)
                stream.write(struct.pack('<I', 400))
                stream.seek(468)
                stream.write(struct.pack('<I', 512))
            stream.seek(392)
            disk_id = uuid.UUID(value)
            stream.write(disk_id.bytes_le + uuid.uuid5(disk_id, 'RetroBoot recovery fixture').bytes_le)
        set_vdi_geometry(dest, SECTORS, 16, 63)
        subprocess.run([converter, 'compare', '-f', 'raw', '-F', 'vdi', raw, dest], check=True)


def main():
    exe = Path(shutil.which('qemu-system-i386') or 'qemu-system-i386').resolve(strict=True)
    bios = exe.parent.parent / 'share/seabios/bios-256k.bin'
    converter = shutil.which('qemu-img')
    if not converter:
        raise ValueError('qemu-img is required to package the VirtualBox disks')
    out = ROOT / 'build/mbr-review-test-recovery-package'
    prepare_output(out)
    bundle = out / 'RetroBoot-Sicherungsfestplatte.zip'
    with tempfile.TemporaryDirectory(dir=out.parent) as directory:
        work = Path(directory)
        files = {'Anleitung.txt': INSTRUCTIONS.replace('\n', '\r\n').encode('utf-8-sig')}
        reports = {}
        raw = None
        for lang, suffix, folder in LANGS:
            result = ROOT / 'build' / ('mbr-review-test-recovery' + suffix)
            report = json.loads((result / 'recovery-disk-results.json').read_bytes())
            check_build_inputs(report, ROOT)
            if any(sha256(result / n) != digest for n, digest in report['manual_media'].items()):
                raise ValueError('Changed exported disk pair: ' + lang)
            if raw and sha256(raw) != sha256(result / 'mbr-recovery.img'):
                raise ValueError('English and German recovery sectors differ')
            raw = result / 'mbr-recovery.img'
            files[folder + '/mbr-target.img'] = (result / 'mbr-target.img').read_bytes()
            reports[lang] = {c['name']: c for c in report['cases']}
        make_vdis(converter, raw, work)
        for name, _, _ in DISKS:
            files[name] = (work / name).read_bytes()
        stage = work / bundle.name
        with zipfile.ZipFile(stage, 'x') as archive:
            for name, data in files.items():
                item = zipfile.ZipInfo(name)
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item, data)

        unpacked = work / 'extract'
        with zipfile.ZipFile(stage) as archive:
            archive.extractall(unpacked)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        for lang, suffix, folder in LANGS:
            src = ROOT / 'build' / ('rescue' + suffix)
            manifest = json.loads((src / 'manifest.json').read_bytes())
            check_build_inputs(manifest, ROOT)
            boot = unpacked / folder / 'mbr-target.img'
            fixture = dict(binary=(src / 'mbr-target.bin').read_bytes(), memory=manifest['memory']['mbr-target'])
            for name, value, serial in DISKS:
                vdi = unpacked / name
                with vdi.open('rb') as stream:
                    stream.seek(392)
                    disk_id = uuid.UUID(bytes_le=stream.read(16))
                words = struct.unpack('<4I', disk_id.bytes_le)
                if str(disk_id) != value or f'VB{words[0]:08x}-{words[3]:08x}' != serial:
                    raise ValueError('Unexpected VirtualBox disk identity')
                case = 'approved-with-source-absent' if serial == BACKUP else 'approved-copy-foreign-serial'
                lines = reports[lang][case]['transcript']
                verified = boot_fixture(exe, bios, fixture, work, boot, None, lang + '-' + case, lines,
                                        [(load_catalog(lang)['D_FIRST'], 'v', None, False)], [], [], readonly_start=True,
                                        recovery_disk=vdi, recovery_identity=(MODEL, serial), recovery_format='vdi')
                if verified['ide_read_lbas'] != reports[lang][case]['ide_read_lbas']:
                    raise ValueError('Packaged VDI verification accessed different sectors')
        if any((unpacked / name).read_bytes() != data for name, data in files.items()):
            raise ValueError('Read-only verification modified a delivered file')
        stage.replace(bundle)
    print(f'Four verified boots: {bundle.name} {sha256(bundle)}')


if __name__ == '__main__':
    main()
