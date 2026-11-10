# Read-only configuration and start-profile records

F5 reads `RBCFG.A` and `RBCFG.B` from the current hidden management volume.
It validates their format, CRC, generation, disk/layout binding and profile
fields, then displays the newest valid copy. A rejected copy is reported even
when the other copy succeeds. Conflicting valid copies of the same generation
leave the configuration unavailable. Every F5 request starts a fresh read.

This is the configuration foundation from specification v0.2 section 10.
The independent `RBSTATE.A/B` installation records, transaction journal,
visibility changes and OS-start authorization remain separate future work.
An `installed` or `approved` field in this diagnostic format is a declaration,
not proof of an installation. Enter, countdown values and F4 on the F5 page
cannot execute a target. The existing main-menu F4 test still uses its exact
compiled T07 binding; it never accepts a configuration record as authorization.

## Manual check

1. A newly downloaded image from this increment is booted in a BIOS VM. An older
   converted VDI does not contain the new files or F5 code.
2. F5 opens the configuration diagnosis. The normal 64 MiB `retroboot-hdd.img` displays two valid copies,
   generation `00000001`, copy `A`, and no stored entries.
3. The separate 128 MiB `retroboot-handoff.img` displays the draft `Test VBR`
   profile: Entry ID `00000001`, P1, type `06`, start `00020000`, length
   `000013D1`, `dos9x_isolated`, state/approval `0 / 0`, visible mask `01`.
   This is a description of the owned test target, not an OS installation.
4. Left/Right cycles through entries; F5 rereads both files. Enter and F4
   stay on the diagnostic page. Esc returns to the main menu; F8 remains
   available. F4 from the handoff image's main menu still reaches
   `RB HANDOFF PASS` and requires a reboot to return.
5. The same checks apply to `hdd-de/` with German labels. Stored names are
   CP437; umlauts and `ß` are exercised in the automated eight-entry fixture.

The main-menu timer stays disabled. The format stores a language preference,
but the current executable's language remains selected at build time.

## Version 1 binary format

Every file has exactly 512 bytes and occupies one allocated FAT16 cluster.
Integers are unsigned little-endian, decoded explicitly rather than by casting
disk bytes to compiler structures. CRC32 uses the reflected IEEE polynomial
`EDB88320`, initial/final XOR `FFFFFFFF`, over bytes 0–507. The standard
`123456789` vector produces `CBF43926`.

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | `RBCFG` followed by three zero bytes |
| 8 | 2 | Version `1` |
| 10 | 2 | Header size `64` |
| 12 | 4 | Total length `512` |
| 16 | 4 | Generation, `1` through `FFFFFFFF` |
| 20 | 4 | Nonzero MBR disk signature |
| 24 | 4 | Structural layout CRC |
| 28 | 4 | Management-volume absolute start LBA |
| 32 | 4 | Management-volume sector count |
| 36 | 2 | Entry count, `0` through `8` |
| 38 | 2 | Configured countdown seconds, `0` through `60`; currently inactive |
| 40 | 4 | Default Entry ID, or zero; nonzero must name an entry |
| 44 | 1 | Language: `0` English, `1` German |
| 45 | 19 | Reserved, all zero; no recovery-write settings yet |
| 64 | 384 | Eight 48-byte profile slots |
| 448 | 60 | Reserved, all zero |
| 508 | 4 | CRC32 |

Unused profile slots are entirely zero. Each used slot has these fields:

| Relative offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | Stable, nonzero Entry ID, unique within the record |
| 4 | 4 | Absolute start LBA |
| 8 | 4 | Sector count |
| 12 | 1 | Primary slot `1` through `4` |
| 13 | 1 | Visible partition type: `06`, `0E`, `0B`, `0C`, or `07` |
| 14 | 1 | Kind: `1` = `dos9x_isolated`, `2` = `nt_chain` |
| 15 | 1 | Declared installation state: `0` unset, `1` pending, `2` installed |
| 16 | 1 | Declared approval: `0` or `1`; `1` requires state `2` |
| 17 | 1 | Intended visible primary-slot mask; bit 0 = P1, bit 3 = P4 |
| 18 | 1 | Name length in bytes, `1` through `24` |
| 19 | 1 | Reserved zero |
| 20 | 24 | CP437 name, zero-padded; control bytes and DEL rejected |
| 44 | 4 | Reserved zero |

The target's start, length and visible type must match its actual primary
slot. Empty and extended slots cannot be selected or named in the visible
mask. The selected slot must be visible in the intended mask. A DOS/Win9x
profile permits only its selected slot and cannot use NTFS type `07`. An NT
chain profile may name other existing data primaries in its mask. Multiple
profiles may reference one primary; their Entry IDs remain distinct.

These checks validate the description and intended visibility. They do not
establish that current visibility is safe for a DOS/Win9x start, validate an
NT loader, inspect OS files, or authorize changes. Profile names are not
identities, and a slot does not imply an operating-system version.

