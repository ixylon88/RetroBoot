"""Build the bilingual VirtualBox kit and boot the exact extracted VDI files."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from package_mbr_recovery import LANGS, set_fixture_identity
from test_backup_disk import (CAPACITY, DATA, PASS, RECOVERY, SOURCE, boot_case, disk,
                              expected_recovery, load_catalog, provision, wire, write_fixture)

SYSTEM = 'RB73-System.vdi'
BACKUP = 'RB73-Sicherung.vdi'
GUID = ('73737373-d413-4b6c-a375-146111111111', '74747474-d413-4b6c-a375-146122222222')
README = """RetroBoot - Metadatensicherung / Metadata backup

Deutsch
1. ZIP entpacken. In der ausgeschalteten BIOS-Test-VM RB73-System.vdi als
   primären IDE-Master (Port 0, Gerät 0) und RB73-Sicherung.vdi als sekundären
   IDE-Master (Port 1, Gerät 0) anschließen. Beide sind vorbereitete Testplatten.
2. Deutsch/backup-disk.img in Laufwerk A einlegen, von A starten und S drücken.
   Nach der Meldung „Sicherung auf der Sicherungsfestplatte abgeschlossen.“
   erscheinen 45 geprüfte Sektoren, MBR-Revision 2 und RB BACKUP DISK PASS.
3. VM ausschalten. RB73-System.vdi vom Controller abkoppeln. RB73-Sicherung.vdi
   und die Startdiskette an ihren Anschlüssen lassen. Von A starten und V drücken.
   Erwartet: „Sicherung von der Sicherungsfestplatte gelesen.“, „Geprüfte Sektoren 45“,
   „Freigegebene MBR-Revision 2“ und RB BACKUP DISK PASS.
Die Sicherung umfasst Start- und Verwaltungsdaten. Die Testplatten enthalten kein
installiertes Betriebssystem. Eine bereits abgeschlossene Sicherung bleibt belegt.

English
1. Extract the ZIP. With the BIOS test VM off, attach RB73-System.vdi as primary
   IDE master (port 0, device 0) and RB73-Sicherung.vdi as secondary IDE master
   (port 1, device 0). Both are prepared test disks.
2. Boot English/backup-disk.img in drive A and press S. Expect “Backup published
   on the recovery disk.”, 45 verified sectors, MBR revision 2 and RB BACKUP DISK PASS.
3. Power off. Detach RB73-System.vdi from the controller. Leave the recovery disk
   and boot floppy in place. Boot from A and press V. Expect “Backup read from the
   recovery disk.”, “Verified sectors 45”, “Approved MBR revision 2” and RB BACKUP DISK PASS.
The backup covers boot and management metadata. The test disks contain no installed
operating system. A completed backup occupies its slot permanently.
"""


def make_vdi(converter, source, dest, guid, count, serial):
    subprocess.run([converter, 'convert', '-f', 'raw', '-O', 'vdi', source, dest], check=True)
    set_fixture_identity(dest, guid, count)
    with dest.open('rb') as stream:
        stream.seek(392)
        words = struct.unpack('<4I', stream.read(16))
    if f'VB{words[0]:08x}-{words[3]:08x}' != serial:
        raise ValueError('VDI creation UUID does not match the enrolled ATA serial')
    subprocess.run([converter, 'compare', '-f', 'raw', '-F', 'vdi', source, dest], check=True)


def main():
    converter = shutil.which('qemu-img')
    exe = Path(shutil.which('qemu-system-i386')).resolve()
    bios = exe.parent.parent/'share/seabios/bios-256k.bin'
    out = ROOT/'build/backup-disk-kit'
    prepare_output(out)
    data = wire()
    with tempfile.TemporaryDirectory(dir=out) as directory:
        work = Path(directory)
        raw = work/'system.raw'
        size, extents = disk()
        write_fixture(raw, size, extents)
        files = {'Anleitung.txt': README.replace('\n', '\r\n').encode('utf-8-sig')}
        blank = None
        for lang, suffix, folder in LANGS:
            src = ROOT/'build'/('rescue'+suffix)
            report = json.loads((ROOT/'build'/('backup-disk-test-'+lang)/'results.json').read_bytes())
            manifest = json.loads((src/'manifest.json').read_bytes())
            check_build_inputs(report, ROOT)
            check_build_inputs(manifest, ROOT)
            if sha256(src/'backup-disk.img') != manifest['artifacts']['backup-disk.img']['sha256']:
                raise ValueError('Changed localized boot image')
            boot, disk_bytes = provision((src/'backup-disk.img').read_bytes())
            if blank is not None and disk_bytes != blank:
                raise ValueError('Localized fixtures disagree on the disk bytes')
            blank = disk_bytes
            files[folder+'/backup-disk.img'] = boot
        carrier = work/'recovery.raw'
        carrier.write_bytes(blank)
        for name, source, guid, count, serial in ((SYSTEM,raw,GUID[0],size//512,SOURCE),
                                                  (BACKUP,carrier,GUID[1],CAPACITY,RECOVERY)):
            dest = work/name
            make_vdi(converter, source, dest, guid, count, serial)
            files[name] = dest.read_bytes()
        bundle = work/'RetroBoot-Metadatensicherung.zip'
        with zipfile.ZipFile(bundle,'x') as archive:
            for name, content in files.items():
                item = zipfile.ZipInfo(name)
                item.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(item,content)
        readback = work/'expected.raw'
        readback.write_bytes(expected_recovery(blank,data,True))
        (work/'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\n')
        for lang, suffix, folder in LANGS:
            dest = work/('extract-'+lang)
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(dest)
            src = ROOT/'build'/('rescue'+suffix)
            ui = load_catalog(lang)
            boot, system, rec = dest/folder/'backup-disk.img', dest/SYSTEM, dest/BACKUP
            trailer = [ui['VERIFY_COUNT']+'45',ui['STORE_REV']+'2',PASS]
            boot_case(exe,bios,src,work,boot,system,rec,ui,lang+'-save','s',
                      [ui['STORE_SAVE'],ui['STORE_DONE'],*trailer],input_format='vdi',recovery_format='vdi',
                      expected_writes=[*range(DATA,DATA+45),8])
            boot_case(exe,bios,src,work,boot,None,rec,ui,lang+'-cold','v',
                      [ui['STORE_VERIFY'],ui['STORE_READ'],*trailer],recovery_format='vdi')
            subprocess.run([converter,'compare','-f','raw','-F','vdi',readback,rec],check=True)
            if boot.read_bytes()!=files[folder+'/backup-disk.img'] or system.read_bytes()!=files[SYSTEM]:
                raise ValueError('Changed packaged source disk or boot diskette')
        bundle.replace(out/bundle.name)
    print(f'Four verified packaged VDI boots: {out/bundle.name}')


if __name__ == '__main__':
    main()
