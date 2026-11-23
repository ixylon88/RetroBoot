# Transaction journal: record and observation model

The journal model is the next prerequisite for a recoverable primary-partition
visibility switch. It decodes complete old/new MBR snapshots, checks the two
journal slots as a pair, and compares the selected transaction with a supplied
current MBR. It performs no disk access and grants no write or OS-start authority.

The model is now used by the [F8/Enter diagnosis](JournalDiagnosis.md).
The released images contain two preallocated three-sector journal slots and
an empty EDD baseline. The eight-file allocation auditor supplies a checked,
fragmentation-aware sector map. The reader binds all identity records, reads
the complete journal pair and checks the current MBR again. The independent
rescue diskette can complete the first switch once the intended, approved MBR
is active. It can repair a partially written new snapshot in the completion
slot and publish the header. See [journal recovery](JournalRecovery.txt).

## Three-sector record, version 1

Each future preallocated slot holds exactly 1,536 bytes. The first sector is a
header; the next two contain all 512 bytes of the original and intended MBR.
A completion record occupies the other slot, as required by specification v0.2.
It repeats the same snapshots and sequence with phase `committed`.

All integers are unsigned little-endian. The three CRC32 fields use the same
algorithm as the configuration/state records and Python `zlib.crc32`. They
detect corruption and are not authentication or a durability guarantee.

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | `RBTXN` followed by three zero bytes |
| 8 | 2 | Version `1` |
| 10 | 2 | Header length `512` |
| 12 | 4 | Total length `1536` |
| 16 | 4 | Nonzero sequence; monotonically increasing, never wrapping |
| 20 | 4 | Disk ID |
| 24 | 4 | Canonical `RBL1` layout CRC, excluding visibility changes |
| 28 | 4 | Hidden management-volume start LBA |
| 32 | 4 | Management-volume sector count |
| 36 | 2 | Phase: `0` empty baseline, `1` prepared, `2` committed |
| 38 | 2 | BIOS route: `1` EDD, `2` CHS |
| 40 | 8 | Reachable sector count, low/high 32-bit words |
| 48 | 16 | Nonzero management-media identity |
| 64 | 4 | CRC32 of the complete old MBR at offset 512 |
| 68 | 4 | CRC32 of the complete new MBR at offset 1024 |
| 72 | 2 | CHS heads; zero for EDD |
| 74 | 2 | CHS sectors per track; zero for EDD |
| 76 | 432 | Reserved zero |
| 508 | 4 | CRC32 of header bytes 0–507 |
| 512 | 512 | Complete old MBR, including signature |
| 1024 | 512 | Complete new MBR, including signature |

The header CRC protects both snapshot CRC fields, so all 1,536 bytes are covered.
An empty baseline has sequence `1` and identical snapshots. Prepared/committed
records have sequence at least `2` and a real visibility change. An already
matching view needs no MBR transaction. Sequence exhaustion requires explicit
maintenance; neither wraparound nor an implicit reset is accepted.

## Context and protected bytes

The decoder requires an independently validated complete partition scan, the
hidden logical management entry, media identity and BIOS reachability/geometry.
It does not discover or authenticate that context. The layout CRC includes the
EBR addresses and all data extents; hidden primary types are normalized, and
active flags are excluded, exactly as in the existing configuration format.

Header identity and geometry must match this context exactly. EDD stores no
invented CHS values. CHS requires 1–256 heads, 1–63 sectors/track, an integral
number of cylinders and at most 1,024 cylinders. A route, capacity or geometry
change blocks the record; a record cannot silently authorize a new translation.

Both MBR snapshots must retain the disk ID, RBM1 management pointer and `55 AA`
signature. All four primary slots must match the validated layout's slot,
normalized type, start and length. Empty entries remain entirely zero; extended
entries remain inactive. At most one primary is active. A nonempty transaction's
intended MBR must have exactly one active, visible data primary.

