"""Cold-boot the released verification fixture and trace its single state write."""
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
import zlib

import config_records
from build_dos_kit import build
from build_hdd import ROOT
from package_mbr_recovery import set_fixture_identity
from prepare_dos_disk import SECTOR, make_disk, read_sector
from prepared_records import CONFIG, JOURNAL, STATE, read_records
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from test_prepared_dos import original_fixture
from ui_text import LANGUAGES, load_catalog, output_name


def block_copy(kit, source, output, language):
    subprocess.run([sys.executable, str(kit), str(source), '--require-recovery', '--output', str(output)],
                   input=('j' if language == 'de' else 'y') + '\n', text=True, check=True, capture_output=True)


def package(work, directory, language):
    source, ready, held = (work / name for name in ('original.img', 'ready.img', 'held.img'))
    vbr, entry = original_fixture(source, directory)
    kit = build(language)
    with patch.object(uuid, 'uuid4', return_value=uuid.UUID(bytes=config_records.FIXTURE_MEDIA_ID)):
        make_disk(source, ready, kit, 2)
    block_copy(kit, ready, held, language)
    image = work / 'RetroBoot-Verify.vdi'
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', held, image], check=True)
    identity = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/ixylon88/RetroBoot/fixtures/verification-' + language)
    set_fixture_identity(image, str(identity), held.stat().st_size // SECTOR)
    name = 'RetroBoot-Pruefstart-DE.zip' if language == 'de' else 'RetroBoot-Verification-Boot-EN.zip'
    bundle = work / name
    with zipfile.ZipFile(bundle, 'x') as archive:
        archive.writestr(zipfile.ZipInfo(image.name), image.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        delivered = Path(archive.extract(image.name, work / 'delivered'))
    compare(delivered, held)
    return bundle, delivered, held, kit, vbr, entry


def state_sector(source, generation, phase):
    record = bytearray(source)
    struct.pack_into('<I', record, 16, generation)
    record[83] = phase
    if phase != 6:
        record[84:88] = bytes(4)
    return config_records.seal(record)


def put(path, lba, data):
    with path.open('r+b') as disk:
        disk.seek(lba * SECTOR)
        disk.write(data)


def run(language, qemu, bios):
    ui = load_catalog(language)
    directory = ROOT / 'build' / output_name('hdd', language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        bundle, shipped, held, kit, vbr, entry = package(work, directory, language)
        with held.open('rb') as disk:
            records = read_records(disk)
            admin = records.binding['admin_start']
            spf = struct.unpack_from('<H', read_sector(disk, admin), 22)[0]
        a, b = [records.files[name][0] for name in STATE]
        ready, recovery = records.state
        pending = state_sector(recovery, 3, 5)
        expected, changed = work / 'expected.img', work / 'changed.img'
        shutil.copyfile(held, expected)
        put(expected, a, pending)

        def start(case, image=shipped, writes=(), **kwargs):
            return boot(qemu, bios, work, image, case, writes, **kwargs)

        def review(menu, slot=0):
            menu.expect(ui['DOS_RECOVERY_REQUIRED'])
            menu.expect(ui['TRIAL_HELP'])
            menu.key('v', 15)
            menu.wait('RB TRIAL OPEN 0000')
            menu.expect(ui['TRIAL_EFFECT'])
            menu.expect(f'RBSTATE.{"AB"[slot]}  0x{(a, b)[slot]:08X}')
            menu.expect('0x00000002 -> 0x00000003')
            menu.expect(f'0x{zlib.crc32(vbr):08X}')

        def confirm(menu):
            menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 20})
            menu.wait('RB HANDOFF PASS')
            if menu.memory(0x7c00, 512) != vbr or menu.memory(0x800, 16) != entry:
                raise ValueError('The destination VBR or primary entry changed during the transfer')

        def expect_blocked(menu, pending_state=True):
            menu.expect(ui['TRIAL_PENDING' if pending_state else 'STATE_DEGRADED'])
            menu.expect(ui['AUTO_OFF'])
            if any('MS-DOS 6.22' in row or ui['TRIAL_HELP'] in row or ui['TIMER_HELP'] in row for row in menu.screen()):
                raise ValueError('A pending or degraded installation offered a normal or verification boot')
            menu.key('v', 0)
            menu.key('f9', 0)
            menu.key('ret', 1)
            menu.key('f6', 7)
            menu.wait('RB STATE proof=0007 detail=0005' if pending_state else 'RB STATE proof=0003')
            if pending_state:
                menu.expect('0x00000003 A')
                menu.expect('0x0007 / 0x0005')
            if 'RB HANDOFF' in menu.log.read_text() or 'RB TRIAL OPEN' in menu.log.read_text():
                raise ValueError('A previously consumed or damaged trial was reachable')

        with start('trial-cancel') as menu:
            time.sleep(2.4)
            menu.expect(ui['AUTO_OFF'])
            menu.key('ret', 1)
            menu.key('esc', 0)
            review(menu)
            menu.key('esc', 0)
            menu.expect(ui['TRIAL_HELP'])
        compare(shipped, held)
        with start('trial-confirm', writes=[a]) as menu:
            review(menu)
            confirm(menu)
        compare(shipped, expected)
        with start('trial-cold') as menu:
            time.sleep(2.4)
            expect_blocked(menu)
        compare(shipped, expected)

        # Swapping the physical copies must change the destination, not the transfer.
        shutil.copyfile(held, changed)
        put(changed, a, recovery)
        put(changed, b, ready)
        with start('trial-other-slot', changed, [b]) as menu:
            review(menu, 1)
            confirm(menu)
        swapped = work / 'swapped.img'
        shutil.copyfile(held, swapped)
        put(swapped, a, recovery)
        put(swapped, b, pending)
        if sha256(changed) != sha256(swapped):
            raise ValueError('Unexpected change on the reversed physical pair')

        def flip(lba, offset):
            with changed.open('rb') as disk:
                sector = bytearray(read_sector(disk, lba))
            sector[offset] ^= 1
            put(changed, lba, sector)

        config_a, config_b = (records.files[name][0] for name in CONFIG)
        def edited_dword(record, offset, value):
            updated = bytearray(record)
            struct.pack_into('<I', updated, offset, value)
            return config_records.seal(updated)

        def exhaust_generation():
            put(changed, a, state_sector(ready, 0xfffffffe, 6))
            put(changed, b, state_sector(recovery, 0xffffffff, 7))

        dos_lba = records.target['start']
        # A valid countdown update on the other configuration copy must also
        # expire an open state review.
        cfg = bytearray(records.config[1])
        struct.pack_into('<I', cfg, 16, 2)
        cfg[38] = 4
        cfg = config_records.seal(cfg)
        for case, alter in (
            ('vbr', lambda: flip(dos_lba, 509)),
            ('directory', lambda: flip(admin + 1 + 2 * spf, 22)),
            ('config', lambda: put(changed, config_b, cfg)),
            ('state', lambda: put(changed, a, recovery)),
            ('journal', lambda: flip(records.files[JOURNAL[0]][0], 508)),
        ):
            shutil.copyfile(held, changed)
            with start('trial-stale-' + case, changed) as menu:
                review(menu)
                menu.qmp.call('stop')
                alter()
                intervening = sha256(changed)
                menu.qmp.call('cont')
                menu.key('ret', 16)
                menu.wait('RB TRIAL REJECT 0003')
                menu.expect(ui['TRIAL_CHANGED'])
            if sha256(changed) != intervening:
                raise ValueError('Stale ' + case + ' review overwrote an intervening change')

        for case, code, message, heads, alter in (
            ('no-ready', 8, 'TRIAL_HISTORY', 16, lambda: put(changed, a, recovery)),
            ('vbr-mismatch', 9, 'TRIAL_VBR', 16, lambda: flip(dos_lba, 509)),
            ('geometry', 10, 'DOS_GEOMETRY', 32, lambda: None),
            ('exhausted', 4, 'TRIAL_FULL', 16, exhaust_generation),
            ('foreign-ready', 8, 'TRIAL_HISTORY', 16, lambda: put(changed, a, edited_dword(ready, 64, 0x12345678))),
            ('foreign-hold', 8, 'TRIAL_HISTORY', 16, lambda: put(changed, b, edited_dword(recovery, 64, 0x12345678))),
            ('state-gap', 8, 'TRIAL_HISTORY', 16, lambda: put(changed, b, state_sector(recovery, 3, 7))),
            ('fat-mismatch', 1, 'TIMER_DISK', 16, lambda: flip(admin + 2 * spf, 510)),
            ('config-gap', 1, 'TIMER_DISK', 16, lambda: put(changed, config_a, edited_dword(records.config[0], 16, 4))),
        ):
            shutil.copyfile(held, changed)
            alter()
            with start('trial-' + case, changed, heads=heads) as menu:
                menu.key('v', 16)
                menu.wait(f'RB TRIAL OPEN {code:04X}')
                menu.expect(ui[message])

        write_error = f'[inject-error]\nevent = "write_aio"\niotype = "write"\nsector = "{a}"\nerrno = "5"\n'
        read_error = ('[set-state]\nevent = "write_aio"\nnew_state = "2"\n'
                      f'[inject-error]\nevent = "read_aio"\niotype = "read"\nstate = "2"\nsector = "{b}"\nerrno = "5"\n')
        for case, code, fault, disk_result in (
            ('write-error', 5, write_error, held), ('readback-error', 6, read_error, expected),
        ):
            shutil.copyfile(held, changed)
            with start('trial-' + case, changed, [a], fault=fault) as menu:
                review(menu)
                menu.key('ret', 16)
                menu.wait(f'RB TRIAL REJECT {code:04X}')
                menu.expect(ui['TRIAL_IO'])
                menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}]})
                menu.key('esc', 0)
                if 'RB HANDOFF' in menu.log.read_text():
                    raise ValueError('An uncertain state write reached the boot sector')
            if sha256(changed) != sha256(disk_result):
                raise ValueError('Unexpected result after ' + case)

        # Tear the CRC in the actual guest-written sector and recover on a new copy.
        torn, repaired = work / 'torn.img', work / 'repaired.img'
        subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', shipped, torn], check=True)
        put(torn, a, pending[:508] + ready[508:])
        with start('trial-torn', torn) as menu:
            expect_blocked(menu, False)
        block_copy(kit, torn, repaired, language)
        shutil.copyfile(held, changed)
        put(changed, a, recovery)
        if sha256(repaired) != sha256(changed):
            raise ValueError('External recovery of a torn trial wrote outside its damaged peer')
        with start('trial-repaired', repaired) as menu:
            menu.key('v', 16)
            menu.expect(ui['TRIAL_HISTORY'])
        reheld = work / 'reheld.img'
        block_copy(kit, expected, reheld, language)
        shutil.copyfile(expected, changed)
        put(changed, b, state_sector(pending, 4, 7))
        if sha256(reheld) != sha256(changed):
            raise ValueError('External recovery of a complete trial did not preserve the pending record')
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
