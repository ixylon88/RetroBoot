"""Check HDD profile switching with a third physical primary outside the configuration."""
import argparse
from pathlib import Path
import shutil
import tempfile
import zlib

import config_records
import state_records
from build_hdd import ROOT, SECTOR, write_fixture
from handoff_fixtures import IMAGE_BYTES
from test_dos_countdown import boot, compare
from test_profile_menu import make_fixture, package_disks, preview, put
from test_profile_switch import change, cold, confirm, review, select
from ui_text import LANGUAGES, load_catalog, output_name


def configure_profiles(disk, language, third='ready', *, count=2):
    """Keep all physical volumes and enroll the selected leading profiles in both copies."""
    profiles = disk.profiles[:count]
    config = config_records.encode(**disk.binding, profiles=profiles, language=language, default_id=profiles[0]['id'])
    installs = []
    for p in disk.profiles:
        if p['slot'] == 3 and third == 'absent':
            continue
        if p['slot'] == 3 and third == 'planned':
            installs.append(dict(p, phase=1))
        else:
            installs.append(dict(p, phase=6, vbr_crc=zlib.crc32(disk.extents[p['start'] * SECTOR])))
    state = state_records.encode(**disk.binding, installations=installs)
    records = {**dict.fromkeys(disk.config_at, config), **dict.fromkeys(disk.state_at, state)}
    disk.extents.update(records)
    put(disk.raw, records)


def refuse_active(qemu, bios, work, disk, ui, image, case):
    with boot(qemu, bios, work, image, case) as menu:
        if any(disk.profiles[2]['name'] in row for row in menu.screen()):
            raise ValueError('Unregistered P3 appeared in the startup menu')
        select(menu, 2)
        menu.key('ret', 12)
        menu.expect(ui['DOS_SCOPE'])
        menu.expect(ui['DOS_UNMANAGED'])
        if menu.screen()[10][33:37] != '0x04':
            raise ValueError('Unregistered P3 was missing from the refusal mask')
        menu.key('s', 12)
        menu.key('ret', 12)
        menu.key('esc', 0)
        if 'RB HANDOFF' in menu.log.read_text():
            raise ValueError('A refused switch transferred control')


def run(language, qemu, bios):
    directory = ROOT / 'build' / output_name('hdd', language)
    ui = load_catalog(language)
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        (work / 'events.txt').write_text('ide_sector_read\nide_sector_write\nblk_co_pwritev\n')
        active = make_fixture(work, directory, language, 3, 3, mixed=True)
        hidden = make_fixture(work, directory, language, 1, 3, mixed=True)
        configure_profiles(active, language)
        configure_profiles(hidden, language, 'absent')
        name = 'RetroBoot-Profilschutz-DE.zip' if language == 'de' else 'RetroBoot-Profile-Scope-EN.zip'
        roles = ('aktiv', 'verborgen') if language == 'de' else ('active', 'hidden')
        images = [(disk, f'P3-{role}.vdi', f'profile-scope-{language}-{role}')
                  for disk, role in zip((active, hidden), roles, strict=True)]
        bundle, (blocked, allowed) = package_disks(work, name, images)
        refuse_active(qemu, bios, work, active, ui, blocked, 'active-p3-ready')
        compare(blocked, active.raw)
        for phase in ('planned', 'absent'):
            configure_profiles(active, language, phase)
            refuse_active(qemu, bios, work, active, ui, active.raw, 'active-p3-' + phase)

        expected = work / 'expected.raw'
        first = change(hidden, hidden.extents, 2, 2, 1)
        second = change(hidden, first.after, 1, 3, 1)
        for step in (first, second):
            with boot(qemu, bios, work, allowed, f'scoped-switch-{step.target}',
                      [at // SECTOR for at, _ in step.rows]) as menu:
                review(menu, hidden, step, ui)
                confirm(menu, hidden, step)
            write_fixture(expected, IMAGE_BYTES, step.after)
            compare(allowed, expected)
            cold(qemu, bios, work, allowed, hidden, step, f'scoped-cold-{step.target}')

        # A settled P3-to-P1 predecessor predates the reduced configuration.
        # P1 still boots, but its history cannot authorize another journal rotation.
        p3 = change(hidden, hidden.extents, 3, 2, 1)
        prior = change(hidden, p3.after, 1, 3, 1)
        write_fixture(hidden.raw, IMAGE_BYTES, prior.after)
        cold(qemu, bios, work, hidden.raw, hidden, prior, 'scope-old-history-cold')
        with boot(qemu, bios, work, hidden.raw, 'scope-old-history-review') as menu:
            select(menu, 2)
            menu.key('ret', 8)
            preview(menu, ui, 1, 2, hidden)
            menu.key('s', 18)
            menu.expect(ui['SWITCH_HISTORY'])
        shutil.copyfile(bundle, directory / bundle.name)
        print(f'{language}: {name} passed both shipped VDI checks', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', choices=LANGUAGES, default='en')
    parser.add_argument('--qemu', default='qemu-system-i386')
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    args = parser.parse_args()
    run(args.language, args.qemu, args.bios)
