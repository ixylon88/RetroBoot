# External metadata container

This increment defines version 1 of a bounded external metadata container and
checks the same wire format in Python and native C/16. It is a foundation for
external recovery, **not a completed backup or restore operation**. The rescue floppy now reads and validates saved files through the
[read-only F4 path](RescueBackupFile.md). It still has no restore action.

The frozen specification v0.2 remains authoritative. Its complete external
backup and independently confirmed restore requirements remain open.

The subsequent [saved-record check](BackupRecords.md) adds native approved-view
partition and configuration/state consistency checks. It is a separate layer;
the wire-format validator and Python inspector described here retain their
container-only boundary. The [FAT boot-area layer](BackupBootAreas.md) follows
the record checks and validates supported saved reserved regions.

The [native metadata encoder](BackupEncoding.md) now emits the five framing
sectors from explicit claims. Its standalone model checks exact Python wire
images; it does not collect payloads, establish provenance or write a backup.

## Validation boundary

Successful validation establishes framing, canonical descriptor order, bounded
and nonoverlapping stored ranges, required role presence and CRC32 integrity.
Header fields describe **claimed** identity and geometry. Neither CRC32 nor a
nonzero media ID proves provenance or a match with a currently attached disk.

The container supports both complete MBR copies, EBR sectors, contiguous or
discontiguous volume boot areas, and current one-sector configuration/state
copies. A boot-area descriptor may cover multiple sectors: FAT32 boot areas
must not be reduced to one sector by a future collector. Payload contents are
opaque here. The validator does not parse saved partition tables, FAT BPBs,
configuration or state, prove that every required EBR/boot sector was captured,
or establish which MBR was originally installed or last approved. Required role
presence is not proof of a complete or consistent snapshot.

Record semantics and stable-source revalidation are supplied by the subsequent
checker layers and F4 file reader. Real collection, management-file ownership,
independent live-media binding, selection of targeted restore bytes, explicit
confirmation and interruption handling remain open. No disk writer or OS-start path is added.
An accepted descriptor list must never be treated as a write plan.

## Wire format, version 1

All integers are unsigned little-endian. Sectors are 512 bytes. The file is at
most 1 MiB (2,048 sectors): one header sector, four descriptor sectors and
contiguous payload sectors. The table has 64 physical slots, of which at most
42 are used: six fixed records, up to 16 EBRs and up to 20 boot-area extents.
Several boot extents may belong to one volume. Unsupported sizes or counts are
rejected, never silently truncated; larger profiles need a future format.

| Header byte offset | Bytes | Field / constraint |
| ---: | ---: | --- |
| 0 | 8 | `52 42 42 41 4B 00 00 00` (`RBBAK`) |
| 8 | 2 | Version `1` |
| 10 | 2 | Header length `512` |
| 12 | 4 | Exact total file length in bytes |
| 16 | 4 | Nonzero snapshot generation, supplied by the producer |
| 20 | 4 | Nonzero claimed disk ID |
| 24 | 4 | Claimed canonical `RBL1` layout CRC32 |
| 28, 32 | 4 each | Management-volume start LBA and sector count |
| 36, 38 | 2 each | Used descriptor count and fixed stride `32` |
| 40 | 2 | Captured read route: `1` EDD, `2` CHS |
| 42, 44 | 2 each | Observed heads and sectors/track |
| 46 | 2 | Reserved zero |
| 48 | 8 | Captured reachable sector count |
| 56 | 16 | Nonzero claimed media identity |
| 72 | 4 | CRC32 of all 2,048 descriptor-table bytes |
| 76 | 432 | Reserved zero |
| 508 | 4 | CRC32 of header bytes 0–507 |

Geometry is either a complete valid pair (1–256 heads, 1–63 sectors/track) or,
for EDD only, zero/zero when no CHS geometry was recorded. CHS capacity must
fit 1,024 cylinders with the recorded heads and sectors/track. Missing EDD
geometry is not reconstructed or inferred. Future snapshot completeness and
target-binding rules must assess the available observations explicitly.

The capacity is 64-bit; stored extents use the existing 32-bit LBA contract.
Each nonempty extent must have a nonwrapping 32-bit exclusive end within
capacity. Management-volume bounds follow the same rule and start above LBA 0.

| Descriptor byte offset | Bytes | Field / constraint |
| ---: | ---: | --- |
| 0, 2 | 2 each | Kind and zero-based index within that kind |
| 4, 8 | 4 each | Original disk LBA and stored sector count |
| 12 | 4 | File-relative payload sector, starting at `5` |
| 16 | 4 | CRC32 of the complete payload extent |
| 20, 24 | 4 each | Owning volume start and length, or zero/zero |
| 28 | 4 | Reserved zero |

