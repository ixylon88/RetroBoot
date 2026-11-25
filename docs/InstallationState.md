# Installation-state records and F6 diagnosis

F6 reads `RBCFG.A/B` and `RBSTATE.A/B` independently, then compares a selected
profile with the current target's validated volume boot record (VBR). This
implements the read-only foundation of specification v0.2 sections 10 and 12.
It does not run an OS, establish safe visibility, inspect OS files, execute a
transaction, or replace the future recovery-backed installer.

F6 reads the four files on demand. A separate operation in the prepared-DOS
kit can put an installation into recovery on a new disk copy. F6 displays the
result at the next boot. [Saving a DOS boot block](#saving-a-dos-boot-block)

## Manual check

A fresh image or freshly converted VDI is required. Old converted images do
not acquire the new files or executable when a download is replaced.

| Image | Expected F6 result |
| --- | --- |
| `hdd/retroboot-hdd.img` | Both record pairs `0000 / 0000`; state generation `00000001`, copy A; no selected profile; check/detail `0006 / 0000` |
| `hdd/retroboot-handoff.img` | Both pairs `0000 / 0000`; generation `00000001`, copy A; green matching-records/current-VBR result; check/detail `0000 / 0000`; profile `Test VBR` |
| Corresponding files under `hdd-de/` | Identical results with German labels |

The two A/B copy-status lines are separate from the check/detail line. On
the normal image, healthy copies (`0000 / 0000`) and no configured entry
(`0006 / 0000`) are expected together. The F6 manual test was reported complete;
no additional platform or language coverage was specified.

The handoff image's installation ID is `0000000100000001`. Its state record
is marked `ready` solely for the synthetic, owned test VBR. The corresponding
F5 declaration is now `2 / 1`; this does not claim an installed or approved
operating system. The displayed CRC depends on the compiled test sector.

Left/Right selects profiles and repeats the current-target check. F6 rereads
both record families. Esc returns to the main menu; F8 opens recovery help.
Only the handoff image's main-menu F4 executes T07 and displays
`RB HANDOFF PASS`. A reboot returns from that terminal test.

## Identities and independent selection

The configuration's Entry ID identifies an editable menu profile. A nonzero
128-bit media ID identifies a managed medium; a nonzero 64-bit installation
ID identifies one installation on that medium. Renaming a profile, changing
its Entry ID, or independently advancing its configuration generation does
not change installation identity. Reinstalling into the same slot requires a
new installation ID. A future installer must allocate fresh, non-reused IDs.

The reproducible test builder uses fixed **synthetic** IDs. They are not an
allocation algorithm for real media. CRC32, disk signatures and stored IDs
provide consistency checks, not cryptographic authentication. Byte-identical
clones remain indistinguishable. A matching VBR does not prove intact OS files.

Each record pair selects its newest completely valid unsigned generation;
equal valid generations must be byte-identical. Identical copies select A.
Selection never retries an older state just because it matches an old
configuration. Configuration and state generations need not agree.

The diagnostic loaders can select one valid copy while reporting a rejected
copy. F6 deliberately refuses a successful cross-check whenever **any** copy
is missing, unreadable or invalid. This prevents a degraded fallback from
being treated as completed installation evidence. An equal-generation
conflict is a hard failure. Generation counters do not wrap.

Legacy configuration version 1 remains readable through F5. It has no media
or installation identity and yields F6 status `0004`; no identity is guessed
and no migration is performed at runtime. New generated images use
[configuration version 2](Configuration.md#version-2-installation-binding).

## RBSTATE version 1 format

A record occupies exactly 512 bytes in one preallocated FAT16 cluster.
Integers are unsigned little-endian. IEEE CRC32 is calculated over bytes
0–507 with reflected polynomial `EDB88320` and initial/final XOR `FFFFFFFF`.

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | `RBSTATE` followed by one zero byte |
| 8 | 2 | Version `1` |
| 10 | 2 | Header length `64` |
| 12 | 4 | Record length `512` |
| 16 | 4 | Nonzero generation |
| 20 | 4 | Nonzero MBR disk signature |
| 24 | 4 | RBL1 structural layout CRC, as specified in Configuration.md |
| 28 | 4 | Management-volume absolute start LBA |
| 32 | 4 | Management-volume sector count |
| 36 | 2 | Entry count, `0` through `4` |
| 38 | 10 | Reserved zero |
| 48 | 16 | Nonzero opaque media ID; displayed in stored byte order |
| 64 | 256 | Four 64-byte installation slots |
| 320 | 188 | Reserved zero |
| 508 | 4 | CRC32 |

Unused slots are entirely zero. Used slots have the following fields:

| Relative offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 8 | Nonzero installation ID, unique within this medium's record |
| 8 | 4 | Target absolute start LBA |
| 12 | 4 | Target sector count |
| 16 | 1 | Primary slot `1` through `4`, unique within the state record |
| 17 | 1 | Visible type `06/0E/0B/0C/07` |
| 18 | 1 | Kind `1` = `dos9x_isolated`, `2` = `nt_chain`; DOS cannot use `07` |
| 19 | 1 | Installation phase, from the table below |
| 20 | 4 | CRC32 of the entire 512-byte VBR; zero unless phase is `ready` |
| 24 | 40 | Reserved zero |

| Phase | Value | F6 treatment |
| --- | ---: | --- |
| `planned` | 1 | Cannot establish readiness; does not block unrelated ready installations |
| `prepared` | 2 | Blocks all profiles |
| `media_handoff` | 3 | Blocks all profiles |
| `setup_in_progress` | 4 | Blocks all profiles |
| `verification_required` | 5 | Blocks all profiles |
| `ready` | 6 | Eligible for the remaining consistency checks |
| `recovery_required` | 7 | Blocks all profiles |

The prepared-DOS kit can place a ready installation on hold. The HDD menu
can consume that hold for one explicitly requested verification boot. Granting
`ready` after an original-OS test requires a separate confirmation.

## Saving a DOS boot block

On a powered-off prepared DOS disk, the external kit can mark the single
existing installation as `recovery_required` on a new disk copy. The source
remains available. The review shows the profile, primary slot, stable
installation ID, both record names, destination LBA, generation and phase.
German kits accept **J** and English kits accept **Y**. The command accepts a raw input and a new VDI output.

```text
python3 RetroBoot-DOS.pyz input.img --require-recovery --output blocked.vdi
```

The tool checks the live DOS volume, partition layout, ownership of all eight
management files, both FATs, both configuration records and the idle journal.
Each healthy state record must agree with the installation ID in the independent
configuration. A `ready` record must match the live DOS VBR. Equal generations
must be byte-identical. Accepted histories cover the original ready pair,
the transition into recovery, the single verification boot, and a return from
verification to recovery. Conflicting or disjoint histories stop the operation.

Confirmation triggers a fresh read of the same disk context, including the
allocation metadata and the full record pairs. The tool updates the inactive
`RBSTATE` sector. The new generation carries phase 7 and a zero VBR claim.
Only the generation (offsets 16–19), phase and claim (83–87), and CRC
(508–511) can change. The tool flushes the sector, reloads both copies,
validates selection and compares the expected records and disk context before
publishing the new image. Two healthy copies already selecting the block
produce no output. Advancing a `ready` or `verification_required` record at
`0xFFFFFFFF` is refused.

A single CRC failure can be handled by the same command with fresh confirmation
when the immutable bytes match and every independent check succeeds. A
surviving `ready` record supplies the identity and previous generation for
completing the block. A surviving `verification_required` record advances
to recovery by the same rule. A surviving `recovery_required` record can restore its
peer at the same generation, including at `0xFFFFFFFF`. Two bad records or a
disagreement in identity require separate diagnosis. The command only publishes
an installation that remains blocked.

On a disk prepared with the updated BIOS menu, the menu checks the independent
installation records before offering DOS or arming its timer. A recovery block
leaves the diagnostics available. For the supplied fixture F6 shows generation
`0x00000002`, copy B, and check/detail `0x0007 / 0x0007`. A damaged copy
also suppresses boot. Enter and an already running timer repeat the full
layout and VBR checks at handoff. Earlier prepared disks retain the menu
version used to create them. [VirtualBox test procedure](PreparedDOS.md#testing-the-installation-boot-block)

## Consuming one verification boot

On a prepared single-DOS disk, **V** reviews a controlled boot from the
`recovery_required` phase. Both installation records must validate. The
previous generation must be `ready`, refer to the same installation and
contain the CRC of the current 512-byte DOS boot sector. The current record
must be the immediately following recovery hold. Two recovery records have
no earlier verified VBR to compare. An exhausted generation also blocks the
attempt. Normal selection and the countdown stay disabled throughout.

**Enter** repeats the partition scan, management-file ownership audit, profile,
state-pair, idle-journal, volume and BIOS geometry checks. Any change to the
reviewed records, allocation metadata, partition entry or VBR ends the
review. On a match RetroBoot replaces the older READY sector with the next
generation in `verification_required`, phase 5, with a zero VBR claim. It
reads back both copies and rechecks the same disk context and staged VBR
before transferring control. The recovery record stays intact. **Esc** during
review performs zero writes. A write or readback error ends the attempt.

| State after a power cut | Next boot |
| --- | --- |
| Original READY sector fully intact beside the hold | Normal boot stays blocked. A new review and explicit consent are required for another attempt. |
| Torn installation sector | The menu reports degraded state. The external recovery tool can restore the surviving hold to its peer on a new copy. |
| Complete phase 5 sector | The menu reports verification pending even if power failed before the jump. No automatic or manual retry is available. |

The released test VBR checks the transfer and displays `RB HANDOFF PASS`.
A real OS test includes its own startup and a subsequent confirmation before
a future writer may grant `ready`. The external `--require-recovery` command
can return a pending disk to the recovery phase on a new copy. Its two records
then contain no READY VBR claim for another trial.
[VirtualBox procedure](PreparedDOS.md#one-dos-verification-boot)

## Read and comparison boundary

Both loaders use `core/record_io.c`: fresh full partition scan, startup/current
management pointer comparison, validated hidden logical FAT16 BPB, bounded
root traversal, exact names, directory checks and two-FAT EOC checks. All four
known files must have distinct starting clusters. FAT and data sectors are
read only for the requested pair. Missing state files do not prevent F5 from
diagnosing a legacy configuration. This reader does not audit every other
file chain and cannot establish write ownership.

After both independent loads, F6 checks record health, version, disk/layout/
media binding, selected installation ID, phase, exact slot/extent/type/kind
and the configuration's installed/approved declaration. Pending or recovery
state anywhere on the managed medium blocks the comparison. Then a further
fresh full scan must still match the structural fingerprint and target.
The normal volume validator reads the selected VBR once; CRC is computed
from that exact validated read, with no later sector reread. Current active
flags/hidden-type pairs are not proof of safe OS visibility.

Failures clear the observed CRC and matched-installation index. The F6 page
shows the relevant reason and LBA without a stale success value. F6 is an
on-demand observation, not a continuing monitor or persistent authorization.

| Hex | F6 result |
| --- | --- |
| `0000` | Records and current VBR match |
| `0001` | Configuration unavailable; detail is configuration status |
| `0002` | State unavailable; detail uses the same record status vocabulary |
| `0003` | At least one rejected/missing/unreadable copy |
| `0004` | Legacy configuration lacks installation binding |
| `0005` | Record disk/layout/media identities differ |
| `0006` | No selected profile |
| `0007` | Pending/recovery installation; detail is its phase |
| `0008` | No matching installation ID |
| `0009` | Matched installation and profile targets/kinds differ |
| `000A` | Selected installation is not ready; detail is its phase |
| `000B` | Profile lacks installed/approved declaration |
| `000C` | Fresh scan failed; detail is scanner status |
| `000D` | Fresh layout/target changed |
| `000E` | Current volume invalid/unreadable; detail is volume status |
| `000F` | Current VBR CRC differs |

## Verification

`make state-test RB_LANGUAGE=en` builds and runs the F6 campaign; `de` selects
German. Direct invocation is `python3 tools/test_state.py --language en`,
with optional `--qemu` and `--bios`. Evidence is under `build/state/` and
`build/state-de/`. Only the normal and T07 handoff images are published.

The native C16 state suite has 86 assertions covering format boundaries,
all seven phases, independent generation selection, stale identities,
renaming, degraded records, fresh scan/VBR checks and failure clearing.
The configuration suite now has 84 assertions, including both record versions.
F6 has 65 emulator campaigns and 650 observed states per language: both BIOS
routes for 30 fault/positive fixtures and both published images, plus an
uninstrumented run. Checks include exact reads, real injected I/O failures
and retries, VGA text/colors/borders, CP437 umlauts/`ß`, loaded code/BSS,
stack guard, unchanged low-memory handoff areas, source hashes and zero writes.
