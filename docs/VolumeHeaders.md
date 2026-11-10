# Read-only FAT volume header checks

F3 adds a bounded FAT16/FAT32 VBR/BPB inspection to the Stage 2 menu. A
successful result means that the first sector's header is plausible within
the selected partition. It does not establish filesystem integrity, identify
an installed operating system or authorize a boot. No sector is modified.

## Operation

| Key | Action |
| --- | --- |
| F3 | Read and validate the complete MBR/EBR layout, then inspect a data partition's first sector |
| Left / Right | Select the previous/next data partition, wrapping and skipping empty slots and extended containers |
| F3 while on the volume page | Refresh the tables and the current entry; select the first data entry if the old index is no longer usable |
| F2 | Return to a freshly read partition table |
| Esc | Return to the main menu |
| F8 | Open recovery information |

Left/Right uses the last successfully validated table snapshot and reads the
newly selected volume header. F3 refreshes both. A table error prevents the
volume read and displays the existing scanner error page. An empty table
shows an empty result without reading a volume. All these states remain
operable; automatic boot stays off.

The page shows the partition slot, type and absolute VBR LBA. Only a successful
probe adds FAT type, bytes per cluster, total sectors, data clusters and the
absolute data-start LBA. Failed or unsupported headers leave these derived
fields blank, including after a successful result for another volume.

## Supported header profile

The parser in `core/volume.c` requires a previously validated partition
layout and independently checks the selected extent against the BIOS range.
It requests at most one sector through the existing BIOS reader. That reader
retains the selected EDD/CHS route and permits at most three attempts.

| Area | Check |
| --- | --- |
| Partition family | FAT16 types `06/16/0E/1E`; FAT32 types `0B/1B/0C/1C` |
| Sector | `55AA` at bytes 510–511; jump syntax `EB xx 90` or `E9 xx xx`; 512 bytes per sector |
| Cluster | Power of two, 1–64 sectors; at most 32 KiB |
| Basic layout | Nonzero reserved-sector and FAT counts; media byte `F0` or `F8`–`FF` |
| Volume extent | Exactly one total-sector field is nonzero; total does not exceed the partition; a smaller volume is allowed |
| Addressing | `BPB_HiddSec` equals the actual absolute partition-start LBA, including logical volumes |
| Arithmetic | Reserved, root and FAT areas fit before data; additions, subtractions and FAT-size multiplication cannot wrap |
| FAT classification | Derived from data-cluster count and compared with the partition family and FAT-size field, independently of text labels |
| FAT capacity | At least `cluster count + 2` entries fit; a larger FAT is allowed |
| Root | FAT16 has a nonempty fixed root; FAT32 has no fixed root and a root cluster inside the data-cluster range |
| FAT32 metadata | Version zero, supported flags, valid active FAT when mirroring is off, FSInfo and optional backup pointers inside the reserved area |

FAT type follows the cluster thresholds 4,085 and 65,525. FAT12 is not
supported. The FAT32 upper cluster bound is the existing conservative
RetroBoot layout policy: fewer than `0x0FFFFFEF` data clusters. BPB geometry,
OEM names and textual filesystem labels do not select the BIOS read route
or prove a filesystem type.

These checks describe the current supported profile, not every valid foreign
FAT variant. In particular, FAT32 requires a nonzero FSInfo pointer below the
reserved-sector count; a no-FSInfo sentinel is not accepted. A zero backup
pointer is allowed; a nonzero one must be in the reserved area and differ
from FSInfo. A hidden-sector value using another convention is rejected,
without patching the BPB.

Types `07/17` are explicitly **unchecked**; their header is not read and no
NTFS validity is inferred. Other types are rejected by the table scanner or
reported unsupported by the standalone probe.

The probe does not read FAT entries, directories, files, FSInfo contents or
backup sectors. It checks jump syntax, not the destination or behavior of
boot code. It cannot establish that FAT copies agree or that a root cluster
contains a directory. A later start path must freshly validate its target,
configuration and identity. The separate [T07 test](Handoff.md) now proves
the transition to an owned VBR, without authorizing arbitrary OS code.

## Manual check of the compact image

