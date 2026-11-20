"""Boot the enrolled ATA reader and check a real original capture on a separate floppy."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import put, sector_body, label
from prepare_mbr_target import prepare_pair
from rescue_text import LANGUAGES, load_catalog, output_name

MODEL = 'VBOX HARDDISK'
SERIAL = 'VB69696969-11111111'
FOREIGN = 'VB69696969-22222222'
TARGET = bytes.fromhex('112233445566478899aabbccddeeff01')
CARRIER = bytes.fromhex('112233445566478899aabbccddeeff02')
SECTORS = 10080
PASS = 'RB ATA TARGET PASS'
BLOCK = 'RB ATA TARGET BLOCKED'


def disk_fields(ui, title, model, serial, sectors):
    return [ui[title], ui['D_MODEL'] + ' ' + model, ui['D_SERIAL'] + ' ' + serial,
            ui['A_SECTORS'] + f' 0x{sectors:016X}']


def original_record(payload, sectors):
    data = bytearray(512)
    struct.pack_into('<8s16sQ16s6I', data, 0, b'RBORG001', TARGET, sectors, CARRIER,
                     1, 1, 0, 0, zlib.crc32(payload), 0)
    struct.pack_into('<I', data, 508, zlib.crc32(data[:508]))
    return bytes(data)


def campaign(exe, bios, src, out, tmp, manifest, language):
    ui = load_catalog(language)
    template = (src / 'mbr-target.img').read_bytes()
    enrolled, virgin = prepare_pair(template, MODEL, SERIAL, SECTORS, TARGET, CARRIER)
    boot, carrier, disk = (tmp / n for n in ('boot.img', 'carrier.img', 'disk.raw'))
    boot.write_bytes(enrolled)
    carrier.write_bytes(virgin)
    payload = sector_body(0)
    disk.write_bytes(payload + bytes(SECTORS * 512 - 512))  # no fixture label anywhere
    fixture = dict(binary=(src / 'mbr-target.bin').read_bytes(), memory=manifest['memory']['mbr-target'])
    cases = []
    expect = ['RB ATA TARGET'] + disk_fields(ui, 'D_EXPECT', MODEL, SERIAL, SECTORS)
    active = expect + disk_fields(ui, 'D_LIVE', MODEL, SERIAL, SECTORS) + ['TARGET MATCH', ui['D_ACTION']]
    capture = [(ui['D_ACTION'], 'e', None, False), (ui['D_INSERT'], 'ret', carrier, False)]

    def run(name, lines, actions=(), writes=(), reads=(), *, model=MODEL, serial=SERIAL, attached=True):
        images = (boot.read_bytes(), bytearray(carrier.read_bytes()), sha256(disk))
        for lba, data in writes:
            put(images[1], lba, data)
        result = boot_fixture(exe, bios, fixture, out, boot, disk if attached else None, name, lines,
                              actions, [n for n, _ in writes], list(reads), readonly_start=True,
                              ata_identity=(model, serial))
        if boot.read_bytes() != images[0] or carrier.read_bytes() != images[1] or sha256(disk) != images[2]:
            raise ValueError(f'{name}: unexpected persistent device changes')
        cases.append(result)
        print(name + ': ' + lines[-1], flush=True)

    run('match-read-only', active + [PASS], [(ui['D_ACTION'], 'esc', None, False)])
    for name, model, serial in (('same-sectors-different-serial', MODEL, FOREIGN),
                                ('same-serial-different-model', 'OTHER MODEL', SERIAL)):
        run(name, expect + disk_fields(ui, 'D_LIVE', model, serial, SECTORS) + [ui['D_WRONG'], BLOCK],
            model=model, serial=serial)
    run('no-disk', expect + [ui['D_ABSENT'], BLOCK], attached=False)
    run('cancel-carrier', active + [ui['D_INSERT'], ui['D_CANCEL'], PASS],
        [capture[0], (ui['D_INSERT'], 'esc', None, False)])
    run('capture', active + [ui['D_INSERT'], 'ORIGINAL REV 1 VERIFIED', PASS], capture,
        [(2, payload), (1, original_record(payload, SECTORS))], [0] * 3)
    run('sealed-cold', active + [ui['D_INSERT'], 'ORIGINAL REV 1 VERIFIED', PASS], capture, reads=[0] * 2)
    with disk.open('r+b') as stream:
        stream.write(sector_body(9))  # same CRC, different MBR
    run('changed-sealed', active + [ui['D_INSERT'], ui['D_CAPTURE_FAIL'], 'CAPTURE STATUS 9', BLOCK], capture, reads=[0])
    carrier.write_bytes(label(TARGET) + virgin[512:])
    run('substituted-carrier', active + [ui['D_INSERT'], ui['D_CAPTURE_FAIL'], 'CAPTURE STATUS 7', BLOCK], capture, reads=[0])
    with disk.open('r+b') as stream:
        stream.truncate((SECTORS + 1) * 512)
    run('resized', expect + disk_fields(ui, 'D_LIVE', MODEL, SERIAL, SECTORS + 1) + [ui['D_WRONG'], BLOCK])
    # The same ATA model/serial at a newly enrolled capacity, without any target label.
    new = SECTORS + 1
    new_boot, _ = prepare_pair(template, MODEL, SERIAL, new, TARGET, CARRIER)
    boot.write_bytes(new_boot)
    carrier.write_bytes(virgin)
    ready = ['RB ATA TARGET'] + disk_fields(ui, 'D_EXPECT', MODEL, SERIAL, new) + disk_fields(ui, 'D_LIVE', MODEL, SERIAL, new)
    run('other-enrollment', ready + ['TARGET MATCH', ui['D_ACTION'], ui['D_INSERT'], 'ORIGINAL REV 1 VERIFIED', PASS],
        capture, [(2, sector_body(9)), (1, original_record(sector_body(9), new))], [0] * 3)
    boot.write_bytes(template)
    run('unprovisioned', ['RB ATA TARGET', ui['D_PROFILE'], BLOCK])
    boot.write_bytes(enrolled[:-1] + bytes([enrolled[-1] ^ 1]))
    run('torn-enrollment', ['RB ATA TARGET', ui['D_PROFILE'], BLOCK])
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    args = parser.parse_args()
    executable = shutil.which(args.qemu)
    if not executable:
        raise ValueError('QEMU not found')
    exe = Path(executable).resolve()
    bios = (args.bios or exe.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    src = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-original-test-ata' + ('-de' if args.language == 'de' else ''))
    prepare_output(out)
    report = out / 'target-results.json'
    report.unlink(missing_ok=True)
    manifest = json.loads((src / 'manifest.json').read_bytes())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-target.img', 'mbr-target.bin'):
        if sha256(src / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed target image: ' + name)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        try:
            cases = campaign(exe, bios, src, work, work, manifest, args.language)
        except Exception:
            for log in work.glob('*.log'):
                shutil.copyfile(log, out / log.name)
            raise
    shutil.copyfile(src / 'mbr-target.img', out / 'mbr-target.img')
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(cases=cases, ui=manifest['ui'], build_inputs=manifest['build_inputs'],
                                      qemu_sha256=sha256(exe), bios_sha256=sha256(bios)), indent=2) + '\n')


if __name__ == '__main__':
    main()
