"""Enroll, review and cold-verify an ATA-bound pair on the actual BIOS/PIO path."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zlib

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import Checkpoint, EMPTY, ORIGIN, header, label, put, seal, sector_body
from prepare_mbr_target import PROFILE_ENTRY, WITNESS_ENTRY, prepare_pair
from rescue_text import LANGUAGES, load_catalog, output_name
from test_mbr_reservation import fault_rom
from test_mbr_target import BLOCK, FOREIGN, MODEL, PASS, SECTORS, SERIAL, disk_fields

HEADER = 2875
MEDIA = ('mbr-target.img', 'mbr-original-data.img')


def campaign(exe, bios, src, work, out, manifest, language):
    ui = load_catalog(language)
    target_id, carrier_id, witness_id = [
        b'RB-ATA-TEST-' + language.encode('ascii') + bytes((0, n)) for n in (1, 2, 3)]
    boot, carrier = (work / name for name in MEDIA)
    disk = work / 'disk.raw'
    enrolled, virgin = prepare_pair((src / MEDIA[0]).read_bytes(), MODEL, SERIAL, SECTORS,
                                   target_id, carrier_id, witness_id)
    original, changed = sector_body(0), sector_body(2)
    assert changed != original and zlib.crc32(original) == zlib.crc32(changed)
    disk.write_bytes(original + bytes(SECTORS * 512 - 512))
    boot.write_bytes(enrolled)
    carrier.write_bytes(virgin)
    fixture = dict(binary=(src / 'mbr-target.bin').read_bytes(), memory=manifest['memory']['mbr-target'])
    menu = ['RB ATA TARGET', ui['D_MENU'], ui['D_FIRST']]
    expected = menu + disk_fields(ui, 'D_EXPECT', MODEL, SERIAL, SECTORS)
    live = expected + disk_fields(ui, 'D_LIVE', MODEL, SERIAL, SECTORS) + ['TARGET MATCH']
    cases = []

    def run(name, lines, actions, writes=(), samples=0, *, attached=True, serial=SERIAL, rom=None, cut=False):
        images = {p: bytearray(p.read_bytes()) for p in (boot, carrier)}
        disk_hash = sha256(disk)
        for path, lba, data in writes:
            put(images[path], lba, data)
        result = boot_fixture(exe, bios, fixture, work, boot, disk if attached else None, name, lines, actions,
                              [n for _, n, _ in writes], [0] * samples, ata_identity=(MODEL, serial),
                              readonly_start=not attached, rom=rom, cut=cut)
        if sha256(disk) != disk_hash or any(p.read_bytes() != data for p, data in images.items()):
            raise ValueError(f'{name}: unexpected persistent device changes')
        result.update(hdd_attached=attached, media_sha256={p.name: sha256(p) for p in images})
        cases.append(result)
        print(f'{name}: ' + ('POWER CUT' if cut else lines[-1]), flush=True)

    def menu_key(key):
        return (ui['D_FIRST'], key, None, False)

    def swap(field, path, readonly=False):
        return (ui[field], 'ret', path, readonly)

    def record(tag, point):
        return header(tag, point, carrier_id, target_id=target_id, capacity=SECTORS)

    def verify(name, point=None, *, error=0, exchange=True):
        lines, actions = list(expected), [menu_key('v')]
        if exchange:
            lines.append(ui['A_DATA'])
            actions.append(swap('A_DATA', carrier, True))
        if error:
            lines += [f'REVIEW STATUS {error}', BLOCK]
        else:
            lines += ['ORIGINAL REV 1 VERIFIED', f'APPROVED REV {point.approved}' if point.approved else
                      'APPROVED NONE', f'LAST ISSUED {point.issued}', PASS]
        run(name, lines, actions, attached=False)

    run('compare-only', live + [PASS], [menu_key('p')])
    verify('blank-detached', error=4, exchange=False)
    for key in ('r', 'e'):
        run('foreign-' + key, expected + disk_fields(ui, 'D_LIVE', MODEL, FOREIGN, SECTORS) +
            [ui['D_WRONG'], BLOCK], [menu_key(key)], serial=FOREIGN)
        run('absent-' + key, expected + [ui['D_ABSENT'], BLOCK], [menu_key(key)], attached=False)

    def edited(data, start, replacement):
        return data[:start] + replacement + data[start + len(replacement):]

    for name, offset, value in [('witness-readonly', WITNESS_ENTRY + 11, b'!'),
                                ('profile-renamed', PROFILE_ENTRY, b'X'),
                                ('missing-witness', WITNESS_ENTRY, b'X')]:
        boot.write_bytes(edited(enrolled, offset, value))
        run(name, live + ['REVIEW STATUS 2', BLOCK], [menu_key('e')])
    boot.write_bytes(edited(enrolled, (HEADER + 3) * 512, changed))
    run('occupied-other-slot', live + ['REVIEW STATUS 7', BLOCK], [menu_key('e')], samples=1)
    for name, start, replacement in [('duplicate-identity', 108, carrier_id), ('reserved-byte', 124, b'X')]:
        boot.write_bytes(enrolled[:-512] + seal(edited(enrolled[-512:], start, replacement)))
        run(name, ['RB ATA TARGET', ui['D_PROFILE'], BLOCK], [])
    boot.write_bytes(enrolled)

    enroll = [(carrier, 2, original), (carrier, 1, record(b'RBORG001', ORIGIN)),
              (carrier, 3, record(b'RBCMT001', ORIGIN)), (boot, HEADER + 1, original),
              (boot, HEADER, record(b'RBWIT001', ORIGIN))]
    lines = live + [ui['A_DATA'], ui['D_BACK']]
    actions = [menu_key('e'), swap('A_DATA', carrier), swap('D_BACK', boot)]
    rom = fault_rom(src / 'int13-reserve.rom', work / 'fault.rom', 2, 2)
    run('cut-after-original-seal', lines[:-1], actions[:-1], enroll[:2], 3, rom=rom, cut=True)
    verify('only-carrier-sealed', error=4, exchange=False)
    run('resume-first-capture', lines + ['INITIAL WITNESS PUBLISHED', PASS], actions, enroll[2:], 5)
    verify('resumed-detached', ORIGIN)
    boot.write_bytes(enrolled)
    carrier.write_bytes(virgin)
    run('first-capture', lines + ['INITIAL WITNESS PUBLISHED', PASS], actions, enroll, 6)
    verify('initial-detached', ORIGIN)
    initial_pair = (boot.read_bytes(), carrier.read_bytes())
    run('repeat-first-on-closed-pair', live + ['REVIEW STATUS 7', BLOCK], [menu_key('e')], samples=1)

    with disk.open('r+b') as stream:
        stream.write(changed)
    reserved, approved = Checkpoint(2, 2), Checkpoint(3, 2, 2)
    writes = [(carrier, 6, EMPTY), (carrier, 5, record(b'RBCMT001', reserved)),
              (boot, HEADER, record(b'RBWIT001', reserved)), (carrier, 4, changed),
              (carrier, 3, record(b'RBCMT001', approved)), (boot, HEADER + 3, changed),
              (boot, HEADER, record(b'RBWIT002', approved))]
    delta = [(i, a, b) for i, (a, b) in enumerate(zip(original, changed)) if a != b]
    lines = live + [ui['A_DATA'], ui['D_BACK'], ui['A_TARGET'] + ' ' + target_id.hex(' ').upper(),
                    ui['A_CARRIER'] + ' ' + carrier_id.hex(' ').upper(), ui['A_SECTORS'] + f' 0x{SECTORS:016X}',
                    'REVIEW 2', 'BASE REV 1', f'CHANGED BYTES {len(delta)}', ui['A_DIFF']]
    lines += [f'0x{i:04X}     {a:02X} -> {b:02X}' for i, a, b in delta]
    lines += [ui['A_DECIDE'], ui['A_SAVE_DATA'], ui['D_SAVE_BACK']]
    actions = [menu_key('r'), swap('A_DATA', carrier), swap('D_BACK', boot),
               (ui['A_DECIDE'], ui['A_YES'].lower(), None, False),
               swap('A_SAVE_DATA', carrier), swap('D_SAVE_BACK', boot)]

    rom = fault_rom(src / 'int13-reserve.rom', work / 'fault.rom', 7, 1)
    run('cut-before-approval-header', lines, actions, writes[:6], 3, rom=rom, cut=True)
    verify('pending-approval-detached', reserved)
    boot.write_bytes(initial_pair[0])
    carrier.write_bytes(initial_pair[1])
    run('approve', lines + ['APPROVED REV 2', PASS], actions, writes, 3)
    run('foreign-after-approval', expected + disk_fields(ui, 'D_LIVE', MODEL, FOREIGN, SECTORS) +
        [ui['D_WRONG'], BLOCK], [menu_key('r')], serial=FOREIGN)
    verify('approved-detached', approved)
    approved_pair = (boot.read_bytes(), carrier.read_bytes())
    carrier.write_bytes(initial_pair[1])
    verify('stale-recovery', error=6)
    carrier.write_bytes(label(target_id) + approved_pair[1][512:])
    verify('wrong-recovery', error=2)
    carrier.write_bytes(edited(approved_pair[1], 4 * 512, original))
    verify('same-crc-other-approved-bytes', error=7)
    carrier.write_bytes(approved_pair[1])
    # Export only the byte-exact pair exercised by the detached verification.
    for path in (boot, carrier):
        shutil.copyfile(path, out / path.name)
    return dict(cases=cases, manual_media={n: sha256(out / n) for n in MEDIA})


def main(run=campaign, folder='mbr-review-test-ata', report_name='ata-history-results.json', media=MEDIA):
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
    out = ROOT / 'build' / (folder + ('-de' if args.language == 'de' else ''))
    prepare_output(out)
    report = out / report_name
    for name in (report.name, *media):
        (out / name).unlink(missing_ok=True)
    manifest = json.loads((src / 'manifest.json').read_bytes())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-target.img', 'mbr-target.bin', 'int13-reserve.rom'):
        if sha256(src / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed ATA history input: ' + name)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nide_bus_exec_cmd\nblk_co_pwritev\n')
        try:
            result = run(exe, bios, src, work, out, manifest, args.language)
        except Exception:
            for log in work.glob('*.log'):
                shutil.copyfile(log, out / log.name)
            raise
    check_build_inputs(manifest, ROOT)
    result.update(ui=manifest['ui'], build_inputs=manifest['build_inputs'], qemu_sha256=sha256(exe),
                  bios_sha256=sha256(bios))
    report.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
