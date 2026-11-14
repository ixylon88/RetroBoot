"""Independent address oracle for the owned native target-comparison fixture."""

ASSERTIONS = 178


def expected_reads():
    # The native fixture has one sector per cluster, a contiguous 5,000-byte
    # Stage 2, four scattered records and two fragmented journal allocations.
    reads = [0, 0, 63, 126, 379, 380]
    chains = ([2, 3, 4], list(range(20, 30)), [2800], [2900], [3000], [3100],
              [3200, 3202, 3204], [3300, 3302, 3304])
    cached = None
    for chain in chains:
        for cluster in chain:
            index = cluster // 256
            if index != cached:
                reads.extend((127 + index, 253 + index))
            cached = index
    reads.extend(lba for index in range(126) for lba in (127 + index, 253 + index))
    reads.extend((3209, 3309, 3409, 3509, 0))
    return reads * 2


def check_reads(actual):
    if actual != expected_reads():
        raise ValueError('Target model metadata addresses or acquisition order differ')
