# F10: management-volume allocation

F10 checks allocation metadata for the six files currently installed on the
hidden RetroBoot FAT16 management volume. It reports overlapping file chains,
incorrect chain lengths, inconsistent FAT copies and allocated clusters that
have no recognized owner. This is a read-only diagnostic and a prerequisite
for future ownership checks, not a disk-write or OS-start authorization.

## Manual check

The **retroboot-hdd-bios** artifact contains English images in `hdd/` and
German images in `hdd-de/`. The check works in both `retroboot-hdd.img` and
`retroboot-handoff.img`. A fresh image or newly converted VirtualBox VDI is
required; an existing VDI does not change when its source raw image is replaced.

1. Boot either current image in the empty BIOS test VM.
2. Press **F10**. The English title is **Management-volume allocation audit**.
3. Expect the green message **Allocation is consistent for the supported file
   set.**, with **Status / detail (hex): `0000 / 0000`**.
4. The table contains `RBBOOT.SYS`, `RBSTG2.BIN`, `RBCFG.A`, `RBCFG.B`,
   `RBSTATE.A` and `RBSTATE.B`.
5. Press F10 again; the result should remain the same. Enter, F4 and F9 are
   inert on this page. Esc returns to the menu. F8 opens recovery information,
   from which F10 opens the same fresh allocation check.

All table numbers are hexadecimal. The current compact images have 2,048-byte
clusters and total cluster count `7D2B`. The normal English image reports
`0015` used and `7D16` free; normal German reports `0016` used and `7D15` free.
The English handoff image reports `0017` used and `7D14` free; the German
handoff reports `0018` used and `7D13` free. These counts include
one bootstrap cluster and four record clusters; the different Stage 2 sizes
explain the remaining difference. File sizes and counts change as code grows.

| Image | Stage 2 bytes, decimal | Stage 2 bytes, hex | Stage 2 clusters, hex |
| --- | ---: | --- | --- |
| English normal | 32,496 | `00007EF0` | `0010` |
| German normal | 33,060 | `00008124` | `0011` |
| English handoff | 36,856 | `00008FF8` | `0012` |
| German handoff | 37,482 | `0000926A` | `0013` |

The German handoff Stage 2 needs one more cluster than the English handoff.
F10 does not validate record contents; F5/F6 retain their separate record checks.

The F10 status `0000 / 0000` was manually confirmed on 13 November 2026.
No additional image/language, machine/BIOS or key-path details were supplied. English F7 followed by F9 was confirmed
under VirtualBox on 13 November 2026, including the matching preview and
`RB HANDOFF PASS`. The separate F10 report confirms its status result.

## Supported management format

The check rereads the MBR and bounded EBR chain, validates the current disk ID
and RBM1 pointer, and requires a hidden logical FAT16 partition (`16` or `1E`).
The same captured management VBR must pass the existing BPB arithmetic check,
RBV1 magic and full-sector checksum. The supported format has one reserved
sector, two FATs, 512 fixed root entries, media byte `F8`, and a BPB total equal
to the partition length. FAT size is limited to 256 sectors; data-cluster IDs
must stay below FAT16's reserved `FFF0` range.

The root scan stops at the first zero entry, or after all 32 root sectors.
Deleted entries are ignored. A volume-label entry with zero size and cluster
fields has no allocation. All other live entries must be one of the six
recognized short names, exactly once, with supported regular-file attributes
and a zero high cluster word. Unknown files, directories and long-file-name
entries are unsupported and block the audit. Future `RBTXN`, export and
backup files require an explicit extension of this ownership model.

| File | Accepted size and chain |
| --- | --- |
| `RBBOOT.SYS` | Nonzero multiple of 512 bytes, at most 8 KiB; contiguous chain; first LBA and sector count equal the VBR bootstrap pointer |
| `RBSTG2.BIN` | Nonzero, at most 48 KiB; fragmentation allowed |
| `RBCFG.A`, `RBCFG.B`, `RBSTATE.A`, `RBSTATE.B` | Exactly 512 bytes each, one cluster per file |

