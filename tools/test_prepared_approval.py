"""Exercise the released approval kit on the disk consumed by the verification-boot test."""
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

from prepare_dos_disk import SECTOR
from prepared_records import STATE, read_records
from setup_toolchain import sha256
from test_dos_countdown import boot, compare
from ui_text import load_catalog


def approval_kit(work, kit, reference, language):
    name = 'RetroBoot-DOS-Freigabe-DE.zip' if language == 'de' else 'RetroBoot-DOS-Approval-EN.zip'
    bundle = work / name
    launcher = 'RetroBoot-Confirm-Verification.cmd'
    with zipfile.ZipFile(kit.with_suffix('.zip')) as release, zipfile.ZipFile(bundle, 'x') as out:
        for item in (kit.name, launcher):
            out.writestr(zipfile.ZipInfo(item), release.read(item), compress_type=zipfile.ZIP_DEFLATED)
        info = zipfile.ZipInfo('RetroBoot-Reference.img')
        info.compress_type = zipfile.ZIP_DEFLATED
        with out.open(info, 'w') as dest, reference.open('rb') as source:
            shutil.copyfileobj(source, dest)
    delivery = work / 'approval-kit'
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(delivery)
    return bundle, delivery / kit.name, delivery / 'RetroBoot-Reference.img'


def check_approval(work, directory, kit, held, trial_vdi, language, qemu, bios):
    bundle, released, reference = approval_kit(work, kit, held, language)
    trial, approved, expected = (work / name for name in ('observed.img', 'approved.img', 'approved-expected.img'))
    subprocess.run(['qemu-img', 'convert', '-f', 'vdi', '-O', 'raw', trial_vdi, trial], check=True)
    trial_hash, reference_hash = sha256(trial), sha256(reference)
    ui = load_catalog(language)
    answer = 'J' if language == 'de' else 'Y'

    def run_cli(source, output, reply):
        return subprocess.run([sys.executable, str(released), str(source), '--confirm-verification', str(reference),
                               '--output', str(output)], input=reply + '\n', capture_output=True, text=True)

    if run_cli(trial, approved, '').returncode == 0 or approved.exists():
        raise ValueError('A cancelled approval published a disk')
    result = run_cli(trial, approved, answer)
    result.check_returncode()
    for field in ('MS-DOS 6.22', 'VBR CRC32', 'RBSTATE.A', 'RBSTATE.B', 'verification_required', 'ready'):
        if field not in result.stdout:
            raise ValueError('Missing approval review field: ' + field)
    if sha256(trial) != trial_hash or sha256(reference) != reference_hash:
        raise ValueError('The approval modified an input')
    # Independent expected disk: preserve the exact original READY sector,
    # change its generation/checksum and install it in the two audited slots.
    with reference.open('rb') as disk:
        original = read_records(disk)
    sector = bytearray(original.state[0])
    struct.pack_into('<I', sector, 16, 4)
    struct.pack_into('<I', sector, 508, zlib.crc32(sector[:508]))
    shutil.copyfile(trial, expected)
    with expected.open('r+b') as disk:
        for name in STATE:
            disk.seek(original.files[name][0] * SECTOR)
            disk.write(sector)
    if sha256(approved) != sha256(expected):
        raise ValueError('Approval changed bytes outside the two expected installation sectors')
    noop = work / 'already-approved.img'
    run_cli(approved, noop, '').check_returncode()
    if noop.exists():
        raise ValueError('An already completed approval published another image')

    vdi = work / 'approved.vdi'
    subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'vdi', approved, vdi], check=True)
    compare(vdi, approved)
    with boot(qemu, bios, work, vdi, 'approval-cold-f6') as menu:
        menu.expect('MS-DOS 6.22')
        menu.key('f6', 7)
        menu.wait('RB STATE proof=0000 detail=0000')
        menu.expect('0x00000004 A')
        menu.expect('0x0000 / 0x0000')
        menu.expect(ui['STATE_MATCH'])
        menu.key('esc', 0)
        menu.open()  # Unmodified F9 on the already installed firmware accepts this pair.
        menu.value(8, 2)
        menu.key('esc', 0)
    with boot(qemu, bios, work, vdi, 'approval-cold-countdown') as menu:
        menu.expect(ui['DOS_TIMER'])
        menu.wait('RB HANDOFF PASS')
    with boot(qemu, bios, work, vdi, 'approval-cold-enter') as menu:
        menu.qmp.call('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 20})
        menu.wait('RB HANDOFF PASS')
        entry = original.mbr[446:462]  # The published fixture uses primary slot 1.
        if menu.memory(0x7c00, 512) != original.vbr or menu.memory(0x800, 16) != entry:
            raise ValueError('Normal handoff changed the approved VBR or partition entry')
    compare(vdi, approved)
    shutil.copyfile(bundle, directory / bundle.name)
    print(f'{language}: {bundle.name} {sha256(bundle)}', flush=True)
