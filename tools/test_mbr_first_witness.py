"""Publish a first witness for an actual BIOS capture and verify the pair without the HDD."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import label, put, seal, sector_body, WITNESS_LBA
from rescue_text import LANGUAGES, output_name
from test_mbr_original import boot as capture_boot, original_header, SAMPLE, TARGET, BLANK
from test_mbr_reservation import fault_rom

TITLE = 'RB FIRST MBR WITNESS'
MENU = 'E FIRST INSTALL / V VERIFY / ESC CANCEL'
DATA = 'INSERT RECOVERY FLOPPY AND PRESS ENTER'
RETURN = 'REINSERT WITNESS FLOPPY AND PRESS ENTER'
IO, FORMAT, CRC, STALE, CHANGED, ORIGIN = 2, 4, 5, 6, 7, 8
WH, WP = WITNESS_LBA + 1, WITNESS_LBA + 2


def header(tag, original):
    data = bytearray(original_header(original))
    data[:8] = tag
    return seal(data)


def replace(path, lba, data):
    with path.open('r+b') as stream:
        stream.seek(lba * 512)
        stream.write(data)


def campaign(exe, bios, source, out, temp, memory):
    witness, carrier, disk = (temp / n for n in ('mbr-witness.img', 'mbr-original-data.img', 'hdd.img'))
    blank_witness = (source / 'mbr-witness.img').read_bytes()
    blank_carrier = (source / carrier.name).read_bytes()
    hdd = (source / 'mbr-original-hdd.img').read_bytes()
    fixture = dict(binary=(source / 'mbr-witness.bin').read_bytes(), memory=memory['mbr-witness'])
    capture_fixture = dict(binary=(source / 'mbr-original.bin').read_bytes(), memory=memory['mbr-original'])
    original_boot = temp / 'mbr-original.img'
    original_boot.write_bytes((source / 'mbr-original.img').read_bytes())
    results, captures = [], []

    def capture(name, original):
        disk.write_bytes(original + hdd[512:])
        carrier.write_bytes(blank_carrier)
        planned = ([] if original == BLANK else [(2, original)]) + [(1, original_header(original))]
        before = sha256(disk)
        captures.append(capture_boot(exe, bios, capture_fixture, out, original_boot, disk, carrier,
                                     name, 0, planned, SAMPLE * 3))
        expected = bytearray(blank_carrier)
        for lba, data in planned:
            put(expected, lba, data)
        if sha256(disk) != before or carrier.read_bytes() != expected:
            raise ValueError(f'{name}: original capture differs from its physical source')
        return bytes(expected)

    def run(name, *, key='e', data=True, back=True, status=0, writes=(), samples=0,
            attached=True, rom=None, cut=False, protected=(), return_image=None):
        paths = {'carrier': carrier, 'witness': witness}
        expected = {k: bytearray(p.read_bytes()) for k, p in paths.items()}
        source_before = sha256(disk)
        other_before = return_image.read_bytes() if return_image is not None else None
        for medium, n, payload in writes:
            put(expected[medium], n, payload)
        lines = [TITLE, MENU]
        actions = [(MENU, key, None, False)]
        if data:
            lines.append(DATA)
            actions.append((DATA, 'ret', carrier, 'carrier' in protected))
        if back:
            lines.append(RETURN)
            actions.append((RETURN, 'ret', return_image or witness, 'witness' in protected))
        if not cut:
            if status:
                lines += [f'WITNESS STATUS {status}', 'RB WITNESS BLOCKED']
            else:
                lines += ['ORIGINAL REV 1 VERIFIED' if key == 'v' else 'INITIAL WITNESS PUBLISHED',
                          'RB WITNESS PASS']
        result = boot_fixture(exe, bios, fixture, out, witness, disk if attached else None,
                              name, lines, actions, [n for _, n, _ in writes], SAMPLE * samples,
                              rom=rom, cut=cut, readonly_start='witness' in protected)
        if (sha256(disk) != source_before or any(p.read_bytes() != expected[k] for k, p in paths.items())
                or (return_image is not None and return_image.read_bytes() != other_before)):
            raise ValueError(f'{name}: unexpected persisted bytes')
        result['hdd_attached'] = attached
        result['media_sha256'] = {k: sha256(p) for k, p in paths.items()}
        results.append(result)
        print(f'{name}: ' + ('POWER CUT' if cut else lines[-1]), flush=True)

    def verify(name, *, status=0, data=True):
        run(name, key='v', data=data, back=False, status=status, attached=False,
            protected=('witness', 'carrier'))

    def planned(original):
        return [('carrier', 3, header(b'RBCMT001', original)),
                ('witness', WP, original), ('witness', WH, header(b'RBWIT001', original))]

    original = hdd[:512]
    sealed = capture('live-capture', original)
    writes = planned(original)

    def reset():
        disk.write_bytes(hdd)
        witness.write_bytes(blank_witness)
        carrier.write_bytes(sealed)

    reset()
    run('publish', writes=writes, samples=3)
    verify('verify-detached')
    # Retain the exact media from successful independent guest processes.
    verified_pair = (witness.read_bytes(), carrier.read_bytes())
    run('already-published', data=False, back=False, status=CHANGED, samples=1)
    other = sector_body(9)
    replace(carrier, 2, other)
    verify('same-crc-different-original', status=CHANGED)
    carrier.write_bytes(verified_pair[1])
    replace(witness, WP, other)
    verify('same-crc-different-witness', status=CHANGED)
    witness.write_bytes(verified_pair[0])
    replace(carrier, 3, BLANK)
    verify('missing-selected-commit', status=FORMAT)
    carrier.write_bytes(verified_pair[1])
    replace(carrier, 0, label(TARGET))
    verify('swapped-carrier', status=IO)
    reset()
    verify('unpublished-witness', status=FORMAT, data=False)
    run('cancelled-origin', key='esc', data=False, back=False, status=ORIGIN, attached=False)
    run('missing-target', data=False, back=False, status=IO, attached=False)
    carrier.write_bytes(blank_carrier)
    run('missing-original', back=False, status=CHANGED, samples=1)
    reset()
    replace(disk, 0, other)
    run('live-same-crc-conflict', back=False, status=CHANGED, samples=1)
    reset()
    replace(carrier, 6, other)
    run('later-carrier-history', back=False, status=CHANGED, samples=1)
    reset()
    replace(witness, WH + 2, other)
    run('unexpected-witness-approval', data=False, back=False, status=CHANGED, samples=1)
    reset()
    run('protected-carrier', back=False, status=IO, samples=2, protected=('carrier',))
    run('protected-witness', status=IO, writes=writes[:1], samples=2, protected=('witness',))
    reset()
    wrong = temp / 'returned.img'
    wrong.write_bytes(blank_witness)
    replace(wrong, WITNESS_LBA, label(TARGET))
    run('foreign-returned-witness', status=IO, writes=writes[:1], samples=2, return_image=wrong)
    reset()
    wrong.write_bytes(blank_witness)
    replace(wrong, WP, original)
    run('changed-returned-witness', status=CHANGED, writes=writes[:1], samples=2, return_image=wrong)
    for mode, done in [(20, 0), (21, 2)]:
        reset()
        run(f'changed-live-read-{mode - 18}', status=CHANGED, writes=writes[:done],
            samples=mode - 18, back=bool(done), rom=source / f'int13-{mode}.rom')
        verify(f'changed-live-read-{mode - 18}-detached', status=FORMAT, data=False)
    for ordinal in (1, 2, 3):
        for mode, fault in enumerate(('before', 'after', 'torn', 'lost', 'ambiguous'), 1):
            reset()
            name = f'{fault}-write-{ordinal}'
            rom = fault_rom(source / 'int13-reserve.rom', temp / 'cut.rom', ordinal, mode)
            completed = ordinal - 1 if fault in ('before', 'lost') else ordinal
            applied = writes[:completed]
            if fault == 'torn':
                medium, n, payload = applied[-1]
                applied[-1] = (medium, n, payload[:128] + bytes(384))
            run(name, status=CHANGED if fault == 'lost' else IO, writes=applied, rom=rom,
                cut=mode <= 3, samples=3 if ordinal == 3 else 2, back=ordinal != 1)
            if fault == 'torn':
                verify(name + '-detached', status=CRC if ordinal == 3 else FORMAT, data=False)
                run(name + '-retry', status=STALE if ordinal == 1 else CHANGED, writes=[],
                    samples=1, back=False, data=ordinal == 1)
            elif completed == 3:
                verify(name + '-detached')
            else:
                verify(name + '-unpublished', status=FORMAT, data=False)
                run(name + '-retry', writes=writes[completed:], samples=3)
                verify(name + '-detached')
    reset()
    rom = fault_rom(source / 'int13-reserve.rom', temp / 'cut.rom', 3, 6)
    run('failed-closing-read', status=FORMAT, writes=writes, samples=3, rom=rom)
    verify('failed-closing-read-detached')

    for name, value in [('distinct-original', other), ('all-zero-original', BLANK)]:
        capture(name + '-capture', value)
        witness.write_bytes(blank_witness)
        updates = [row for row in planned(value) if row[2] != BLANK]
        run(name + '-publish', writes=updates, samples=3)
        verify(name + '-detached')

    return dict(captures=captures, cases=results), verified_pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    args = parser.parse_args()
    found = shutil.which(args.qemu)
    if not found:
        raise ValueError('QEMU not found')
    exe = Path(found).resolve()
    bios = (args.bios or exe.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    source = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-witness-test' if args.language == 'en' else 'mbr-witness-test-de')
    prepare_output(out)
    report = out / 'witness-results.json'
    pair = [out / 'mbr-witness.img', out / 'mbr-original-data.img']
    for path in [report, *pair]:
        path.unlink(missing_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-witness.bin', 'mbr-witness.img', 'mbr-original.bin', 'mbr-original.img',
                 'mbr-original-hdd.img', 'mbr-original-data.img', 'int13-reserve.rom', 'int13-20.rom', 'int13-21.rom'):
        if sha256(source / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed witness fixture: ' + name)
    (out / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    with tempfile.TemporaryDirectory() as tmp:
        result, images = campaign(exe, bios, source, out, Path(tmp), manifest['memory'])
    check_build_inputs(manifest, ROOT)
    for path, image in zip(pair, images):
        path.write_bytes(image)
    result.update(ui=manifest['ui'], build_inputs=manifest['build_inputs'], qemu_sha256=sha256(exe),
                  bios_sha256=sha256(bios), verified_pair={p.name: sha256(p) for p in pair})
    report.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
