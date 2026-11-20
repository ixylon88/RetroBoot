"""Approve an observed BIOS MBR, interrupt publication and independently reopen both roles."""
import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from build_inputs import check_build_inputs
from build_rescue import ROOT, prepare_output, sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import label, put, seal, sector_body
from rescue_text import LANGUAGES, load_catalog, output_name
from test_mbr_original import BLANK, CARRIER, SAMPLE, TARGET, boot as capture, original_header
from test_mbr_reservation import fault_rom

TITLE = 'RB MBR REVIEW'
PASS, BLOCK = 'RB MBR REVIEW PASS', 'RB MBR REVIEW BLOCKED'
HEADER = 2876  # The label is at 2875, followed by four records in RBWITNES.BIN.


@dataclass(frozen=True)
class State:
    generation: int = 1
    issued: int = 1
    approved: int = 0
    previous: int = 0
    alternate: bool = False
    payload: bytes = BLANK


def metadata(tag, point, original):
    h = bytearray(original_header(original))
    h[:8] = tag
    struct.pack_into('<6I', h, 48, point.generation, point.issued, point.approved, point.previous,
                     zlib.crc32(original), zlib.crc32(point.payload) if point.approved else 0)
    return seal(h)


def witness_header(point, original):
    return metadata(b'RBWIT002' if point.alternate else b'RBWIT001', point, original)


def planned(old, candidate, original):
    reserved = replace(old, generation=old.generation + 1, issued=old.issued + 1)
    approved = replace(reserved, generation=reserved.generation + 1, approved=reserved.issued,
                       previous=old.approved, payload=candidate, alternate=not old.alternate)

    def carrier(state):
        slot = 3 if state.generation & 1 else 5
        return [('carrier', slot + 1, state.payload),
                ('carrier', slot, metadata(b'RBCMT001', state, original))]

    reserve = carrier(reserved) + [('witness', HEADER, witness_header(reserved, original))]
    publish = carrier(approved) + [('witness', HEADER + 2 + int(approved.alternate), candidate),
                                   ('witness', HEADER, witness_header(approved, original))]
    return reserved, approved, reserve + publish


