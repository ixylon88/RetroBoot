"""Exercise the released installation-state tool and both cold-boot outcomes."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
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
from prepared_records import STATE, read_records
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from test_prepared_dos import original_fixture
from ui_text import LANGUAGES, load_catalog, output_name


def package(work, directory, language):
    source = work / 'original.img'
    fixture = work / 'RetroBoot-Status-Test.img'
    kit = build(language)
    original_fixture(source, directory)
    with patch.object(uuid, 'uuid4', return_value=uuid.UUID(bytes=config_records.FIXTURE_MEDIA_ID)):
        make_disk(source, fixture, kit, 2)
    name = 'RetroBoot-Startsperre-DE.zip' if language == 'de' else 'RetroBoot-Boot-Hold-EN.zip'
    bundle = work / name
    with zipfile.ZipFile(kit.with_suffix('.zip')) as release, zipfile.ZipFile(bundle, 'x') as archive:
        for entry in (kit.name, 'RetroBoot-Recovery-Required.cmd'):
            archive.writestr(zipfile.ZipInfo(entry), release.read(entry), compress_type=zipfile.ZIP_DEFLATED)
        info = zipfile.ZipInfo(fixture.name)
        info.compress_type = zipfile.ZIP_DEFLATED
        with archive.open(info, 'w') as out, fixture.open('rb') as disk:
            shutil.copyfileobj(disk, out)
    delivered = work / 'release'
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(delivered)
    return bundle, delivered / kit.name, delivered / fixture.name


def run(language, qemu, bios):
    directory = ROOT / 'build' / output_name('hdd', language)
    ui = load_catalog(language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        bundle, kit, source = package(work, directory, language)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        original_hash = sha256(source)
        blocked = work / 'blocked.img'
        consent = 'j' if language == 'de' else 'y'

        def run_kit(disk, output, reply, check=True):
            return subprocess.run([sys.executable, str(kit), str(disk), '--require-recovery', '--output', str(output)],
                                  input=reply + '\n', capture_output=True, text=True, check=check)

        if run_kit(source, blocked, '', False).returncode == 0 or blocked.exists():
            raise ValueError('Cancellation published a disk')
        report = run_kit(source, blocked, consent).stdout
        with source.open('rb') as disk:
            records = read_records(disk)
        target = records.files[STATE[1]][0]
        for field in ('RBSTATE.A', 'RBSTATE.B', f'LBA 0x{target:08X}', 'ready', 'recovery_required'):
            if field not in report:
                raise ValueError('Incomplete installation-state review: ' + field)
        expected = work / 'expected.img'
        shutil.copyfile(source, expected)
        # Independent oracle for the complete output of the released CLI.
        intended = bytearray(records.state[0])
        intended[16:20] = (2).to_bytes(4, 'little')
        intended[83:88] = b'\x07' + bytes(4)
        intended = config_records.seal(intended)
        with expected.open('r+b') as disk:
            disk.seek(target * SECTOR)
            disk.write(intended)
        if sha256(blocked) != sha256(expected) or sha256(source) != original_hash:
            raise ValueError('Unexpected installation update outside the inactive state record')
        noop = work / 'noop.img'
        run_kit(blocked, noop, '')
        if noop.exists():
            raise ValueError('An already blocked installation produced another disk')

        with boot(qemu, bios, work, source, 'state-original') as menu:
            menu.expect(ui['DOS_TIMER'])
            menu.wait('RB HANDOFF PASS')
        vdi = work / 'blocked.vdi'
        subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', blocked, vdi], check=True)
        disk_id = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/ixylon88/RetroBoot/fixtures/state-' + language)
        set_fixture_identity(vdi, str(disk_id), records.geometry[0])
        compare(vdi, blocked)

        def check_blocked(menu, damaged=False, wait=False):
            menu.expect(ui['STATE_DEGRADED' if damaged else 'DOS_RECOVERY_REQUIRED'])
            menu.expect(ui['AUTO_OFF'])
            if any('MS-DOS 6.22' in row or ui['TIMER_HELP'] in row for row in menu.screen()):
                raise ValueError('Blocked OS entry or countdown writer offered')
            if wait:
                time.sleep(2.4)
                menu.expect(ui['AUTO_OFF'])
            menu.key('f9', 0)
            menu.key('ret', 1)  # Only diagnostics can be selected in this menu.
            menu.key('f6', 7)
            if damaged:
                menu.wait('RB STATE proof=0003')
            else:
                menu.wait('RB STATE proof=0007 detail=0007')
                rows = menu.screen()
                if rows[9][29:41] != '0x00000002 B' or rows[13][29:44] != '0x0007 / 0x0007':
                    raise ValueError('F6 did not show the selected recovery generation and phase')
            if 'RB HANDOFF' in menu.log.read_text() or 'RB DOS REJECT' in menu.log.read_text():
                raise ValueError('Blocked system reached the DOS start path')

        for case in ('state-blocked', 'state-blocked-cold'):
            with boot(qemu, bios, work, vdi, case) as menu:
                check_blocked(menu, wait=True)
        compare(vdi, blocked)
        # Preserve the old CRC after the new phase and generation have reached disk.
        torn = work / 'torn.img'
        shutil.copyfile(blocked, torn)
        with torn.open('r+b') as disk:
            disk.seek(target * SECTOR + 508)
            disk.write(records.state[1][508:])
        with boot(qemu, bios, work, torn, 'state-torn') as menu:
            check_blocked(menu, damaged=True)
        torn_hash = sha256(torn)
        repaired = work / 'repaired.img'
        run_kit(torn, repaired, consent)
        if sha256(torn) != torn_hash or sha256(repaired) != sha256(expected):
            raise ValueError('Recovery did not complete the exact confirmed hold')
        with boot(qemu, bios, work, repaired, 'state-recovered') as menu:
            check_blocked(menu)

        # Change only the test disk's state while a previously valid selection
        # is displayed. Both Enter and the running timer must recheck at handoff.
        for case in ('state-stale-enter', 'state-stale-timer'):
            stale = work / (case + '.img')
            shutil.copyfile(source, stale)
            with boot(qemu, bios, work, stale, case) as menu:
                menu.expect(ui['DOS_TIMER'])
                menu.qmp.call('stop')
                with stale.open('r+b') as disk, blocked.open('rb') as new:
                    disk.seek(target * SECTOR)
                    disk.write(read_sector(new, target))
                menu.qmp.call('cont')
                if case.endswith('enter'):
                    menu.key('ret', 12)
                menu.wait('RB DOS REJECT 0002')
                if 'RB HANDOFF' in menu.log.read_text():
                    raise ValueError('A stale DOS selection executed')
        if sha256(source) != original_hash:
            raise ValueError('Released input image changed')
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
