"""Independent whole-extent CRCs and read oracles for the payload observer."""
import struct
import zlib

try:
    from .backup_plan_vectors import (
        HEADERS, PASS, SYSTEM, cases as plan_cases, expected_reads as plan_reads,
        model_header as plan_header, sectors,
    )
    from .rescue_match_fixtures import RECORDS
except ImportError:
    from backup_plan_vectors import (
        HEADERS, PASS, SYSTEM, cases as plan_cases, expected_reads as plan_reads,
        model_header as plan_header, sectors,
    )
    from rescue_match_fixtures import RECORDS


def extents(reserved=32):
    return [(0, 0, 0, 1), (3, 0, 63, 1), (4, 0, SYSTEM, reserved),
            (4, 1, 126, 1), *[(5+i, 0, lba, 1) for i, lba in enumerate(RECORDS)]]


def payload_reads(reserved=32):
    return [lba+i for _, _, lba, count in extents(reserved) for i in range(count)]


PAYLOAD_PASS = PASS + len(payload_reads())


def expected_reads():
    validation = plan_reads()[:PASS]
    return (validation[:-1] + payload_reads() + validation[-1:]) * 2


def check_reads(actual):
    if actual != expected_reads():
        raise ValueError('Payload observation addresses or acquisition order differ')


def case_data(case, changed=True):
    data = {lba: bytearray(block) for lba, block in sectors().items()}
    edits = case['initial'] + (case['patches'] if changed else [])
    for lba, offset, value in edits:
        struct.pack_into('<I', data.setdefault(lba, bytearray(512)), offset, value)
    return data


def payload_crcs(case):
    if case['status']:
        return [0] * 8
    data = case_data(case)
    return [zlib.crc32(b''.join(data.get(lba+i, bytes(512)) for i in range(count)))
            for _, _, lba, count in extents(case['reserved'])]


def cases():
    original = plan_cases()
    by_name = {c['name']: c for c in original}
    result = []

    def add(case, **changes):
        result.append(dict(case, stop=0, **changes))

    # Stable sources and first-pass validation failures retain the independent
    # planner's fixtures. No payload read is allowed after a validation failure.
    for case in original:
        if not case['status']:
            add(case, reads=2*(HEADERS + 2*case['reserved'] + 11))
        elif case['reads'] < PASS and case['start'] < PASS:
            add(case)
        elif case['name'].startswith('changed-') and case['name'] != 'changed-reserved-count':
            add(case, start=PAYLOAD_PASS+1, reads=PAYLOAD_PASS*2)
        elif case['name'] == 'resealed-tail-outer':
            add(case, start=PAYLOAD_PASS+1, reads=PAYLOAD_PASS*2)

    base = by_name['fat32-edd']
    for outer in (0, 1):
        at = 0
        for kind, index, lba, count in extents():
            for offset in range(count):
                call = outer*PAYLOAD_PASS + PASS + at
                add(base, name=f'payload-io-{outer}-{at}', status=10, detail=kind,
                    index=index, lba=lba+offset, reads=call, io=call)
                at += 1

    # Changes confined to the collection window are invisible to ordinary
    # whole-record CRC comparisons when a trailing CRC is also recalculated.
    for outer in (0, 1):
        for source in ('resealed-tail-outer', 'changed-reserved-tail', 'changed-ebr-chs'):
            case = dict(by_name[source], name=f'transient-{outer}-{source}',
                        start=outer*PAYLOAD_PASS+PASS, reads=PAYLOAD_PASS*2)
            add(case)
            result[-1]['stop'] = (outer+1)*PAYLOAD_PASS

    for at, name in ((PASS, 'mbr-changed-during-payload'),
                     (PAYLOAD_PASS, 'mbr-changed-after-payload')):
        add(by_name['mbr-changed-after-vbrs'], name=name, start=at, reads=at)
    add(by_name['primary-fsinfo-lead'], name='second-pass-invalid-fsinfo',
        start=PAYLOAD_PASS+1, reads=PAYLOAD_PASS+HEADERS+4)
    add(by_name['bad-reference'], name='second-pass-invalid-reference',
        start=PAYLOAD_PASS+1, reads=PAYLOAD_PASS+528)
    return result


def assertions():
    return 5*len(cases()) + 4


def model_header():
    vectors = cases()
    lines = [plan_header(vectors), 'static const rb_u32 rb_payload_crc[][8] = {']
    lines += ['    {' + ', '.join(str(crc)+'UL' for crc in payload_crcs(c)) + '},'
              for c in vectors]
    lines += ['};', 'static const rb_u16 rb_payload_stop[] = {',
              '    ' + ', '.join(str(c['stop']) for c in vectors), '};',
              '#define RB_PAYLOAD_FAILURE_CASE ' + str(next(
                  i for i, c in enumerate(vectors) if c['name'] == 'payload-io-1-38')) + 'U']
    return '\n'.join(lines) + '\n'