Every chain must have exactly the number of clusters implied by its size,
valid in-range successors and an end marker `FFF8`–`FFFF` at its last cluster.
A loop or a cluster shared by two files blocks the check. At most 116 ownership
entries are needed: 16 bootstrap clusters, 96 Stage 2 clusters and four records
at the smallest supported 512-byte cluster size.

After the chain walk, a complete sector-by-sector comparison of both FATs
checks all bytes, including padding. The owned format requires header words
`FFF8 / FFFF`. Every addressable nonzero data-cluster entry must belong to
exactly one recognized file; even an unowned bad-cluster marker blocks this
closed format. Each owned successor must still equal the value captured during
the chain walk. Entries beyond the addressable cluster range do not own data,
but their bytes must still match between the two FAT copies.

No file-data sectors are read. Stage 2 contents, record CRCs, authenticity,
OS bootability and general FAT recovery are outside this check. The reads are
not an atomic snapshot against external media changes. Success must not be
cached as a future write lease. Private synchronous scratch is cleared on both
success and failure; failure also clears all displayed file and count values.

## Diagnostic codes

| Status, hex | Meaning |
| --- | --- |
| `0000` | Supported allocation is consistent |
| `0001` | Partition scan failed; detail is the scanner status |
| `0002` | Unsupported or invalid management binding/header; detail may be the volume status |
| `0003` | Required metadata read failed after bounded retries |
| `0004` | Root entry problem: detail `1` unknown, `2` duplicate, `3` missing, `4` attributes/high word, `5` size, `6` cluster bounds |
| `0005` | Invalid, looping or incorrectly sized chain |
| `0006` | Shared cluster; detail identifies the earlier owning file |
| `0007` | FAT copies differ, including possible padding differences |
| `0008` | FAT header differs from the current management format |
| `0009` | Allocated cluster has no recognized owner |
| `000A` | An owned successor changed between chain walk and full sweep |
| `000B` | Bootstrap allocation differs from its raw loader binding |

The error page includes the relevant LBA and, when available, a file ID and
cluster. File IDs `1`–`6` follow the displayed table order; zero means no
specific file. Chain/orphan/change details contain the observed FAT value;
a detected loop instead reports the existing owner ID. F10 always starts a
fresh check, including after a failure.

## Automated evidence

`make audit-test` builds and runs the English suite; `RB_LANGUAGE=de` selects
German. Already-built media can be tested with `python3 tools/test_audit.py`,
with optional `--language`, `--qemu` and `--bios`. Evidence is written under
`build/audit/` and `build/audit-de/` and published with the four release images.
The deliberately damaged images remain local build fixtures.

The native C16 model runs 72 assertions (`A=0048`) via EDD and CHS. It includes
all 32 root sectors, exact maximum 116-cluster allocation, intra-file loops,
shared chains, bad/reserved entries, stale-result cleanup and a FAT successor
changing during the final sweep. Five host tests independently check mutation
boundaries, the canonical root, full-FAT read evidence and error-page hygiene.

Per language, 37 QEMU campaigns check 370 keyboard/VGA states: 16 metadata/fault
fixtures and both released images via EDD/CHS, plus one uninstrumented handoff
image. Three F10 attempts per campaign prove fresh reads and recovery-page
access. Exact post-menu metadata-read sequences, bounded real BIOS retries,
English/German text, result colors, frame preservation, file values, full
loaded code/BSS/stack checks, unchanged handoff memory, image hashes and zero
block writes are required. F4/F9/Enter cannot launch a target from F10.

Released and diagnostic fixtures now have the canonical six-file root.
Explicit `hdd-*` loader campaigns retain their synthetic directory/LFN entries
that test bootstrap skipping. The audit deliberately rejects those extra live
entries rather than overlooking possible allocation owners. Specification
v0.2 and the existing loader's skip coverage remain unchanged.
