"""Update or recover the countdown on a private copy of a prepared DOS disk."""
from dataclasses import dataclass, replace
import struct
import zlib

try:
    from . import config_records, state_records
    from .prepare_dos_disk import dword, word
    from .prepared_records import CONFIG, JOURNAL, STATE, check_configuration, management_files, read_records, write_sector
except ImportError:
    import config_records
    import state_records
    from prepare_dos_disk import dword, word
    from prepared_records import CONFIG, JOURNAL, STATE, check_configuration, management_files, read_records, write_sector


@dataclass(frozen=True)
class MenuSetting:
    geometry: tuple
    lbas: tuple
    copies: tuple
    active: int
    disk_context: tuple
    needs_repair: bool


def inspect(disk, *, allow_countdown_damage=False):
    records = read_records(disk)
    state = records.state[0]
    entry = dict(records.target, install_id=int.from_bytes(state[64:72], 'little'))
    ready = state_records.encode(**records.binding, generation=dword(state, 16),
        installations=[dict(entry, phase=6, vbr_crc=zlib.crc32(records.vbr))])
    if records.state != (ready, ready):
        raise ValueError('DOS installation state or boot sector differs from its verified record')
    active, repair = check_configuration(records.config, records.binding, entry, allow_damage=allow_countdown_damage)
    context = (records.mbr, records.ebr, records.vbr, state, records.files, records.allocation)
    return MenuSetting(records.geometry, tuple(records.files[n][0] for n in CONFIG),
                       records.config, active, context, repair)


def write_inactive(disk, before, sector):
    """Recheck the reviewed disk, then replace and validate exactly one record."""
    if inspect(disk, allow_countdown_damage=before.needs_repair) != before:
        raise ValueError('Disk or setting changed before the update')
    target = 1 - before.active
    write_sector(disk, before.lbas[target], sector)
    copies = list(before.copies)
    copies[target] = sector
    # Copying the survivor produces equal peers (the firmware selects A).
    # An ordinary timer update publishes a new generation in the other slot.
    active = 0 if before.needs_repair else target
    if inspect(disk) != replace(before, copies=tuple(copies), active=active, needs_repair=False):
        raise ValueError('Configuration readback failed')
    return before.geometry


def change_countdown(disk, seconds, language):
    """Only the unpublished raw output of write_disk_copy is writable here."""
    before = inspect(disk)
    source = before.copies[before.active]
    current = word(source, 38)
    if seconds is None:
        prompt = (f'Bisher {current} s. Neue Wartezeit in Sekunden (0 = aus, 1-60, Enter = Abbruch): '
                  if language == 'de' else
                  f'Current delay {current} s. New delay in seconds (0 = off, 1-60, Enter = cancel): ')
        try:
            reply = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            reply = ''
        if not reply:
            raise ValueError('Abgebrochen.' if language == 'de' else 'Cancelled.')
        seconds = int(reply)
    if not 0 <= seconds <= 60:
        raise ValueError('Countdown must be between 0 and 60 seconds')
    if seconds == current:
        return before.geometry
    generation = dword(source, 16)
    if generation == 0xffffffff:
        raise ValueError('Configuration generation exhausted')
    edit = bytearray(source)
    struct.pack_into('<I', edit, 16, generation + 1)
    struct.pack_into('<H', edit, 38, seconds)
    return write_inactive(disk, before, config_records.seal(edit))


def recover_countdown(disk, language):
    before = inspect(disk, allow_countdown_damage=True)
    german = language == 'de'
    if not before.needs_repair:
        print('Beide Konfigurationskopien sind gültig. Keine Reparatur erforderlich.'
              if german else 'Both configuration copies are valid. No repair is needed.')
        return None

    source = before.copies[before.active]
    seconds = word(source, 38)
    generation = dword(source, 16)
    good = 'RBCFG.' + 'AB'[before.active]
    target = 1 - before.active
    bad = 'RBCFG.' + 'AB'[target]
    lba = before.lbas[target]
    if german:
        print(f'{good} ist gültig. Generation {generation}, Wartezeit {seconds} s.')
        prompt = f'{bad} hat einen Prüfsummenfehler. LBA 0x{lba:08X} in der neuen Kopie ersetzen? [j/N] '
    else:
        print(f'{good} is valid. Generation {generation}, delay {seconds} s.')
        prompt = f'{bad} has a checksum error. Replace LBA 0x{lba:08X} in the new copy? [y/N] '
    try:
        reply = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        reply = ''
    if reply != ('j' if german else 'y'):
        raise ValueError('Abgebrochen.' if german else 'Cancelled.')
    return write_inactive(disk, before, source)
