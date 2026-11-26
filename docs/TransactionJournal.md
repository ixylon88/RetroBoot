# Transaction journal: record and observation model

The journal model validates the records used in a recoverable primary-partition
visibility switch. It decodes complete old/new MBR snapshots, checks the two
journal slots as a pair, and compares the selected transaction with a supplied
current MBR. It performs no disk access and grants no write or OS-start authority.

The model is now used by the [F8/Enter diagnosis](JournalDiagnosis.md).
The released images contain two preallocated three-sector journal slots and
an empty EDD baseline. The eight-file allocation auditor supplies a checked,
fragmentation-aware sector map. The reader binds all identity records, reads
the complete journal pair and checks the current MBR again. The independent
rescue diskette can apply the approved first switch when the prepare and
baseline are intact and the live MBR matches the old snapshot or an exact
new prefix followed by its old suffix. When the intended MBR is already
active, it can complete the journal snapshot and header. When both snapshots
are intact and the live MBR is still old, the diskette can also reconstruct a
missing or partly written first prepare header over its seed. It checks the
resulting physical journal pair before changing the partition table. An
earlier interruption can leave only part of the intended MBR in the journal.
The bilingual kit demonstrates discarding that copy on confirmation and
recognizing the intact baseline on restart. [First-switch recovery](JournalRecovery.txt)