Only type and active-flag bytes of supported data primaries may differ between
the snapshots. A type change must be the corresponding visible/hidden variant
of FAT16, FAT32 or NTFS. Boot code, loader pointer, disk signature, reserved
bytes, CHS fields, starts, lengths, empty slots and the extended container must
remain byte-identical. The journal does not decide which profile may select a
visible group: fresh F5/F6/F7 policy and original-OS authorization remain separate.

## Pair rules and observations

Both copies must be readable and fully valid before a transaction is selected.
One damaged copy produces `degraded`; two unusable copies produce `unavailable`.
There is no fallback to an older valid completion, because the unreadable slot
may contain a newer prepared switch. Both outcomes clear the selected sequence,
phase, snapshot CRCs, change mask and observation; per-copy reasons remain.

| Valid pair | Selection |
| --- | --- |
| Identical sequence, phase and all bytes | Copy A; duplicate evidence is consistent |
| Same sequence, one prepared and one committed, identical complete snapshots | The committed copy |
| Newer prepared record immediately following an empty/committed record | Newer copy, only if its old MBR exactly equals the older copy's new MBR |
| Any other pairing | Conflict; no selected record |

The predecessor test is byte-for-byte, not a CRC-only comparison. Skipped
sequences, two different pending transactions, a completion without its matching
prepare, equal-sequence contradictions and implicit sequence resets conflict.
The initial seed/prepared and prepared/committed pairs work in either slot order.

The selected record is compared with the complete supplied current MBR:

| Observation | Meaning |
| --- | --- |
| `BASELINE` | Empty journal and current MBR equal the baseline |
| `PREPARED_OLD` | Prepared transaction and current MBR equal its old snapshot |
| `PREPARED_NEW` | Prepared transaction and current MBR equal its new snapshot; no matching completion is present |
| `COMMITTED_NEW` | Consistent completion evidence and current MBR equal the new snapshot |
| `DIVERGED` | Any other relation, including an old MBR beside a committed transaction |
| `UNOBSERVED` | No record selected because input/pair validation failed |

These are observations of bytes and record claims, not proof of historical
write ordering. `PREPARED_OLD` does not prove that a write was never attempted;
`COMMITTED_NEW` does not prove that caches reached durable storage. A valid
pair can still produce `DIVERGED`. No observation supplies an automatic
rollback, roll-forward, repair, countdown, write lease or OS-start decision.

Record status codes are `0` valid, `1` missing, `2` format, `3` CRC,
`4` identity, `5` geometry, `6` snapshot/layout and `7` forbidden delta.
Pair status adds `8` unavailable, `9` degraded and `10` conflict. Status zero
means successful parsing/pair selection; the separate observation still matters.

## Native evidence and next integration

`make hdd-test` includes the journal model through both BIOS read routes.
The native model prints `T=007E` and `RB JOURNAL MODEL PASS`: 126 assertions
cover literal host-to-C16 vectors, reserved fields, identities, geometry,
protected MBR bytes, all observations, both slot orders, sequence exhaustion,
stale-result cleanup and all six partial three-sector replacement combinations.
The pure model has no sector-reader or writer callback and retains no input
pointers or static scratch. Four host tests check literal offsets/CRCs, the
native vector, coverage of every record byte, fixture transitions and rejected
inputs. The full boot suite now has 104 cases and 47 identical EDD/CHS pairs.

`tools/journal_records.py` creates only owned in-memory vectors and newly
generated fixture allocations/baselines. It is not an import command or
installer. The model is linked into the released diagnosis and native tests.
Test-only startup/model variants omit unused menu code and its private scratch;
they retain the same core implementations and existing file/stack budgets.

The [diagnosis guide](JournalDiagnosis.md) specifies the bounded reader,
42 native reader assertions, 495 UI states per language, manual check and
remaining limitations. F10 now recognizes all eight files. External rescue
covers the completion snapshot and header of the first switch. Earlier
interruption points and the normal switch still require recovery and write tests.
