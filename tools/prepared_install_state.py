"""Block or explicitly approve a verified installation on an unpublished disk copy."""
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
VERIFY = state_records.PHASES.index('verification_required') + 1


def state_record(records, entry, generation, phase):
    if phase not in (READY, RECOVERY, VERIFY):
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
    transition = records.state[1 - active][83], records.state[active][83]
    # The first approval write follows READY -> hold -> trial, with generation
    # 1 the earliest possible starting point. The mirror write follows readback.
    approved = transition == (VERIFY, READY) and dword(records.state[1 - active], 16) >= 3
    if not approved and transition not in ((READY, READY), (READY, RECOVERY), (RECOVERY, RECOVERY),
                                           (RECOVERY, VERIFY), (VERIFY, RECOVERY)):
        raise ValueError('Unexpected installation-state transition')
    return records, entry, active, False


def confirm(prompt, language):
    try:
        reply = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        reply = ''
    if reply != ('j' if language == 'de' else 'y'):
        raise ValueError('Abgebrochen.' if language == 'de' else 'Cancelled.')


def show_installation(records, entry):
    profile = records.config[0]
    name = profile[84:84 + profile[82]].decode('cp437')
    print(f'{name}  P{entry["slot"]}  ID 0x{entry["install_id"]:016X}')


def save_state_record(disk, before, target, sector):
    if inspect_state(disk)[0] != before:
        raise ValueError('Disk changed before the installation update')
    write_sector(disk, before.files[STATE[target]][0], sector)
    expected = list(before.state)
    expected[target] = sector
    after, _, selected, damaged = inspect_state(disk)
    if (damaged or after != replace(before, state=tuple(expected))
            or selected != select_generation(expected, 'installation')):
        raise ValueError('Installation-state readback failed')
    return after


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
    if current[83] != RECOVERY:
        if generation == 0xffffffff:
            raise ValueError('Installation generation exhausted')
        next_record = state_record(records, entry, generation + 1, RECOVERY)
    else:
        next_record = current
    lba = records.files[STATE[target]][0]
    source_name, target_name = ('RBSTATE.' + 'AB'[i] for i in (source, target))
    show_installation(records, entry)
    label = 'Generation' if german else 'generation'
    print(f'{source_name}  {label} {generation}  {state_records.PHASES[current[83] - 1]}')
    if damaged:
        print(f'{target_name} hat einen Prüfsummenfehler.' if german else f'{target_name} has a checksum error.')
    print(f'{target_name}  LBA 0x{lba:08X}  {label} {dword(next_record, 16)}  recovery_required')
    confirm('DOS-Start auf der neuen Kopie sperren? [j/N] ' if german else
            'Block DOS boot on the new copy? [y/N] ', language)
    save_state_record(disk, records, target, next_record)
    return records.geometry


def confirm_verification(disk, reference, language):
    """Bind the post-trial disk to the retained READY sector and the operator's observation."""
    current, entry, _, damaged = inspect_state(disk)
    witness, _, latest, degraded = inspect_state(reference)
    if damaged or degraded:
        raise ValueError('Verification approval requires two healthy copies on each disk')
    if current != replace(witness, state=current.state):
        raise ValueError('The reference and tested disk differ in identity, layout, configuration or DOS boot sector')

    # A retained hold has exactly the READY sector consumed by the trial.
    # A retained original READY pair also predates the hold created by the host.
    retained = witness.state[latest]
    if retained[83] == RECOVERY:
        trial_slot = 1 - latest
    elif retained[83] == READY and witness.state[0] == witness.state[1]:
        trial_slot = latest
    else:
        raise ValueError('A reference from before the verification boot is required')
    old_ready = witness.state[trial_slot]
    generation = dword(old_ready, 16)
    if old_ready[83] != READY:
        raise ValueError('Reference lacks the preceding verified DOS boot sector')
    if generation > 0xfffffffc:
        raise ValueError('Installation generation exhausted')
    hold = state_record(current, entry, generation + 1, RECOVERY)
    if retained[83] == RECOVERY and retained != hold:
        raise ValueError('Reference recovery hold does not follow the verified READY record')

    pending = state_record(current, entry, generation + 2, VERIFY)
    ready = state_record(current, entry, generation + 3, READY)
    other = 1 - trial_slot
    german = language == 'de'
    if current.state == (ready, ready):
        print('Diese Freigabe ist bereits gespeichert.' if german else 'This approval is already recorded.')
        return None
    if current.state[trial_slot] != pending or current.state[other] != hold:
        raise ValueError('The disk does not contain the exact pending trial and its original recovery hold')

    show_installation(current, entry)
    label = 'Generation' if german else 'generation'
    print(f'READY  {label} {generation}  VBR CRC32 0x{dword(old_ready, 84):08X}')
    print(f'RBSTATE.{"AB"[trial_slot]}  {label} {generation + 2}  verification_required')
    for slot in (other, trial_slot):
        print(f'RBSTATE.{"AB"[slot]}  LBA 0x{current.files[STATE[slot]][0]:08X}  {label} {generation + 3}  ready')
    delay = current.config[select_generation(current.config, 'configuration')][38]
    print(f'Gespeicherte DOS-Wartezeit: {delay} s' if german else f'Saved DOS boot delay: {delay} s')
    confirm('Prüfstart und Rückkehr zu RetroBoot erfolgreich? Normalen Start auf der neuen Kopie freigeben? [j/N] '
            if german else 'Did the trial boot and return to RetroBoot succeed? Enable normal boot on the new copy? [y/N] ',
            language)

    # Both writes are on the private output. The second gives existing F9/menu
    # and countdown tools their identical READY pair. The source keeps phase 5.
    def check_reference():
        if read_records(reference) != witness:
            raise ValueError('Reference changed during verification approval')

    check_reference()
    for slot in (other, trial_slot):
        current = save_state_record(disk, current, slot, ready)
        check_reference()
    return current.geometry
