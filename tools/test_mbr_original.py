"""Capture an original MBR through the BIOS and cold-boot the same recovery media."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_restart_fixtures import label, put, sector_body
from rescue_text import LANGUAGES, output_name
from test_mbr_reservation import fault_rom
from mbr_boot import boot_fixture

TITLE = 'RB ORIGINAL MBR'
PROMPT = 'ENTER CONFIRMS FIRST INSTALL, ESC CANCELS'
TARGET = bytes(15) + b'\x61'
CARRIER = bytes(15) + b'\x62'
SAMPLE = [10079, 0, 10079]
BLANK = bytes(512)


def original_header(data):
    header = bytearray(512)
    struct.pack_into('<8s16sQ16s6I', header, 0, b'RBORG001', TARGET, 10080, CARRIER,
                     1, 1, 0, 0, zlib.crc32(data), 0)
    struct.pack_into('<I', header, 508, zlib.crc32(header[:508]))
    return bytes(header)


def boot(exe, bios, fixture, out, boot_disk, disk, carrier, name, status, writes, reads,
         *, rom=None, readonly=False, key='ret', cut=False, attached=True):
    lines = [TITLE, 'INSERT RECOVERY FLOPPY', PROMPT]
    if not cut:
        lines += ([f'CAPTURE STATUS {status}', 'RB ORIGINAL BLOCKED'] if status else
                  ['ORIGINAL REV 1 VERIFIED', 'RB ORIGINAL PASS'])
    result = boot_fixture(exe, bios, fixture, out, boot_disk, disk if attached else None, name, lines,
                          [(PROMPT, key, carrier, readonly)], [n for n, _ in writes], reads, rom=rom, cut=cut)
    result['carrier_write_lbas'] = result.pop('floppy_write_lbas')
    return result


def campaign(exe, bios, source, out, temp, memory):
    image = (source / 'mbr-original.img').read_bytes()
    virgin = (source / 'mbr-original-data.img').read_bytes()
    hdd = (source / 'mbr-original-hdd.img').read_bytes()
    boot_disk, disk, carrier = (temp / name for name in ('boot.img', 'disk.img', 'carrier.img'))
    boot_disk.write_bytes(image)
    original = hdd[:512]
    header = original_header(original)
    both = [(2, original), (1, header)]
    fixture = dict(binary=(source / 'mbr-original.bin').read_bytes(), memory=memory)
    results = []

    def reset():
        disk.write_bytes(hdd)
        carrier.write_bytes(virgin)

    def edit(path, sector, value):
        with path.open('r+b') as stream:
            stream.seek(sector * 512)
            stream.write(value)

    def run(name, status, writes, reads, **options):
        expected = bytearray(carrier.read_bytes())
        disk_before = sha256(disk)
        for n, value in writes:
            put(expected, n, value)
        result = boot(exe, bios, fixture, out, boot_disk, disk, carrier, name, status, writes, reads, **options)
        if disk_before != sha256(disk) or boot_disk.read_bytes() != image or carrier.read_bytes() != expected:
            raise ValueError(f'{name}: persisted media differ from byte-for-byte expectation')
        result['carrier_sha256'] = sha256(carrier)
        results.append(result)
        print(f'{name}: {result["transcript"][-1] if not options.get("cut") else "POWER CUT"}', flush=True)

    reset()
    run('capture', 0, both, SAMPLE * 3)
    run('sealed-cold', 0, [], SAMPLE * 2, readonly=True)
    other = sector_body(9)
    if other == original or zlib.crc32(other) != zlib.crc32(original):
        raise ValueError('Expected two different MBRs with the same whole-sector CRC')
    edit(disk, 0, other)
    run('changed-mbr-equal-crc', 9, [], SAMPLE)
    reset()
    edit(disk, 0, other)
    run('second-original', 0, [(2, other), (1, original_header(other))], SAMPLE * 3)
    reset()
    edit(disk, 0, BLANK)
    run('blank-original', 0, [(1, original_header(BLANK))], SAMPLE * 3)
    reset()
    run('unknown-origin', 2, [], [], key='esc')
    run('no-target', 6, [], [], attached=False)
    run('protected-carrier', 7, [], SAMPLE, readonly=True)
    edit(carrier, 0, label(TARGET))
    run('swapped-carrier', 7, [], SAMPLE)
    reset()
    edit(disk, 10079, label(CARRIER))
    run('swapped-target', 6, [], [10079])
    reset()
    with disk.open('r+b') as stream:
        stream.truncate(len(hdd) + 512)
    run('wrong-capacity', 6, [], [])
    reset()
    edit(disk, 0, original[:432] + b'RBM1' + original[436:])
    run('already-managed', 2, [], SAMPLE)
    reset()
    edit(carrier, 6, sector_body(3))
    run('existing-history', 9, [], SAMPLE)
    reset()
    edit(carrier, 1, header)
    run('missing-sealed-payload', 9, [], SAMPLE)
    for mode, name, saved in [(20, 'changed-before-seal', both[:1]), (21, 'changed-after-seal', both)]:
        reset()
        run(name, 9, saved, SAMPLE * (mode - 18), rom=source / f'int13-{mode}.rom')
        run(name + '-cold', 0, both[len(saved):], SAMPLE * (3 if mode == 20 else 2))
    for ordinal in (1, 2):
        for mode, fault in enumerate(('before', 'after', 'torn', 'lost', 'ambiguous'), 1):
            reset()
            name = f'{fault}-write-{ordinal}'
            rom = fault_rom(source / 'int13-reserve.rom', temp / 'cut.rom', ordinal, mode)
            completed = ordinal - 1 if fault in ('before', 'lost') else ordinal
            saved = both[:completed]
            if fault == 'torn':
                n, value = saved[-1]
                saved[-1] = (n, value[:128] + bytes(384))
            # The payload is the first write. A second live sample precedes the header.
            run(name, 9 if fault == 'lost' else 7, saved, SAMPLE * ordinal, rom=rom, cut=mode <= 3)
            if fault == 'torn':
                run(name + '-cold', 9 if ordinal == 1 else 4, [], SAMPLE)
            else:
                run(name + '-cold', 0, both[completed:], SAMPLE * (2 if completed == 2 else 3))
    return results


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
    source = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-original-test' if args.language == 'en' else 'mbr-original-test-de')
    prepare_output(out)
    report = out / 'original-results.json'
    report.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-original.img', 'mbr-original-data.img', 'mbr-original-hdd.img',
                 'mbr-original.bin', 'int13-reserve.rom', 'int13-20.rom', 'int13-21.rom'):
        if sha256(source / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed original capture fixture: ' + name)
    (out / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    with tempfile.TemporaryDirectory() as tmp:
        results = campaign(exe, bios, source, out, Path(tmp), manifest['memory']['mbr-original'])
    check_build_inputs(manifest, ROOT)
    report.write_text(json.dumps(dict(ui=manifest['ui'], build_inputs=manifest['build_inputs'], cases=results,
                                      qemu_sha256=sha256(exe), bios_sha256=sha256(bios)), indent=2) + '\n')


if __name__ == '__main__':
    main()
