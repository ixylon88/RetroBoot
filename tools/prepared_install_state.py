"""Persist the recovery-required installation phase on an unpublished disk copy."""
from dataclasses import replace
import zlib

try:
    from . import state_records
    from .prepare_dos_disk import dword
    from .prepared_records import STATE, check_configuration, read_records, select_generation, write_sector
except ImportError:
    import state_records
    from prepare_dos_disk import dword
    from prepared_records import STATE, check_configuration, read_records, select_generation, write_sector


READY = state_records.PHASES.index('ready') + 1
RECOVERY = state_records.PHASES.index('recovery_required') + 1


def state_record(records, entry, generation, phase):
    if phase not in (READY, RECOVERY):
        raise ValueError('Unsupported installation phase for this operation')
    crc = zlib.crc32(records.vbr) if phase == READY else 0
    return state_records.encode(**records.binding, generation=generation,
                                installations=[dict(entry, phase=phase, vbr_crc=crc)])


def inspect_state(disk):
    records = read_records(disk)
    # Both config copies and the idle journal independently bind this identity.
    entry = dict(records.target, install_id=int.from_bytes(records.config[0][108:116], 'little'))
    check_configuration(records.config, records.binding, entry)
    a, b = records.state
    # The writer can change only generation, phase, prior VBR claim and CRC.
    if a[:16] != b[:16] or a[20:83] != b[20:83] or a[88:508] != b[88:508]:
        raise ValueError('Installation copies disagree outside the transition fields')
    valid = []
    for index, data in enumerate(records.state):
        if dword(data, 508) == zlib.crc32(data[:508]):
            if data != state_record(records, entry, dword(data, 16), data[83]):
                raise ValueError('Installation state does not match this prepared DOS disk')
            valid.append(index)
    if not valid:
        raise ValueError('Both installation checksums failed')
    if len(valid) == 1:
        return records, entry, valid[0], True
    active = select_generation(records.state, 'installation')
    if records.state[1 - active][83] == RECOVERY and records.state[active][83] == READY:
        raise ValueError('Unexpected transition out of recovery')
    return records, entry, active, False


def require_recovery(disk, language):
    records, entry, source, damaged = inspect_state(disk)
    target = 1 - source
    current = records.state[source]
    generation = dword(current, 16)
    german = language == 'de'
    if current[83] == RECOVERY and not damaged:
        print('Die Startsperre ist bereits gespeichert.' if german else 'Boot is already blocked.')
        return None
    # A surviving recovery record can restore its peer even at the counter limit.
    if current[83] == READY:
        if generation == 0xffffffff:
            raise ValueError('Installation generation exhausted')
        next_record = state_record(records, entry, generation + 1, RECOVERY)
    else:
        next_record = current
    lba = records.files[STATE[target]][0]
    source_name, target_name = ('RBSTATE.' + 'AB'[i] for i in (source, target))
    profile = records.config[0]
    name = profile[84:84 + profile[82]].decode('cp437')
    print(f'{name}  P{entry["slot"]}  ID 0x{entry["install_id"]:016X}')
    label = 'Generation' if german else 'generation'
    print(f'{source_name}  {label} {generation}  {state_records.PHASES[current[83] - 1]}')
    if damaged:
        print(f'{target_name} hat einen Prüfsummenfehler.' if german else f'{target_name} has a checksum error.')
    print(f'{target_name}  LBA 0x{lba:08X}  {label} {dword(next_record, 16)}  recovery_required')
    try:
        reply = input('DOS-Start auf der neuen Kopie sperren? [j/N] ' if german else
                      'Block DOS boot on the new copy? [y/N] ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        reply = ''
    if reply != ('j' if german else 'y'):
        raise ValueError('Abgebrochen.' if german else 'Cancelled.')
    if inspect_state(disk)[0] != records:
        raise ValueError('Disk changed before the installation update')
    write_sector(disk, lba, next_record)
    expected = list(records.state)
    expected[target] = next_record
    after, _, selected, degraded = inspect_state(disk)
    expected_source = 0 if current[83] == RECOVERY else target
    if degraded or selected != expected_source or after != replace(records, state=tuple(expected)):
        raise ValueError('Installation-state readback failed')
    return records.geometry
