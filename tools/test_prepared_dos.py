"""Exercise the released disk-copy kit and checked DOS menu with the owned T07 VBR."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid
import zipfile

try:
    from .build_hdd import ROOT
    from .build_dos_kit import build
    from . import config_records
    from .handoff_fixtures import LBA, SECTORS, entry_bytes
    from .prepare_dos_disk import SECTOR, make_disk, partition, read_sector
    from .prepared_countdown import change_countdown, inspect
    from .setup_toolchain import sha256
    from .test_hdd import check_trace
    from .test_menu import Qmp, screen_rows, wait_marker
    from .ui_text import LANGUAGES, load_catalog, output_name
except ImportError:
    from build_hdd import ROOT
    from build_dos_kit import build
    import config_records
    from handoff_fixtures import LBA, SECTORS, entry_bytes
    from prepare_dos_disk import SECTOR, make_disk, partition, read_sector
    from prepared_countdown import change_countdown, inspect
    from setup_toolchain import sha256
    from test_hdd import check_trace
    from test_menu import Qmp, screen_rows, wait_marker
    from ui_text import LANGUAGES, load_catalog, output_name


def original_fixture(path, directory):
    # Instrumented independent boot sector. The root entries exercise the import
    # checks. They do not contain DOS and never serve as original-OS evidence.
    mbr = bytearray(512)
    raw_entry = bytearray(partition(6, LBA, SECTORS, LBA, 16, 63))
    raw_entry[0] = 0x80
    mbr[446:462] = raw_entry
    mbr[510:] = b'\x55\xaa'
    vbr = (directory/'handoff-vbr.bin').read_bytes()
    if vbr.count(entry_bytes()) != 1:
        raise ValueError('Missing register-check entry in T07 VBR')
    vbr = bytearray(vbr.replace(entry_bytes(), bytes(raw_entry)))
    struct.pack_into('<HH', vbr, 24, 63, 16)
    root = bytearray(512)
    for index, name in enumerate((b'IO      SYS', b'MSDOS   SYS', b'COMMAND COM')):
        offset = index * 32
        root[offset:offset+11] = name
        struct.pack_into('<HI', root, offset+26, index+2, 512)
    with path.open('xb') as f:
        f.truncate((LBA+SECTORS)*SECTOR)
        for lba, contents in ((0,mbr), (LBA,vbr), (LBA+41,root)):
            f.seek(lba*SECTOR)
            f.write(contents)
    return bytes(vbr), bytes(raw_entry)


def change_menu_record(path, case):
    with path.open('r+b') as disk:
        admin = struct.unpack_from('<I', read_sector(disk, 0), 436)[0]
        volume = read_sector(disk, admin)
        first = struct.unpack_from('<I', volume, 66)[0]
        for cluster in config_records.CLUSTERS:
            lba = first + (cluster - 2) * volume[13]
            cfg = bytearray(read_sector(disk, lba))
            if case == 'stale-profile':
                cfg[64+20] = ord('X')  # Rename the displayed entry.
            else:
                struct.pack_into('<I', cfg, 40, 0)  # Withdraw its default ID.
            disk.seek(lba * SECTOR)
            disk.write(config_records.seal(cfg))


def recovery_fixture(work, source, kit, language):
    image = work / 'RetroBoot-Countdown-Test.img'
    # Fixed identity only for the distributed, project-owned boot-sector fixture.
    with patch.object(uuid, 'uuid4', return_value=uuid.UUID(bytes=config_records.FIXTURE_MEDIA_ID)):
        make_disk(source, image, kit, 0)
    healthy_hash = sha256(image)
    with image.open('r+b') as disk:
        before = inspect(disk)
        change_countdown(disk, 1, language)
        # Power loss after the new generation and delay, before the new CRC.
        disk.seek(before.lbas[1] * SECTOR + 40)
        disk.write(before.copies[1][40:])
    damaged_hash = sha256(image)
    if damaged_hash == healthy_hash:
        raise ValueError('Ineffective interrupted countdown fixture')

    bundle = work / f'RetroBoot-Countdown-Recovery-{language.upper()}.zip'
    with zipfile.ZipFile(kit.with_suffix('.zip')) as release, zipfile.ZipFile(bundle, 'x') as archive:
        for name in ('RetroBoot-DOS.pyz', 'RetroBoot-Countdown-Recovery.cmd'):
            archive.writestr(zipfile.ZipInfo(name), release.read(name), compress_type=zipfile.ZIP_DEFLATED)
        info = zipfile.ZipInfo(image.name)
        info.compress_type = zipfile.ZIP_DEFLATED
        with archive.open(info, 'w') as output, image.open('rb') as raw:
            shutil.copyfileobj(raw, output)
    manual = work / 'manual'
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(manual)
    damaged = manual / image.name
    repaired = work / 'recovered.img'
    cmd = [sys.executable, str(manual / kit.name), str(damaged), '--recover-countdown', '--output', str(repaired)]
    cancelled = subprocess.run(cmd, input='\n', text=True, capture_output=True)
    if cancelled.returncode == 0 or repaired.exists():
        raise ValueError('Cancellation published a recovery output')
    consent = 'j' if language == 'de' else 'y'
    result = subprocess.run(cmd, input=consent + '\n', text=True, capture_output=True, check=True)
    for field in ('RBCFG.A', 'RBCFG.B', f'0x{before.lbas[1]:08X}', '0 s'):
        if field not in result.stdout:
            raise ValueError('Incomplete countdown recovery review: ' + field)
    if sha256(damaged) != damaged_hash or sha256(repaired) != healthy_hash:
        raise ValueError('Recovery must restore the exact healthy disk and preserve the packaged input')
    return bundle, damaged, repaired


def run(language, qemu, bios):
    kit = build(language)
    directory = ROOT / 'build' / output_name('hdd',language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        source, prepared = work/'source.img', work/'prepared.img'
        vbr, entry = original_fixture(source, directory)
        original_hash = sha256(source)
        subprocess.run([sys.executable, str(kit), str(source), '--output', str(prepared),
                        '--countdown', '2'], check=True)
        with source.open('rb') as a, prepared.open('rb') as b:
            a.seek(SECTOR)
            if read_sector(b, 0)[446:462] != entry:
                raise ValueError('DOS MBR entry changed')
            b.seek(SECTOR)
            while chunk := a.read(1024*1024):
                if chunk != b.read(len(chunk)):
                    raise ValueError('Original disk contents after sector zero changed')
        disabled, enabled = work/'disabled.img', work/'enabled.img'
        prepared_hash = sha256(prepared)
        subprocess.run([sys.executable, str(kit), str(prepared), '--output', str(disabled),
                        '--set-countdown'], input='0\n', text=True, check=True)
        subprocess.run([sys.executable, str(kit), str(disabled), '--output', str(enabled),
                        '--set-countdown', '1'], check=True)
        bundle, damaged, repaired = recovery_fixture(work, source, kit, language)
        catalog = load_catalog(language)
        images = {'countdown-off': disabled, 'countdown-on': enabled, 'recovery-blocked': damaged,
                  'recovery-restored': repaired, 'recovery-cold': repaired}
        timer_off = ('countdown-off', 'recovery-restored', 'recovery-cold')
        for case in ('enter', 'timeout', 'countdown-off', 'countdown-on', 'cancel',
                     'changed-vbr', 'changed-mbr', 'wrong-geometry', 'stale-profile', 'changed-default',
                     'recovery-blocked', 'recovery-restored', 'recovery-cold'):
            image = images.get(case, prepared)
            if case in ('changed-vbr','changed-mbr','stale-profile','changed-default'):
                image = work/(case+'.img')
                shutil.copyfile(prepared,image)
            if case in ('changed-vbr','changed-mbr'):
                with image.open('r+b') as f:
                    pos = LBA*SECTOR+509 if case == 'changed-vbr' else 447
                    f.seek(pos)
                    b = f.read(1)
                    f.seek(pos)
                    f.write(bytes([b[0]^1]))
            heads = 32 if case == 'wrong-geometry' else 16
            events = work/'events.txt'
            events.write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
            trace, log = work/(case+'.trace'), work/(case+'.log')
            cmd = [qemu,'-L',str(bios.parent),'-bios',str(bios),'-machine','pc-i440fx-8.2,accel=tcg',
                   '-cpu','486','-m','16','-nodefaults','-vga','std','-display','none','-nic','none',
                   '-serial','none','-monitor','none','-boot','c','-qmp','stdio','-no-reboot',
                   '-debugcon','file:'+str(log),'-global','isa-debugcon.iobase=0xe9',
                   '-drive',f'if=none,id=d0,media=disk,format=raw,snapshot=on,file={image}',
                   '-device',f'ide-hd,drive=d0,bus=ide.0,unit=0,lcyls=255,lheads={heads},lsecs=63',
                   '-trace',f'events={events},file={trace}']
            with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as p:
                try:
                    qmp = Qmp(p)
                    def key(name):
                        qmp.call('send-key', {'keys':[{'type':'qcode','data':name}], 'hold-time':30})
                    def memory(addr, size):
                        dump = work/'memory.bin'
                        qmp.call('pmemsave', {'val':addr,'size':size,'filename':str(dump)})
                        return dump.read_bytes()
                    wait_marker(p, log, 'RB MENU READY')
                    rows = screen_rows(memory(0xb8000,4000))
                    has_dos = any('MS-DOS 6.22' in row for row in rows)
                    if case == 'recovery-blocked':
                        if has_dos or not any(catalog['NO_PROFILES'] in row for row in rows):
                            raise ValueError('A damaged countdown copy enabled the DOS entry')
                    elif not has_dos:
                        raise ValueError('DOS entry missing from the VGA menu')
                    if case in timer_off or case == 'countdown-on':
                        message = catalog['AUTO_OFF' if case in timer_off else 'DOS_TIMER']
                        if not any(message in row for row in rows):
                            raise ValueError('Updated countdown missing from the cold-boot VGA menu')
                    if case in ('stale-profile', 'changed-default'):
                        qmp.call('stop')
                        change_menu_record(image, case)
                        qmp.call('cont')
                    if case == 'cancel':
                        key('esc')
                    if case == 'cancel' or case in timer_off:
                        time.sleep(2.5)
                        if 'RB HANDOFF' in log.read_text():
                            raise ValueError('Disabled countdown started the selection')
                    if case == 'recovery-blocked':
                        key('f5')
                        wait_marker(p, log, 'RB CONFIG status=0000 copies=00000004 source=0000 count=0001')
                    elif case not in ('timeout', 'changed-default', 'countdown-on'):
                        key('ret')
                    errors = {'changed-vbr':'0002', 'changed-mbr':'0006', 'wrong-geometry':'0007',
                              'stale-profile':'0001', 'changed-default':'0001'}
                    if case in errors:
                        wait_marker(p, log, 'RB DOS REJECT '+errors[case])
                        if 'RB HANDOFF' in log.read_text():
                            raise ValueError('Invalid target executed')
                    elif case != 'recovery-blocked':
                        wait_marker(p, log, 'RB HANDOFF PASS')
                        if memory(0x7c00,512) != vbr or memory(0x800,16) != entry:
                            raise ValueError('Target VBR or entry changed during transfer')
                    qmp.call('quit')
                    p.wait(timeout=5)
                finally:
                    if p.poll() is None:
                        p.kill()
            check_trace(trace.read_text())
            print(f'{language} prepared DOS menu: {case} passed', flush=True)
        if sha256(source) != original_hash or sha256(prepared) != prepared_hash:
            raise ValueError('A source disk changed')
        shutil.copyfile(bundle, directory / bundle.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