def campaign(exe, bios, src, out, temp, manifest, lang):
    ui = load_catalog(lang)
    names = ('mbr-review.img', 'mbr-original-data.img', 'mbr-review-hdd.img')
    witness, carrier, hdd = [temp / n for n in names]
    paths = {'witness': witness, 'carrier': carrier}
    fixture = dict(binary=(src / 'mbr-review.bin').read_bytes(), memory=manifest['memory']['mbr-review'])
    records = []
    original_disk = (src / 'mbr-original-hdd.img').read_bytes()
    original = original_disk[:512]
    hdd.write_bytes(original_disk)
    carrier.write_bytes((src / carrier.name).read_bytes())
    witness.write_bytes((src / witness.name).read_bytes())
    begin = State()
    captures = [capture(exe, bios, dict(binary=(src / 'mbr-original.bin').read_bytes(),
                                         memory=manifest['memory']['mbr-original']), out,
                        src / 'mbr-original.img', hdd, carrier, 'live-capture', 0,
                        [(2, original), (1, original_header(original))], SAMPLE * 3)]
    sealed = bytearray((src / carrier.name).read_bytes())
    put(sealed, 1, original_header(original))
    put(sealed, 2, original)
    assert carrier.read_bytes() == sealed and hdd.read_bytes() == original_disk
    assert sha256(src / 'mbr-original.img') == manifest['artifacts']['mbr-original.img']['sha256']

    def boot(name, screen, actions, writes, reads, *, attached=True, rom=None, cut=False, readonly=False):
        expected = {k: bytearray(path.read_bytes()) for k, path in paths.items()}
        disk_hash = sha256(hdd)
        for medium, lba, data in writes:
            put(expected[medium], lba, data)
        result = boot_fixture(exe, bios, fixture, out, witness, hdd if attached else None, name,
                              screen, actions, [lba for _, lba, _ in writes], reads,
                              rom=rom, cut=cut, readonly_start=readonly)
        if sha256(hdd) != disk_hash or any(path.read_bytes() != expected[k] for k, path in paths.items()):
            raise ValueError(f'{name}: unexpected persisted bytes')
        result.update(hdd_attached=attached, hdd_sha256=disk_hash,
                      media_sha256={k: sha256(path) for k, path in paths.items()})
        records.append(result)
        print(f'{name}: ' + ('POWER CUT' if cut else screen[-1]), flush=True)

    def verify(name, state, *, error=0, exchange=True):
        lines = [TITLE, ui['A_MENU']]
        actions = [(lines[-1], 'v', None, False)]
        if exchange:
            lines.append(ui['A_DATA'])
            actions.append((lines[-1], 'ret', carrier, True))
        if error:
            lines += [f'REVIEW STATUS {error}', BLOCK]
        else:
            lines += ['ORIGINAL REV 1 VERIFIED', f'APPROVED REV {state.approved}' if state.approved else
                      'APPROVED NONE', f'LAST ISSUED {state.issued}', PASS]
        boot(name, lines, actions, [], [], attached=False, readonly=True)

    hd = metadata(b'RBCMT001', begin, original)
    boot('enroll-witness', [TITLE, ui['A_MENU'], ui['A_DATA'], ui['A_BACK'], 'INITIAL WITNESS PUBLISHED', PASS],
         [(ui['A_MENU'], 'e', None, False), (ui['A_DATA'], 'ret', carrier, False),
          (ui['A_BACK'], 'ret', witness, False)],
         [('carrier', 3, hd), ('witness', HEADER + 1, original),
          ('witness', HEADER, witness_header(begin, original))], SAMPLE * 3)
    verify('initial-detached', begin)
    initial = (witness.read_bytes(), carrier.read_bytes())
    changed = sector_body(9)
    other = sector_body(10)
    assert changed != original and zlib.crc32(changed) == zlib.crc32(other) == zlib.crc32(original)

    def reset(pair, candidate=changed):
        witness.write_bytes(pair[0])
        carrier.write_bytes(pair[1])
        hdd.write_bytes(candidate + original_disk[512:])

    def attempt(name, old, candidate, *, until='save_back', writes=None, samples=3, reads=None,
                error=0, reject=False, reject_page=False, attached=True, rom=None, cut=False,
                protected=(), save_witness=None, save_carrier=None):
        reserved, new, all_writes = planned(old, candidate, original)
        lines = [TITLE, ui['A_MENU']]
        actions = [(lines[-1], 'r', None, False)]
        phases = ('start', 'data', 'back', 'decision', 'save_data', 'save_back')
        end = phases.index(until)

        def exchange(field, path, role):
            lines.append(ui[field])
            actions.append((lines[-1], 'ret', path, role in protected))

        if end >= 1:
            exchange('A_DATA', carrier, 'reserve_carrier')
        if end >= 2:
            exchange('A_BACK', witness, 'reserve_witness')
        if end >= 3:
            base = old.payload if old.approved else original
            delta = [(i, a, b) for i, (a, b) in enumerate(zip(base, candidate)) if a != b]
            lines += [ui['A_TARGET'] + ' ' + TARGET.hex(' ').upper(),
                      ui['A_CARRIER'] + ' ' + CARRIER.hex(' ').upper(),
                      ui['A_SECTORS'] + ' 0x0000000000002760', f'REVIEW {reserved.issued}', f'BASE REV {old.approved or 1}', f'CHANGED BYTES {len(delta)}']
            if delta:
                lines.append(ui['A_DIFF'])
            for idx, (i, a, b) in enumerate(delta, 1):
                lines.append(f'0x{i:04X}     {a:02X} -> {b:02X}')
                if idx % 8 == 0 and idx < len(delta):
                    lines.append(ui['A_NEXT'])
                    actions.append((lines[-1], 'esc' if reject_page else 'n', None, False))
                    if reject_page:
                        break
            if not reject_page:
                lines.append(ui['A_DECIDE'])
                actions.append((lines[-1], 'esc' if reject else ui['A_YES'].lower(), None, False))
        if end >= 4:
            exchange('A_SAVE_DATA', save_carrier or carrier, 'save_carrier')
        if end >= 5:
            exchange('A_SAVE_BACK', save_witness or witness, 'save_witness')
        if not cut:
            lines += ([f'REVIEW STATUS {error}', BLOCK] if error else
                      ['REVIEW REJECTED', PASS] if reject or reject_page else [f'APPROVED REV {new.approved}', PASS])
        boot(name, lines, actions, all_writes if writes is None else writes, SAMPLE * samples if reads is None
             else reads, attached=attached, rom=rom, cut=cut)
        return reserved, new

    reset(initial)
    for path in (witness, carrier, hdd):
        shutil.copyfile(path, out / path.name)
    _, first = attempt('approve', begin, changed)
    verify('approved-detached', first)
    first_pair = (witness.read_bytes(), carrier.read_bytes())

    reset(first_pair, other)
    reserved, second, steps = planned(first, other, original)
    attempt('approve-second', first, other)
    verify('second-detached', second)
    _, same_again = attempt('approve-identical', second, other)
    verify('identical-new-revision', same_again)

    reset(first_pair, other)
    attempt('reject', first, other, until='decision', reject=True, writes=steps[:3], samples=1)
    verify('rejected-detached', reserved)
    _, after_reject = attempt('fresh-review-after-reject', reserved, other)
    verify('fresh-review-detached', after_reject)

    many = bytes([1] * 22) + original[22:]
    reset(initial, many)
    reservation, paged, changes = planned(begin, many, original)
    attempt('reject-page', begin, many, until='decision', reject_page=True, writes=changes[:3], samples=1)
    verify('rejected-page-detached', reservation)
    _, paged = attempt('accept-after-all-pages', reservation, many)
    verify('paged-detached', paged)

    reset(first_pair, BLANK)
    _, zero = attempt('approve-zero-sector', first, BLANK)
    verify('zero-detached', zero)

    # The three reservation writes have their own complete interruption campaign.
    # Interrupt each new approval write on top of a real, previously approved sector.
    for ordinal in range(4, 8):
        for mode, fault in enumerate(('before', 'after', 'torn', 'lost', 'ambiguous'), 1):
            reset(first_pair, other)
            name = f'{fault}-write-{ordinal}'
            rom = fault_rom(src / 'int13-reserve.rom', temp / 'fault.rom', ordinal, mode)
            applied = list(steps[:ordinal if mode in (2, 3, 5) else ordinal - 1])
            if mode == 3:
                medium, lba, data = applied[-1]
                previous = bytearray(paths[medium].read_bytes())
                for location, address, earlier in applied[:-1]:
                    if location == medium:
                        put(previous, address, earlier)
                old_tail = previous[lba * 512 + 128:(lba + 1) * 512]
                applied[-1] = medium, lba, data[:128] + old_tail
            attempt(name, first, other, writes=applied, samples=3 if ordinal == 7 else 2,
                    until='save_data' if ordinal < 6 else 'save_back',
                    rom=rom, cut=mode <= 3, error=7 if mode == 4 else 2)
            broken = ordinal == 7 and mode == 3
            state = second if ordinal == 7 and mode in (2, 5) else reserved
            verify(name + '-detached', state, error=5 if broken else 0, exchange=not broken)
            if ordinal == 6 and mode == 3:
                _, fresh = attempt('fresh-after-torn-payload', reserved, other)
                verify('fresh-after-torn-detached', fresh)

    for mode, sample in ((20, 2), (21, 3)):
        reset(first_pair, other)
        attempt(f'changed-live-{sample}', first, other, until='decision' if sample == 2 else 'save_back',
                writes=steps[:3] if sample == 2 else steps[:6], samples=sample, error=7,
                rom=src / f'int13-{mode}.rom')
        verify(f'changed-live-{sample}-detached', reserved)

    reset(first_pair, other)
    candidate = bytearray(other)
    candidate[77] ^= 3
    struct.pack_into('<I', candidate, 428, struct.unpack_from('<I', candidate, 428)[0] ^ 0x3989e089)
    assert candidate == changed and zlib.crc32(candidate) == zlib.crc32(other)
    attempt('same-crc-live-substitution', first, other, until='decision', writes=steps[:3],
            samples=2, error=7, rom=src / 'int13-22.rom')
    verify('same-crc-live-detached', reserved)

    reset(first_pair, other)
    attempt('missing-hdd', first, other, until='back', writes=steps[:3], reads=[], error=2, attached=False)
    verify('missing-hdd-detached', reserved)
    reset(first_pair, other)
    attempt('protected-approval-carrier', first, other, until='save_data', writes=steps[:3], samples=2,
            error=2, protected=('save_carrier',))
    verify('protected-carrier-detached', reserved)
    reset(first_pair, other)
    attempt('protected-approval-witness', first, other, writes=steps[:5], samples=2,
            error=2, protected=('save_witness',))
    verify('protected-witness-detached', reserved)

    foreign = temp / 'foreign.img'
    wrong = bytearray(first_pair[0])
    put(wrong, HEADER - 1, label(TARGET))
    foreign.write_bytes(wrong)
    reset(first_pair, other)
    attempt('swapped-witness', first, other, writes=steps[:5], samples=2, error=2, save_witness=foreign)
    assert foreign.read_bytes() == wrong
    verify('swapped-witness-detached', reserved)
    foreign.write_bytes(first_pair[1])
    reset(first_pair, other)
    attempt('stale-carrier', first, other, until='save_data', writes=steps[:3], samples=2,
            error=6, save_carrier=foreign)
    assert foreign.read_bytes() == first_pair[1]
    verify('stale-carrier-detached', reserved)

    reset(first_pair)
    tampered = bytearray(first_pair[1])
    put(tampered, 4, other)  # Same CRC as the selected approved sector.
    carrier.write_bytes(tampered)
    verify('same-crc-substituted-approval', first, error=7)
    reset(first_pair)
    tampered = bytearray(first_pair[0])
    put(tampered, HEADER + 3, other)
    witness.write_bytes(tampered)
    verify('same-crc-substituted-witness', first, error=7)
    reset(first_pair)
    exhausted = replace(first, generation=0xfffffffe)
    tampered = bytearray(first_pair[0])
    put(tampered, HEADER, witness_header(exhausted, original))
    witness.write_bytes(tampered)
    boot('one-generation-left', [TITLE, ui['A_MENU'], 'REVIEW STATUS 8', BLOCK],
         [(ui['A_MENU'], 'r', None, False)], [], [])
    return dict(captures=captures, cases=records, manual_media={name: sha256(out / name) for name in names})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path)
    args = parser.parse_args()
    exe = shutil.which(args.qemu)
    if not exe:
        raise ValueError('QEMU not found')
    exe = Path(exe).resolve()
    bios = (args.bios or exe.parent.parent / 'share/seabios/bios-256k.bin').resolve()
    src = ROOT / 'build' / output_name('rescue', args.language)
    out = ROOT / 'build' / ('mbr-review-test' if args.language == 'en' else 'mbr-review-test-de')
    prepare_output(out)
    report = out / 'review-results.json'
    for name in ('mbr-review.img', 'mbr-original-data.img', 'mbr-review-hdd.img', report.name):
        (out / name).unlink(missing_ok=True)
    manifest = json.loads((src / 'manifest.json').read_text())
    check_build_inputs(manifest, ROOT)
    for name in ('mbr-review.img', 'mbr-review.bin', 'mbr-original.img', 'mbr-original.bin',
                 'mbr-original-data.img', 'mbr-original-hdd.img', 'int13-reserve.rom',
                 'int13-20.rom', 'int13-21.rom', 'int13-22.rom'):
        if sha256(src / name) != manifest['artifacts'][name]['sha256']:
            raise ValueError('Changed approval fixture: ' + name)
    (out / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
    with tempfile.TemporaryDirectory() as tmp:
        result = campaign(exe, bios, src, out, Path(tmp), manifest, args.language)
    check_build_inputs(manifest, ROOT)
    result.update(ui=manifest['ui'], build_inputs=manifest['build_inputs'], qemu_sha256=sha256(exe),
                  bios_sha256=sha256(bios))
    report.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