A separate floppy can restore the previous generation or finish a later
interrupted switch between prepared FAT16 and FAT32 profiles. [Later switches](#external-recovery-of-later-profile-switches)

## Three-sector record, version 1

Each preallocated slot holds exactly 1,536 bytes. The first sector is a
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

A partially written live MBR still reads as `DIVERGED` in F8. External
recovery separately checks the physical sector against both snapshots, the
intact journal pair and the independently approved new MBR before offering
the exact remaining byte changes.

Record status codes are `0` valid, `1` missing, `2` format, `3` CRC,
`4` identity, `5` geometry, `6` snapshot/layout and `7` forbidden delta.
Pair status adds `8` unavailable, `9` degraded and `10` conflict. Status zero
means successful parsing/pair selection; the separate observation still matters.

## Native evidence and next integration

`make hdd-test` includes the journal model through both BIOS read routes.
The native model prints `T=0090` and `RB JOURNAL MODEL PASS`. Its 144 assertions
cover literal host-to-C16 vectors, reserved fields, identities, geometry,
protected MBR bytes, all observations, both slot orders, sequence exhaustion,
stale-result cleanup and all six partial three-sector replacement combinations.
They also check all 16 combinations of four visibility changes in a journal
snapshot after a torn copy or interrupted discard, plus two unrelated bytes.
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
covers the first prepare header with complete snapshots and an old live MBR,
the validated prepared pair with an old or prefix-matching live MBR, and the
completion snapshot and header with the approved MBR active. When only part of
the new snapshot reached the prepare slot under its intact seed header, the
rescue diskette can restore that single journal sector from the baseline.
The old live MBR and both complete baseline records are verified afterward.
The normal boot menu also exercises this order on a two-profile FAT16 disk.


## Confirmed HDD switch

On a prepared multi-profile EDD disk, **S** opens a review from the selected
hidden profile's preview. The review identifies the disk, the target, each
current and intended primary type/active flag, and the next sequence. **Esc**
cancels. **Enter** authorizes this particular change. The firmware requires
exclusive access to the disk for the operation.

A fresh allocation audit supplies the six physical journal addresses. The
firmware retains both original headers, the preceding MBR snapshot, the
reviewed before/after sectors and fingerprints of the allocation and identity
records. Confirmation checks all of them again. A healthy baseline or a
completed previous transaction must match the cold-boot MBR. Changed records,
a different VBR, mismatched geometry or an exhausted sequence stop the switch.

| Phase | Required physical observation |
| --- | --- |
| Prepare | Publish the old snapshot, the new snapshot and then the prepare header in the inactive slot. Read back each changed sector. Both slots must select `PREPARED_OLD`. |
| Switch | Recheck the target and live MBR, write sector zero, read it back byte for byte, and observe `PREPARED_NEW`. |
| Complete | Publish the same snapshots and a committed header at the same sequence in the other slot. The validated pair must select `COMMITTED_NEW`. |
| Start | Reread the target through the READY and visibility checks. Pass that exact VBR and its current primary entry to the real-mode handoff. |

The allocation and the expected contents of all six journal sectors and the
live MBR are rechecked after each changed sector. Snapshot sectors that
already match are skipped. The write to sector zero has a dedicated entry
point. The management-record writer only addresses sectors beyond the
management VBR. A write or readback error stops the operation before handoff.
Firmware readback observes the BIOS storage path. Power-loss durability also
depends on the device and its caches.

The EN/DE HDD tests compare the full VDI against independently encoded disks
after P1 → P2 and P2 → P1. The first transition changes four bytes in sector
zero. Errors at each of five or seven writes, failed readbacks and distinct
partial sectors are exercised. A cold boot blocks ambiguous states. A fully
committed disk can boot its selected target on a later cold start even after
the original session reported a failed readback.

For the first switch, a separately enrolled rescue floppy and external
backup complete the actual interrupted HDD transaction and verify the
repaired disk through a cold P2 boot. A full powered-off pre-switch copy is
also restored and booted at each injected write boundary in both directions.
[Single-VDI manual check](PreparedDOS.md#switching-profiles-on-one-disk)


## External recovery of later profile switches

`profile-recovery.img` boots independently of the HDD loader. Its published
secondary backup and floppy witness authorize the entire intended MBR. The
enrolled primary IDE master and BIOS disk 0x80 must return identical physical
sector contents. The backup must match the live disk identity, management
volume, EBRs, boot areas, and raw configuration/state records.

The HDD menu and both recovery programs derive the eligible slots for a
multi-profile switch from the selected configuration. Each approved profile
must resolve to a READY installation on that physical slot. An unrelated
READY record leaves its slot outside the mask. A hidden, inactive primary
outside the mask is copied byte-for-byte through each candidate view. A
proposed change to an unregistered slot blocks the transaction before review.

Before rotating a completed journal the HDD also checks its two previous
views. Both must describe isolated profiles in the current configuration.
A previous switch involving a subsequently removed profile blocks a new
rotation. Direct handoff to a matching current profile remains available.

The later recovery program recognizes two or three approved FAT16 or FAT32
primary profiles. It derives each slot's `0x06` or `0x0B` base type from the
externally approved MBR. Both the primary and backup FAT32 boot sectors
are included in the byte comparison of the complete saved reserved area.
A complete committed predecessor or a complete prepared successor supplies
the candidate sequence and slot order. The two possible phases of each
header, both old/new snapshots, and the live MBR are compared against the
seven physical writes in their publication order. Each candidate previous
profile uses the protected bytes of the full external MBR. All sectors
following an interrupted write must still have their expected old contents.

| Observed on the system disk | Offered operation |
| --- | --- |
| Previous or final committed pair matches the live MBR | Report completion with zero writes |
| Only the old snapshot was copied, or the new snapshot is still incomplete | Restore the unpublished journal sectors from the previous generation and keep its active profile |
| Both new-generation snapshots are complete and the target matches external approval | Publish the remaining sectors in order, including LBA 0 only when required |
| Foreign disk or witness, protected-byte change, or incompatible sector order | Stop before writing |

A torn LBA 0 write can leave two active flags during a P2-to-P1 return. For
the structural allocation audit, the program reads the physical MBR and
substitutes the externally approved view in memory. The write decision
still requires every byte of the observed physical MBR to match the ordered
transition, including its exact old suffix. Journal addresses come from
the checked live management allocation.

The review lists the resulting profile, sequence, all remaining LBAs, and
the individual differences if LBA 0 is included. Confirmation repeats the
checks and pins the observed sector. Each write is flushed, read back
through BIOS and ATA and followed by a fresh independent check. After an
error, a new boot derives the remaining work from the physical disk.

`make profile-recovery-test` builds both rescue languages and exercises the
shipped VDIs, both slot orders, all seven interruption points and the final
32-bit sequence. The ZIP is written to `build/profile-recovery/`.
[VirtualBox test and expected messages](LaterProfileRecovery.txt)