| Kind | Meaning | Index / range rule |
| ---: | --- | --- |
| 1 | Original full MBR | Index 0, disk LBA 0, one sector, no owner |
| 2 | Last approved full MBR | Index 0, disk LBA 0, one sector, no owner |
| 3 | EBR | Indices 0–15, one sector above LBA 0, no owner |
| 4 | Volume boot area | Indices 0–19, wholly inside its owning volume |
| 5, 6 | Configuration A, B | Each index 0, one sector inside the management volume |
| 7, 8 | Installation state A, B | Each index 0, one sector inside the management volume |

Descriptors are sorted by kind, then consecutive index starting at zero.
Kinds 1, 2, 4, 5, 6, 7 and 8 must occur. EBRs are optional for a primary-only
layout. The two MBR roles intentionally refer to the same disk sector; every
other stored disk range must be disjoint. Config/state owner fields must equal
the header's management-volume bounds. Boot-area ownership is a range claim,
not proof that the saved or live partition table contains that volume.

Payloads follow descriptor order, without holes, aliases or trailing bytes.
Unused descriptor slots are zero. CRC32 uses reflected polynomial
`EDB88320h`, initial accumulator `FFFFFFFFh` and final XOR `FFFFFFFFh`.
It detects accidental corruption, not deliberate modification by an actor
able to recompute checksums.

## Reader and host inspector

`rb_backup_validate` accepts an exact file-sector count and a callback that
copies exactly one sector on success. Callback addresses refer to the file,
not the target HDD. Reads are sequential: header, all four table sectors, then
payload. Validation stops at the first error. The decoder holds one 512-byte
scratch buffer and a bounded result; a payload can exceed the 64 KiB segment.
Private scratch makes the function non-reentrant. The caller must keep the
source stable during validation and revalidate before any later use. No
partial result survives a failed call, including failure in the final sector.

| Status | Meaning |
| ---: | --- |
| `0000` | Container framing and integrity accepted within the stated boundary |
| `0001` | Callback read failed |
| `0002` | Unsupported format, invalid fields, flags or reserved bytes |
| `0003` | Header, table or payload checksum mismatch |
| `0004` | Invalid disk/file/owner bounds or file extent sequence |
| `0005` | Invalid kind order, duplicate role or index sequence |
| `0006` | Overlapping disk ranges other than the two MBR roles |
| `0007` | Required role missing |

The Python encoder serializes explicitly supplied chunks; it does not collect
them from a disk. Its read-only command-line inspector opens a regular file,
caps the read size and prints claims and descriptors as JSON:

```sh
python tools/backup_container.py build/rescue/synthetic-container.rbb
```

The generated example contains synthetic byte patterns, **not boot sectors or
usable recovery records**. Its report explicitly sets `live_media_match` and
`restore_authorized` to false. It is published with CI evidence solely as a
format example. There is no command for creating a real disk backup yet.

## Verification

The file-validation increment brought `make check` to 167 host tests;
[CI.md](CI.md) records the current suite including rescue F5. The nine container tests include literal
wire-offset checks, a byte mutation at each of the 22,528 positions in the
small example, resealed malformed metadata, all required roles, size/count
limits, round trips, CLI output and unchanged input files.

The rescue build adds a separate test-only `backup-model` payload. Its reader
synthesizes file sectors without reading a disk or loading the whole file into
the 16-bit segment. It exercises 72 scenarios with 216 assertions (`B=00D8`,
`RB BACKUP MODEL PASS`): positive EDD/CHS and geometry variants, 130-sector
boot areas, the 1 MiB maximum, 42 descriptors, discontiguous boot areas,
resealed malformed fields, CRC damage, overlapping ranges, missing roles,
and read failures including the last sector of the largest file. Every call
checks bounded sequential reads, result guards and cleared failure results.

The container increment established 39 boots per language, with the same
217 UI states: 78 boots and 434 states total. The subsequent saved-record
and boot-area models add one boot each per language (82 boots / 434 states at PR #21). The subsequent F4 file path reaches
138 boots / 812 states.
Existing diagnostic, startup,
BIOS-fault, unchanged-media and no-write checks remain. Both languages are
built twice and their binaries/manifests compared. At PR #19, normal EN/DE rescue images remained byte-identical to PR #18.
The subsequent F4 path also links the checkers into the normal rescue program. The HDD and ABI implementations are unchanged. The additional model
has no language-specific behavior and is exercised in both build variants.
