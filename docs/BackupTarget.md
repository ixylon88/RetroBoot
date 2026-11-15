# Read-only target-claim comparison core

`rb_backup_match_target` compares the identity, capacity, geometry and canonical
layout claimed by a backup header with independently acquired current metadata.
The native **backup-target-model** exercises it with an in-memory reader.
The independent rescue program now also calls it from the [F5 comparison
adapter](RescueTargetCheck.md), which supplies freshly validated file claims,
fresh BIOS discovery and real read-only HDD access. The HDD menu now also uses
the [numeric and byte display convention](Languages.md#numbers-and-byte-sequences);
its disk-access and validation behavior is unchanged by that presentation update.

## Inputs and boundaries

The API in [backup_target.h](../include/backup_target.h) accepts:

- Claims in an `rb_backup` structure. The caller must separately validate the
  complete saved file through the existing container, record and boot-area
  layers. Descriptors, backup generation and saved payloads are not examined here.
- A freshly acquired `rb_rescue_device`: first HDD `80h`, EDD or CHS route,
  64-bit accessible sector count, heads and sectors per track.
- A read-only sector callback and its opaque context, bound to that same device.
  Its addresses are **physical HDD LBAs**, unlike the file-relative readers
  used by the saved-content validators.
- A writable, non-overlapping result structure. Sources must remain stable
  for the call; private scratch makes the checker non-reentrant.

No BIOS discovery, file loading, writing, boot handoff or persistent selection
occurs. Failure clears all observed identity, layout and generation fields.
Only status, detail and error LBA remain. Results expire when their source
changes; success is not a lease for a later operation.

## Acquisition and comparison

`rb_backup_observe_target` exposes the same two-acquisition observation without
saved claims. Its optional `rb_backup_sources` result contains the validated
partition scan and config A/B, state A/B addresses from the allocation audit.
It also projects READY first-VBR claims (start, CRC and original entry index)
from the selected validated installation-state copy, for full boot-area checks.
That result is cleared at entry and populated only after both acquisitions
agree. Missing arguments or invalid devices cause no reads. It requires the
same non-overlap, stable-source and non-reentrancy preconditions. The
[preliminary capture planner](BackupCapturePlan.md) uses this observation;
the existing F5 comparison retains its claim checks and exact read order.

Invalid parameters, unequal capacities and unequal route/geometry are rejected
before any disk read. The comparison is deliberately exact. EDD permits an
unknown `0 / 0` geometry; otherwise heads must be `1..256` and sectors per
track `1..63`. CHS also requires a nonzero capacity within 1,024 cylinders.
One missing geometry component, a changed BIOS route, or a changed translation
is rejected rather than guessed.

For each of two complete acquisitions:

1. Read physical LBA 0. Require its boot signature, `RBM1` marker, nonzero disk
   ID and management-volume pointer. These values come from the current MBR,
   never from the backup's location claims.
2. Run the existing [eight-file allocation audit](AdminAllocation.md) using
   those observed values and the independently supplied device capacity. This
   discovers the MBR/EBR layout, validates the owned FAT16 volume and file
   chains, compares the entire FAT copies and rejects unowned allocations.
3. Read `RBCFG.A/B` and `RBSTATE.A/B` at the physical addresses discovered by
   that audit. Both copies must validate, and equal-generation conflicts are
   rejected. Both configurations must be version 2 and carry the same media
   identity. Both state copies must carry that identity too. Newer valid record
   generations are accepted; they need not equal a backup generation.
4. Check installation references between the independently selected newest
   configuration and state. Every nonzero profile installation ID must resolve
   to an entry with the same slot, type, kind, start and length. An approved
   profile requires a `READY` entry. The shared
   [saved/live helper](../core/backup_links.c) preserves the existing
   [saved-record rules](BackupRecords.md): unbound drafts, empty lists and
   several profiles for one installation remain valid. Unapproved references
   may resolve to pending entries. Older copies must still validate individually,
   but their links are not selected claims; configuration and state generations
   need not match. No additional sector reads occur.
5. Reread LBA 0. Every MBR read within this acquisition must match its initial
   512 bytes exactly. Return the independently observed disk/media IDs,
   canonical layout, management bounds and selected record generations.

The two acquisitions must have equal read counts and matching ordered
fingerprints. Each fingerprint consists of two separate CRC32 chains over the
first and second 256-byte halves of every sector, including the physical LBA
and previous chain value. Keeping these chains separate detects the tested
case of a changed record with a correctly recalculated trailing CRC: hashing
the complete CRC-suffixed sector alone would produce a constant residue.
Padding, root timestamps and boot-code bytes are included when their sectors
are read. Root sectors after the directory end marker are not acquired by the
existing allocation audit and are not covered by this comparison.

Only after successful acquisition are the observed disk/media IDs, canonical
layout CRC and management bounds compared with the backup's claims. A wrong
but well-formed backup pointer therefore does not redirect physical reads.
Backup descriptor addresses never enter the reader at all.

## Result codes

These codes belong to the core API. F5 displays them as detail/nested when
its outer check code is `0004`. They are not F4 file-status codes.

| Hex | Symbol | Meaning / detail |
| --- | --- | --- |
| `0000` | `OK` | The supported current metadata matches the supplied claims |
| `0001` | `PARAMS` | Missing argument (`0`), invalid claims (`1`) or invalid device (`2`); no reads |
| `0002` | `IO` | Direct MBR or record read failed; record details `5..8` identify config A/B, state A/B |
| `0003` | `ALLOCATION` | Existing allocation audit failed; detail is its status, with its error LBA |
| `0004` | `CONFIG` | Invalid/degraded/conflicting configuration pair; detail uses configuration codes |
| `0005` | `STATE` | Invalid/degraded/conflicting state pair; detail uses configuration/state codes |
| `0006` | `IDENTITY` | Missing live MBR identity (`1`), configuration identity/version (`2`), state identity (`3`) or claim mismatch (`4`) |
| `0007` | `CAPACITY` | Exact accessible sector counts differ; no reads |
| `0008` | `GEOMETRY` | Exact route, heads or sectors per track differ; no reads |
| `0009` | `LAYOUT` | Canonical layout or management-volume bounds differ |
| `000A` | `CHANGED` | MBR changed within acquisition, or the successful acquisitions differ |
| `000B` | `INSTALLATION` | Unresolved/incompatible selected installation reference; detail is the zero-based profile index |

Record-copy errors identify the failing physical file sector. Pair conflicts
have no single failing copy and use error LBA zero. Zero can also identify the
MBR; status and detail give the context. An I/O failure inside the allocation
audit remains `ALLOCATION`, with that audit's status and physical error LBA.
For `INSTALLATION`, error LBA identifies the profile's target start, not a
failed sector read. F5 displays `0x0004 / 0x000B / index`; rescue F6 displays
`0x0000 / 0x0002 / 0x000B / index`. Both clear prior successful output.

## Evidence and limitations

The native model runs **178 assertions** per language (`F=00B2`,
`RB BACKUP TARGET PASS`). Tests cover both routes, 64-bit capacity, unknown and
known EDD geometry, invalid inputs with no I/O, wrong claims, missing or damaged
live metadata, invalid/degraded/conflicting records, legacy configurations,
advanced generations, result clearing, 20 injected read failures and changes
to the MBR, EBR, VBR, root metadata, resealed records and FAT padding between
acquisitions. Guard bytes surround the result.

The successful fixture emits its complete **542-read** sequence, two identical
271-read acquisitions. An independent host oracle verifies exact order and
addresses, including both complete FATs and the final MBR reread. No program,
journal payload or system-volume VBR is read. Three new host tests verify the
seed records, oracle boundaries and rejection of incomplete/redirected traces.
The F5 integration adds real floppy/HDD campaigns and host tests. The live F5 fixture
has larger FATs and therefore a separate 1,058-read oracle; the model
retains its 542-read sequence.

The expanded capture-plan model exercises the same observer with nonempty
records: mismatched ID halves/kinds, approved pending states, independently
newer A/B selections, ignored older links, unbound drafts, empty lists, eight
profiles sharing an installation, the last profile failing and changes in
later acquisitions. A semantic failure after success must clear all source
addresses and READY claims. It now has 136 scenarios / 692 assertions.
F5/F6 floppy and instrumented/bare CD campaigns cover the new published
bad-reference fixture. A host mutation from intact to unlinked metadata also
checks F6's stale-result clearing. Current suite totals are recorded in the
[project state](Arbeitsstand.md).

This establishes comparison behavior for the supported intact metadata, not
unique physical-device identity. A disk clone with copied identifiers and the
same geometry is indistinguishable. CRCs are not authentication, and repeated
reads do not make a snapshot atomic. Changes after a final read remain possible.

The `RBL1` layout CRC normalizes visibility types and excludes active flags,
CHS table bytes and boot code. A match therefore does not prove equality to an
approved MBR, authorize a visibility change or establish original-MBR provenance.
Program contents, journal contents and current system VBRs need their separate
checks. Installation links establish record consistency, not actual installed
OS contents, readiness or authorization. The model does not establish complete
backup coverage, ownership history or recoverability.

Damaged or absent live MBR/FAT/identity metadata is rejected. A different,
independently justified recovery path for those cases remains open; trusting a
backup's sector addresses is not a fallback. Complete collection, provenance,
targeted restore authorization and interruption testing remain required before
disk writes. The read-only rescue UI integration is now available through F5.