The normal 64 MiB image is available in both languages as
`hdd/retroboot-hdd.img` and `hdd-de/retroboot-hdd.img` in the CI artifact.
The [HDD guide](HDD_Boot.md) covers QEMU and VirtualBox startup and conversion.

After F3, the expected compact-image result is:

| Field | Expected value |
| --- | --- |
| Partition / type | `L1` / `16` |
| VBR LBA, hex | `0000007E` |
| Result | Plausible FAT BPB; filesystem contents unchecked |
| FAT type / bytes per cluster | `FAT16` / `2048` |
| Volume sectors, hex | `0001F5C9` |
| Data clusters, hex | `00007D2B` |
| Data-start LBA, hex | `0000019B` |

Left and Right return to L1 because it is the only data partition. Repeated
F3, F2, Esc and F8 remain usable. The large reference image has unformatted
OS/data placeholders: their missing VBR signature is expected. Its management
volume L2 is the successful FAT16 case.

Manual success for the English/German builds from PR #8 and subsequently the
F3 page from PR #9 was reported without new platform details. The new separate
T07 and the subsequent F5 test were also reported complete. The new
[F6 state check](InstallationState.md) remains open for manual verification.

## Native arithmetic and verification

The C16 compiler emits register helpers for unsigned 32-bit multiplication,
division and remainder. `runtime/arith.asm` implements the required ABI with
386 instructions, without DOS or the C runtime library:

| Helper | Inputs | Outputs |
| --- | --- | --- |
| `__U4M` | `DX:AX`, `CX:BX` | Product modulo 2^32 in `DX:AX`; `BX/CX` volatile |
| `__U4D` | Dividend `DX:AX`, nonzero divisor `CX:BX` | Quotient `DX:AX`, remainder `CX:BX` |

Both preserve SI, DI, BP, segment registers and the stack. They are compiler
register helpers, not cdecl functions. Every parser divisor is checked before
use. These independent implementations are linked only into HDD Stage 2;
unprovided runtime symbols still cause a link error.

```sh
make check
make hdd-test
make hdd-ui-test RB_LANGUAGE=de
make volume-test RB_LANGUAGE=en
```

`volume-test` builds once and runs just the volume UI campaigns. Already built
images can be checked with `python3 tools/test_volume.py --language en`, with
optional `--qemu` and `--bios` paths as in the other emulator tests.

- 113 host tests include four fixture checks for preserved loader data, fixed
  header values, disjoint ranges and rejected inputs.
- The 94-case boot suite includes the native `hdd-volume-model` with both
  EDD and CHS: 114 assertions (`V=072`, hexadecimal), comprising 30 arithmetic
  and 84 parser/read-bound assertions, followed by `RB VOLUME MODEL PASS`.
- Each language runs 43 volume campaigns with 318 VGA/keyboard states.
  These include valid FAT16/FAT32 headers, corrupted fields, unsupported NTFS
  types, empty/invalid tables, logical partitions, wrapping, refresh, failure
  recovery and actual one-off/permanent block-read errors.
- Expected read sequences are exact, including retries and skipped reads.
  Every state checks VGA, Stage 2 bytes, BSS and stack protection; source
  hashes remain unchanged and disk traces contain no writes. Paired EDD/CHS
  campaigns must read identical sector sequences.

The 19 new 128 MiB fixtures contain test headers alongside the existing
management volume. Their added FAT16/FAT32 regions have no boot program,
FAT contents or directories and are deliberately not bootable filesystems.
These fault/header fixtures and the large reference image are not uploaded.
The separate T07 image is described in its own guide. Reports,
text pages, screenshots, RAM/VGA snapshots and traces are under `build/volume/`
or `build/volume-de/`, and `volume/` or `volume-de/` in the CI artifact.
`volume-results.json` is written only after the entire campaign succeeds.

Format reference: Microsoft, [FAT Specification 1.03](https://www.isdaman.com/alsos/protocols/fats/fatgen103.pdf).
Compiler ABI references: Open Watcom [32-bit division helpers](https://github.com/open-watcom/open-watcom-v2/blob/master/bld/clib/cgsupp/a/i4d.asm)
and [multiplication helpers](https://github.com/open-watcom/open-watcom-v2/blob/master/bld/clib/cgsupp/a/i4m.asm).