## Layout binding and copy selection

The fingerprint is CRC32 over the following concatenated byte sequence:

- ASCII `RBL1`, then 16-bit partition and EBR counts.
- Each visited EBR's 32-bit absolute LBA, in traversal order.
- Every scan entry, including empty primaries, in scan order: 32-bit start,
  length and table LBA, followed by 16-bit normalized type, slot and logical
  flag. Each entry contributes 18 bytes.

Hidden data types `16/1E/1B/1C/17` normalize to `06/0E/0B/0C/07`.
Active flags and CHS bytes are excluded so a future controlled visibility
change does not change structural identity. Extended types remain distinct.
The disk signature and management extent are bound separately in the header.
EDD capacity and CHS reach are not fingerprint inputs; the full scan validates
ranges using the current route before computing the fingerprint.

Only completely valid copies participate in generation selection. The greater
unsigned generation wins; equal valid generations must be byte-identical.
Identical copies select A deterministically. A missing, unreadable, corrupt,
unknown-version or mismatched record can be rejected while the other valid
copy is used with a warning. With no valid copy, no profile data is exposed.
Generations do not wrap; a future writer must stop at `FFFFFFFF`.

CRC32 detects damage, not malicious changes. A disk signature plus structural
CRC cannot distinguish byte-identical clones and is not independent installation
identity. No compatibility with unknown record versions is guessed.

## File-reading boundary

`core/config_io.c` first rescans the entire MBR/EBR layout against the startup
disk signature. It checks the current `RBM1` management pointer against the
startup pointer and requires the corresponding hidden logical FAT16 volume.
The captured, validated BPB must have one reserved sector, two FATs, 512 root
entries and a total sector count equal to the partition extent.

The root directory is read from its freshly derived address, stopping at the
first end marker or the fixed 512-entry bound. Deleted and LFN entries are
skipped. Exact uppercase 8.3 file names are required. Duplicate names, invalid
attributes, high cluster words, wrong file sizes, out-of-range/reserved
clusters and an A/B cluster alias reject the entire load. Every present file
must have equal EOC values in both FAT copies (`FFF8` through `FFFF`). No
configuration chain is followed beyond its one allocated cluster. Each file's
first sector is then read; a data-read failure can leave the other copy usable.
Directory/FAT structural or read failures stop the whole load.

This is a bounded reader for preallocated files, not a general filesystem
integrity or ownership audit. It does not enumerate other file chains or
prove absence of cross-links to every other file. A future write path still
requires the complete allocation/ownership checks from specification v0.2.
All current disk accesses use the existing BIOS reader and bounded retries.
No directory, FAT, record, boot sector or partition entry is written at runtime.

## Status values

F5 displays the status of each copy in hexadecimal. A textual overall reason
accompanies failures; the relevant LBA and nested detail code are shown where
available. No stale profile rows survive a failed load.

| Hex | Meaning |
| --- | --- |
| `0000` | Valid |
| `0001` | Missing/unavailable copy |
| `0002` | Read failure |
| `0003` | Record format/version/reserved fields |
| `0004` | Record CRC |
| `0005` | Disk, layout or management-extent mismatch |
| `0006` | Invalid profile or default ID |
| `0007` | Conflicting valid records of equal generation |
| `0008` | Full partition scan failed; detail is the scanner status |
| `0009` | Management pointer/partition/BPB mismatch; BPB detail where available |
| `000A` | Directory/allocation ambiguity; detail 0/1 = A/B, 2 = alias |
| `000B` | Configuration FAT entry/copy mismatch; detail 0/1 = A/B |

## Verification

`make config-test RB_LANGUAGE=en` builds once and runs the focused suite;
`RB_LANGUAGE=de` selects the German build. Direct invocation after a build is
`python3 tools/test_config.py --language en`, with optional `--qemu` and
`--bios`. Evidence is saved under `build/config/` and `build/config-de/`.

The 76 native C16 assertions check CRC vectors, exact binary fields, CP437 including
`ß`, identity, bounds, names, profile semantics, generation ordering, conflicts,
fallback and clearing of stale results. The 63 emulator campaigns per language cover 678 states and add real FAT and
directory reads, 8-entry navigation, damaged files, allocation ambiguity,
nonstandard valid EOC, bounded full-root traversal and real BIOS read failures.
An explicitly declared approved/default profile with a one-second countdown
still cannot start from the diagnostic page. Both EDD and CHS run every fixture;
an additional run has no instrumentation ROM.

VGA, loaded code, BSS, stack guard, exact read sequences, unchanged low-memory
handoff buffers, image hashes and absence of guest writes are checked. The
result file is written only after the complete suite passes. Failure fixtures
are not uploaded as manual-test images; CI retains their reports and screenshots.
