"""Boot with an independently identified secondary IDE master as the recovery carrier."""
import shutil
import zlib

from build_rescue import sha256
from mbr_boot import boot_fixture
from mbr_restart_fixtures import Checkpoint, EMPTY, ORIGIN, header, label, put, seal, sector_body
from prepare_mbr_target import prepare_pair
from rescue_text import load_catalog
from test_mbr_ata_history import HEADER, main
from test_mbr_reservation import fault_rom
from test_mbr_target import BLOCK, MODEL, PASS, SECTORS, SERIAL, disk_fields

BACKUP = 'VB71717171-11111111'
OTHER = 'VB71717171-22222222'
MEDIA = ('mbr-target.img', 'mbr-recovery.img')
IDS = tuple(b'RB-RECOVERY-IDE' + bytes((i,)) for i in (1, 2, 3))


def recovery_fields(ui, title, model, serial, sectors):
    return [ui[title], ui['D_MODEL'] + ' ' + model, ui['D_SERIAL'] + ' ' + serial,
            ui['D_REC_CAP'] + f' 0x{sectors:016X}']


def campaign(exe, bios, src, work, out, manifest, language):
    ui = load_catalog(language)
    start, backup = (work / name for name in MEDIA)
    source = work / 'source.raw'
    blank, disk_label = prepare_pair((src / 'mbr-target.img').read_bytes(), MODEL, SERIAL, SECTORS,
                                    *IDS, recovery=(MODEL, BACKUP, SECTORS))
    virgin = disk_label + bytes((SECTORS - 1) * 512)
    old, new = sector_body(0), sector_body(2)
    assert new != old and zlib.crc32(old) == zlib.crc32(new)
    source.write_bytes(old + bytes((SECTORS - 1) * 512))
    start.write_bytes(blank)
    backup.write_bytes(virgin)
    fixture = dict(binary=(src / 'mbr-target.bin').read_bytes(), memory=manifest['memory']['mbr-target'])
    menu = ['RB ATA TARGET', ui['D_BOTH'], ui['D_FIRST']]
    expected = menu + disk_fields(ui, 'D_EXPECT', MODEL, SERIAL, SECTORS)
    live = expected + disk_fields(ui, 'D_LIVE', MODEL, SERIAL, SECTORS) + ['TARGET MATCH']
    intended = recovery_fields(ui, 'D_REC_EXPECT', MODEL, BACKUP, SECTORS)
    attached = recovery_fields(ui, 'D_REC_LIVE', MODEL, BACKUP, SECTORS)
    present = intended + attached + ['RECOVERY MATCH']
    cases = []

    def run(name, screen, actions, writes=(), samples=0, *, src_disk=source, rec_disk=backup, serial=BACKUP,
            source_serial=SERIAL, cut_rom=None, readonly=False, expected_reads=None):
        images = {p: bytearray(p.read_bytes()) for p in (start, backup)}
        for p, lba, data in writes:
            put(images[p], lba, data)
        source_hash = sha256(source)
        result = boot_fixture(exe, bios, fixture, work, start, src_disk, name, screen, actions,
                              [n for _, n, _ in writes], [0] * samples, rom=cut_rom, cut=bool(cut_rom),
                              readonly_start=readonly, ata_identity=(MODEL, source_serial), recovery_disk=rec_disk,
                              recovery_identity=(MODEL, serial), recovery_writes=[n for p, n, _ in writes if p == backup])
        if any(p.read_bytes() != data for p, data in images.items()) or sha256(source) != source_hash:
            raise ValueError(f'{name}: unexpected persistent changes')
        if expected_reads is not None and result.get('ide_read_lbas', result['hdd_read_lbas']) != expected_reads:
            raise ValueError(f'{name}: read an unexpected sector before endpoint agreement')
        result.update(source_attached=src_disk is not None, recovery_attached=rec_disk is not None,
                      media_sha256={p.name: sha256(p) for p in images})
        cases.append(result)
        print(f'{name}: ' + ('POWER CUT' if cut_rom else screen[-1]), flush=True)

    def key(field, value):
        return (ui[field], value, None, False)

    def metadata(tag, point):
        return header(tag, point, IDS[1], target_id=IDS[0], capacity=SECTORS)

    def verify(name, point=None, error=0, disk=None):
        outcome = [f'REVIEW STATUS {error}', BLOCK] if error else [
            'ORIGINAL REV 1 VERIFIED', f'APPROVED REV {point.approved}' if point.approved else
            'APPROVED NONE', f'LAST ISSUED {point.issued}', PASS]
        run(name, expected + present + outcome, [key('D_FIRST', 'v')], src_disk=disk, readonly=True)

    run('both-identified', live + present + [PASS], [key('D_FIRST', 'p')], expected_reads=[0])
    run('source-missing', expected + [ui['D_ABSENT'], BLOCK], [key('D_FIRST', 'e')], src_disk=None,
        expected_reads=[])
    run('disk-at-wrong-port', expected + intended + [ui['D_REC_ABSENT'], BLOCK], [key('D_FIRST', 'v')],
        src_disk=backup, source_serial=BACKUP, rec_disk=None, expected_reads=[])
    run('swapped-source', expected + disk_fields(ui, 'D_LIVE', MODEL, BACKUP, SECTORS) + [ui['D_WRONG'], BLOCK],
        [key('D_FIRST', 'r')], src_disk=backup, rec_disk=source, source_serial=BACKUP, serial=SERIAL, expected_reads=[])
    wrong = intended + recovery_fields(ui, 'D_REC_LIVE', MODEL, OTHER, SECTORS) + [ui['D_REC_WRONG'], BLOCK]
    for cmd in ('e', 'r', 'v'):
        run('copied-carrier-' + cmd, (expected if cmd == 'v' else live) + wrong, [key('D_FIRST', cmd)],
            serial=OTHER, expected_reads=[])
    with backup.open('r+b') as stream:
        stream.truncate((SECTORS + 1) * 512)
    run('resized', expected + intended + recovery_fields(ui, 'D_REC_LIVE', MODEL, BACKUP, SECTORS + 1) +
        [ui['D_REC_WRONG'], BLOCK], [key('D_FIRST', 'v')], expected_reads=[])
    backup.write_bytes(label(IDS[0]) + virgin[512:])
    run('right-device-wrong-label', live + intended + attached + [ui['D_REC_LABEL'], BLOCK],
        [key('D_FIRST', 'e')], expected_reads=[0])
    backup.write_bytes(virgin)
    for offset, data in [(124, blank[-464:-444]), (192, b'X')]:
        profile = bytearray(blank[-512:])
        profile[offset:offset + len(data)] = data
        start.write_bytes(blank[:-512] + seal(profile))
        run(f'invalid-profile-{offset}', ['RB ATA TARGET', ui['D_PROFILE'], BLOCK], [], expected_reads=[])
    start.write_bytes(blank)
    verify('blank-witness', error=4)
    for action, field in [('e', 'D_REC_FIRST'), ('r', 'D_REC_REVIEW')]:
        run('cancel-' + action, live + present + [ui[field], PASS], [key('D_FIRST', action), key(field, 'esc')],
            expected_reads=[0])

    enroll_screen = live + present + [ui['D_REC_FIRST']]
    enroll_keys = [key('D_FIRST', 'e'), key('D_REC_FIRST', 'e')]
    enroll = [(backup, 2, old), (backup, 1, metadata(b'RBORG001', ORIGIN)), (backup, 3, metadata(b'RBCMT001', ORIGIN)),
              (start, HEADER + 1, old), (start, HEADER, metadata(b'RBWIT001', ORIGIN))]
    done = ['INITIAL WITNESS PUBLISHED', PASS]
    managed = bytearray(old)
    managed[432:436] = b'RBM1'
    with source.open('r+b') as stream:
        stream.write(managed)
    run('managed-mbr-before-first-capture', enroll_screen + ['REVIEW STATUS 8', BLOCK], enroll_keys, samples=1)
    with source.open('r+b') as stream:
        stream.write(old)
    # The ROM only interrupts floppy writes. The three ATA records have already been flushed.
    rom = fault_rom(src / 'int13-reserve.rom', work / 'cut.rom', 2, 1)
    run('before-first-witness-header', enroll_screen, enroll_keys, enroll[:-1], 6, cut_rom=rom)
    verify('unpublished-after-power-cut', error=4)
    run('resume-first-capture', enroll_screen + done, enroll_keys, enroll[-1:], 5)
    verify('resumed-original', ORIGIN)
    start.write_bytes(blank)
    backup.write_bytes(virgin)

    # A failed drive flush cannot publish the immutable original header or the witness.
    injection = work / 'failed-flush.conf'
    injection.write_text('[inject-error]\nevent = "flush_to_disk"\nerrno = "5"\nonce = "on"\n')
    run('failed-recovery-flush', enroll_screen + ['REVIEW STATUS 9', BLOCK], enroll_keys, enroll[:1], 2,
        rec_disk=f'blkdebug:{injection}:{backup}')
    verify('failed-flush-detached', error=4)
    backup.write_bytes(virgin)
    run('first-capture', enroll_screen + done, enroll_keys, enroll, 6)
    verify('original-with-source-absent', ORIGIN)
    first = start.read_bytes(), backup.read_bytes()
    with source.open('r+b') as stream:
        stream.write(new)
    reserved, approved = Checkpoint(2, 2), Checkpoint(3, 2, 2)
    changes = [(i, a, b) for i, (a, b) in enumerate(zip(old, new)) if a != b]
    review_screen = live + present + [ui['D_REC_REVIEW'], ui['A_TARGET'] + ' ' + IDS[0].hex(' ').upper(),
        ui['A_CARRIER'] + ' ' + IDS[1].hex(' ').upper(), ui['A_SECTORS'] + f' 0x{SECTORS:016X}',
        'REVIEW 2', 'BASE REV 1', f'CHANGED BYTES {len(changes)}', ui['A_DIFF']]
    review_screen += [f'0x{i:04X}     {a:02X} -> {b:02X}' for i, a, b in changes] + [ui['A_DECIDE']]
    review_keys = [key('D_FIRST', 'r'), key('D_REC_REVIEW', 'r')]
    accept = review_keys + [key('A_DECIDE', ui['A_YES'].lower())]
    writes = [(backup, 6, EMPTY), (backup, 5, metadata(b'RBCMT001', reserved)),
              (start, HEADER, metadata(b'RBWIT001', reserved)), (backup, 4, new),
              (backup, 3, metadata(b'RBCMT001', approved)), (start, HEADER + 3, new),
              (start, HEADER, metadata(b'RBWIT002', approved))]
    run('rejected', review_screen + ['REVIEW REJECTED', PASS], review_keys + [key('A_DECIDE', 'esc')], writes[:3], 1)
    verify('rejected-detached', reserved)
    start.write_bytes(first[0])
    backup.write_bytes(first[1])
    rom = fault_rom(src / 'int13-reserve.rom', work / 'cut.rom', 3, 1)
    run('before-approval-header', review_screen, accept, writes[:-1], 3, cut_rom=rom)
    verify('staged-approval-detached', reserved)
    start.write_bytes(first[0])
    backup.write_bytes(first[1])
    run('approve', review_screen + ['APPROVED REV 2', PASS], accept, writes, 3)
    saved = backup.read_bytes()
    backup.write_bytes(first[1])
    verify('stale-backup', error=6)
    backup.write_bytes(saved[:4 * 512] + old + saved[5 * 512:])
    verify('same-crc-substitution', error=7)
    backup.write_bytes(saved)
    run('approved-copy-foreign-serial', expected + wrong, [key('D_FIRST', 'v')], serial=OTHER,
        src_disk=None, readonly=True, expected_reads=[])
    verify('approved-with-source-present', approved, disk=source)
    verify('approved-with-source-absent', approved)
    for path in (start, backup):
        shutil.copyfile(path, out / path.name)
    return dict(cases=cases, manual_media={n: sha256(out / n) for n in MEDIA})


if __name__ == '__main__':
    main(campaign, 'mbr-review-test-recovery', 'recovery-disk-results.json', MEDIA)
