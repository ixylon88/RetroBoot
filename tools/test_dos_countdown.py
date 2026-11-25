"""Cold-boot the shipped VDI and check the exact writes issued by the F9 menu."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
from unittest.mock import patch
import uuid
import zipfile

import config_records
from build_dos_kit import build
from build_hdd import ROOT
from package_mbr_recovery import set_fixture_identity
from prepare_dos_disk import SECTOR, make_disk, read_sector
from prepared_countdown import JOURNAL, STATE, change_countdown, inspect, management_files, recover_countdown
from setup_toolchain import sha256
from test_menu import Qmp, screen_rows, wait_marker
from test_prepared_dos import original_fixture
from ui_text import LANGUAGES, load_catalog, output_name


def package(work, directory, language):
    source, raw = work / 'source.img', work / 'prepared.img'
    original_fixture(source, directory)
    kit = build(language)
    with patch.object(uuid, 'uuid4', return_value=uuid.UUID(bytes=config_records.FIXTURE_MEDIA_ID)):
        make_disk(source, raw, kit, 0)
    disk = work / 'RetroBoot-F9.vdi'
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', raw, disk], check=True)
    disk_id = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/ixylon88/RetroBoot/fixtures/F9-' + language)
    set_fixture_identity(disk, str(disk_id), raw.stat().st_size // SECTOR)
    name = 'RetroBoot-Countdown-' + ('Menue-DE' if language == 'de' else 'Menu-EN') + '.zip'
    bundle = work / name
    with zipfile.ZipFile(bundle, 'x') as archive:
        archive.writestr(zipfile.ZipInfo(disk.name), disk.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        delivered = Path(archive.extract(disk.name, work / 'extracted'))
    compare(delivered, raw)
    return bundle, delivered, raw


def compare(vdi, raw):
    subprocess.run(['qemu-img', 'compare', '-q', '-f', 'vdi', '-F', 'raw', vdi, raw], check=True)


class Menu:
    def __init__(self, process, work, log):
        self.process, self.work, self.log = process, work, log
        self.qmp, self.serial = Qmp(process), 0
        self.wait('RB MENU READY')

    def wait(self, marker):
        return wait_marker(self.process, self.log, marker)

    def key(self, name, view):
        self.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': name}], 'hold-time': 20})
        self.serial += 1
        self.wait(f'RB MENU {self.serial:04X} view={view:04X} ')

    def memory(self, address, size):
        path = self.work / 'ram.bin'
        self.qmp.call('pmemsave', {'val': address, 'size': size, 'filename': str(path)})
        return path.read_bytes()

    def screen(self):
        return screen_rows(self.memory(0xb8000, 4000))

    def expect(self, text):
        if not any(text in row for row in self.screen()):
            raise ValueError(f'{text!r} missing from VGA\n' + '\n'.join(self.screen()))

    def value(self, row, value):
        if self.screen()[row][30:33].strip() != str(value):
            raise ValueError(f'Expected {value} on row {row}')

    def open(self):
        self.key('f9', 13)
        self.wait('RB TIMER OPEN 0000')

    def save(self, status, message):
        self.key('ret', 14)
        self.wait(f'RB TIMER SAVE {status:04X}')
        self.expect(message)


@contextmanager
def boot(qemu, bios, work, disk, case, writes=(), fault=''):
    log, trace = work / (case + '.log'), work / (case + '.trace')
    location = disk
    if fault:
        conf = work / (case + '.conf')
        conf.write_text(fault)
        location = f'blkdebug:{conf}:{disk}'
    fmt = 'vdi' if disk.suffix == '.vdi' else 'raw'
    cmd = [qemu, '-L', str(bios.parent), '-bios', str(bios), '-machine', 'pc-i440fx-8.2,accel=tcg',
           '-cpu', '486', '-m', '16', '-nodefaults', '-vga', 'std', '-display', 'none', '-nic', 'none',
           '-serial', 'none', '-monitor', 'none', '-boot', 'c', '-qmp', 'stdio', '-no-reboot',
           '-debugcon', 'file:' + str(log), '-global', 'isa-debugcon.iobase=0xe9',
           '-drive', f'if=none,id=d0,media=disk,format={fmt},file={location},werror=report,rerror=report',
           '-device', 'ide-hd,drive=d0,bus=ide.0,unit=0,lcyls=255,lheads=16,lsecs=63',
           '-trace', f'events={work / "events.txt"},file={trace}']
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as process:
        try:
            menu = Menu(process, work, log)
            yield menu
            if menu.memory(0x1e000, 2) != b'\x5a\xa5':
                raise ValueError('Firmware stack guard overwritten')
            menu.qmp.call('quit')
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
    bus = trace.read_text()
    if 'ide_sector_read sector=0 nsectors=1' not in bus:
        raise ValueError('Missing IDE boot trace')
    transfers = [(int(a), int(b)) for a, b in re.findall(r'ide_sector_write sector=(\d+) nsectors=(\d+)', bus)]
    if transfers != [(lba, 1) for lba in writes] or bus.count('ide_sector_write') != len(writes):
        raise ValueError(f'{case}: unexpected IDE writes {transfers}')
    if not writes and 'blk_co_pwritev' in bus:
        raise ValueError(f'{case}: unexpected block write')
    print(f'{case}: passed, {len(writes)} guest writes', flush=True)


def run(language, qemu, bios):
    ui = load_catalog(language)
    directory = ROOT / 'build' / output_name('hdd', language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        bundle, vdi, raw = package(work, directory, language)
        with raw.open('rb') as disk:
            baseline = inspect(disk)
        a, b = baseline.lbas
        expected = work / 'expected.img'
        shutil.copyfile(raw, expected)

        def start(case, writes=(), image=vdi, fault=''):
            return boot(qemu, bios, work, image, case, writes, fault)

        with start('cancel-and-noop') as menu:
            menu.expect(ui['TIMER_HELP'])
            menu.open()
            menu.value(8, 0)
            menu.expect(f'RBCFG.B   0x{b:08X}')
            menu.key('end', 13)
            menu.key('right', 13)
            menu.value(10, 60)
            menu.key('esc', 0)
            menu.open()
            menu.key('left', 13)
            menu.value(10, 0)
            menu.save(7, ui['TIMER_UNCHANGED'])
        compare(vdi, raw)
        with start('save-three', [b]) as menu:
            menu.open()
            for _ in range(3):
                menu.key('right', 13)
            menu.value(10, 3)
            menu.save(0, ui['TIMER_OK'])
            menu.value(10, 3)
            menu.key('esc', 0)
            menu.expect(ui['AUTO_OFF'])
        with expected.open('r+b') as disk:
            change_countdown(disk, 3, language)
        compare(vdi, expected)
        with start('cold-automatic') as menu:
            menu.expect(ui['DOS_TIMER'])
            menu.wait('RB HANDOFF PASS')
        with start('disable', [a]) as menu:
            menu.open()
            menu.expect(f'RBCFG.A   0x{a:08X}')
            menu.value(8, 3)
            menu.key('home', 13)
            menu.save(0, ui['TIMER_OK'])
        with start('cold-disabled') as menu:
            time.sleep(3.2)
            menu.expect(ui['AUTO_OFF'])
            menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}]})
            menu.wait('RB HANDOFF PASS')
        with expected.open('r+b') as disk:
            change_countdown(disk, 0, language)
        compare(vdi, expected)

        # Interrupt the actual second guest update before its CRC reaches disk.
        torn = work / 'torn.img'
        subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', vdi, torn], check=True)
        with torn.open('r+b') as disk:
            disk.seek(a * SECTOR + 40)
            disk.write(baseline.copies[0][40:])
        with start('torn-copy', image=torn) as menu:
            menu.expect(ui['NO_PROFILES'])
            if any(ui['TIMER_HELP'] in row for row in menu.screen()):
                raise ValueError('Damaged configuration offered the writer')
        with torn.open('r+b') as disk, patch('builtins.input', return_value='j' if language == 'de' else 'y'):
            recover_countdown(disk, language)
            fixed = inspect(disk)
        with expected.open('r+b') as disk:
            disk.seek(a * SECTOR)
            disk.write(fixed.copies[1])
        if sha256(expected) != sha256(torn) or fixed.copies[0][38] != 3:
            raise ValueError('Recovery did not restore exactly the last completed delay')

        def set_generation(disk, lba, generation):
            record = bytearray(read_sector(disk, lba))
            struct.pack_into('<I', record, 16, generation)
            disk.seek(lba * SECTOR)
            disk.write(config_records.seal(record))

        changed = work / 'changed.img'
        shutil.copyfile(raw, changed)
        with start('changed-after-review', image=changed) as menu:
            menu.open()
            menu.key('right', 13)
            menu.qmp.call('stop')
            with changed.open('r+b') as disk:
                change_countdown(disk, 2, language)
            changed_hash = sha256(changed)
            menu.qmp.call('cont')
            menu.save(3, ui['TIMER_CHANGED'])
        if sha256(changed) != changed_hash:
            raise ValueError('A stale review overwrote the intervening update')
        with changed.open('r+b') as disk:
            set_generation(disk, a, 0xffffffff)
        with start('generation-gap', image=changed) as menu:
            menu.key('f9', 14)
            menu.expect(ui['TIMER_RECORDS'])
        with changed.open('r+b') as disk:
            set_generation(disk, b, 0xfffffffe)
        with start('generation-limit', image=changed) as menu:
            menu.open()
            menu.key('right', 13)
            menu.save(4, ui['TIMER_FULL'])
            menu.key('esc', 0)
            menu.open()
            menu.save(7, ui['TIMER_UNCHANGED'])

        # A directory timestamp changes none of the file LBAs or record bytes.
        # The review still expires. Separately damage the mirrored FAT, the DOS
        # VBR, an installation record and an idle journal before opening F9.
        with raw.open('rb') as disk:
            mbr = read_sector(disk, 0)
            admin = struct.unpack_from('<I', mbr, 436)[0]
            dos = struct.unpack_from('<I', mbr, 454)[0]
            volume = read_sector(disk, admin)
            spf = struct.unpack_from('<H', volume, 22)[0]
            root = admin + 1 + 2 * spf
            files = management_files(disk, admin, struct.unpack_from('<I', volume, 32)[0])

        def flip(lba, offset):
            with changed.open('r+b') as disk:
                record = bytearray(read_sector(disk, lba))
                record[offset] ^= 1
                disk.seek(lba * SECTOR)
                disk.write(record)

        shutil.copyfile(raw, changed)
        with start('allocation-changed-after-review', image=changed) as menu:
            menu.open()
            menu.key('right', 13)
            menu.qmp.call('stop')
            flip(root, 22)
            menu.qmp.call('cont')
            menu.save(3, ui['TIMER_CHANGED'])
        for case, lba, offset in (('fat-mismatch', admin + 2 * spf, 510), ('vbr-mismatch', dos, 509),
                                  ('state-mismatch', files[STATE[1]][0], 508),
                                  ('journal-mismatch', files[JOURNAL[0]][0], 508)):
            shutil.copyfile(raw, changed)
            flip(lba, offset)
            with start(case, image=changed) as menu:
                if case == 'state-mismatch':
                    menu.key('f9', 0)
                    menu.expect(ui['STATE_DEGRADED'])
                else:
                    menu.key('f9', 14)
                    menu.expect(ui['TIMER_DISK'])

        # Fail the write, then separately fail reading the untouched peer after
        # a successful write. Neither path may retry Enter or report success.
        for case, status, message, fault in (
            ('write-error', 5, 'TIMER_WRITE', f'[inject-error]\nevent = "write_aio"\niotype = "write"\nsector = "{b}"\nerrno = "5"\n'),
            ('readback-error', 6, 'TIMER_READBACK', '[set-state]\nevent = "write_aio"\nnew_state = "2"\n'
                f'[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nsector = "{a}"\nerrno = "5"\n')):
            shutil.copyfile(raw, changed)
            with start(case, [b], image=changed, fault=fault) as menu:
                menu.open()
                menu.key('right', 13)
                menu.save(status, ui[message])
                menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}]})
                menu.key('esc', 0)
            shutil.copyfile(raw, expected)
            if status == 6:
                with expected.open('r+b') as disk:
                    change_countdown(disk, 1, language)
            if sha256(changed) != sha256(expected):
                raise ValueError(f'{case}: unexpected on-disk result')

        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
