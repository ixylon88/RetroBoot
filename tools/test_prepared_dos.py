"""Exercise the released disk-copy kit and checked DOS menu with the owned T07 VBR."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

try:
    from .build_hdd import ROOT
    from .build_dos_kit import build
    from . import config_records
    from .handoff_fixtures import LBA, SECTORS, entry_bytes
    from .prepare_dos_disk import SECTOR, partition, read_sector
    from .setup_toolchain import sha256
    from .test_hdd import check_trace
    from .test_menu import Qmp, screen_rows, wait_marker
    from .ui_text import LANGUAGES, output_name
except ImportError:
    from build_hdd import ROOT
    from build_dos_kit import build
    import config_records
    from handoff_fixtures import LBA, SECTORS, entry_bytes
    from prepare_dos_disk import SECTOR, partition, read_sector
    from setup_toolchain import sha256
    from test_hdd import check_trace
    from test_menu import Qmp, screen_rows, wait_marker
    from ui_text import LANGUAGES, output_name


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
        for case in ('enter', 'timeout', 'cancel', 'changed-vbr', 'changed-mbr', 'wrong-geometry',
                     'stale-profile', 'changed-default'):
            image = prepared
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
                    if not any('MS-DOS 6.22' in row for row in screen_rows(memory(0xb8000,4000))):
                        raise ValueError('DOS entry missing from the VGA menu')
                    if case in ('stale-profile', 'changed-default'):
                        qmp.call('stop')
                        change_menu_record(image, case)
                        qmp.call('cont')
                    if case == 'cancel':
                        key('esc')
                        time.sleep(2.5)
                        if 'RB HANDOFF' in log.read_text():
                            raise ValueError('Esc failed to cancel the default boot')
                    if case not in ('timeout', 'changed-default'):
                        key('ret')
                    errors = {'changed-vbr':'0002', 'changed-mbr':'0006', 'wrong-geometry':'0007',
                              'stale-profile':'0001', 'changed-default':'0001'}
                    if case in errors:
                        wait_marker(p, log, 'RB DOS REJECT '+errors[case])
                        if 'RB HANDOFF' in log.read_text():
                            raise ValueError('Invalid target executed')
                    else:
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
        if sha256(source) != original_hash:
            raise ValueError('The original source disk changed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
