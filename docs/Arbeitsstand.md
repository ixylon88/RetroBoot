# Project state and resumption

Updated: 13 November 2026.

## Saved baseline

PR #14 (checked-profile test handoff) is merged into `historical` at
`0b9054bd25746d6f183654601ee75759802269cf`. Its host, ABI and HDD CI passed.
English F7 followed by F9 was manually confirmed under VirtualBox on
13 November 2026. The supplied screenshots show the matching English preview,
`0000 / 0000 / 0000`, P1 `06 / 80`, P4 `05 / 00`, visible/active masks
`01 / 01`, changed mask `00`, the F9 hint, and then `RB HANDOFF PASS` with
`Test VBR reached. Reboot to return.` No BIOS version, reboot observation,
physical-hardware coverage or original-OS start was established by that report.

Earlier manual reports cover the ABI floppy, HDD/C startup, menu, partition
scanner, English/German builds, F3, the T07 test-VBR handoff, F5 and F6.
German F7 screenshots from PR #13 confirmed both expected normal/handoff
views under VirtualBox on 12 November 2026. These reports do not establish
coverage beyond their stated environments and increments.

## Current increment: management-volume allocation

Branch `codex/admin-allocation-audit` adds F10 to both normal and handoff images.
It validates the hidden management-volume binding and the six current root
files, walks their exact bounded chains, rejects shared clusters, binds the
contiguous bootstrap to its VBR pointer, and compares both full FATs. Unowned
allocated data clusters and successors changing during the final sweep block
the check. Private scratch and incomplete file/count results are cleared on
failure. The [allocation guide](AdminAllocation.md) records supported formats,
codes, controls, limits and the pending manual check.

F10 rereads; Esc returns to the menu; F8 opens recovery information and F10
also works there. Enter, F4 and F9 are inert on the audit page. The existing
F7-to-F9 path still executes only the exact owned T07 test VBR after its own
fresh record/target checks. F10 adds no disk writes, installer transitions,
journal, countdown or original-OS starts and grants no persistent write lease.

Released diagnostic roots now contain the canonical six-file set. Explicit
`hdd-*` loader fixtures retain the extra directory/LFN entries used to prove
bootstrap skipping. Unknown live entries block the closed allocation audit;
future journal/export/backup files need explicit ownership support.

Verification scope:

- 126 host checks plus the reference layout report.
- Two byte-identical builds per language in CI; unchanged 48 KiB Stage 2
  and 8 KiB stack budgets. Normal Stage 2 is 32,496 bytes (EN) and 33,060
  bytes (DE); the handoff variants are 36,856 bytes (EN) and 37,482 bytes (DE).
- 100 boot cases, including 45 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic, 29 handoff, 84 configuration, 86 installation-state,
  52 visibility, 60 checked-profile and 72 allocation checks (`A=0048`).
- Per language: 75 menu, 204 scanner, 318 volume, 185 handoff, 678
  configuration, 650 installation-state, 370 visibility, 336 checked-profile
  and 370 allocation states; 3,186 per language and 6,372 total.
- F10's 37 campaigns per language cover metadata faults, full FAT padding,
  shared chains, orphan allocation, unsupported roots, wrong sizes/bootstrap
  binding, real I/O failures/retries, fresh repeated checks, recovery access,
  inert start keys, VGA/RAM/BSS/stack, exact metadata reads, unchanged handoff
  memory, unchanged source images and zero block writes.

Local emulator checks use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU
`486` and 16 MiB RAM. CI records its own versions and ROM hashes. English
remains the default; `RB_LANGUAGE=de` selects CP437 German including umlauts
and `ß`, with separate outputs. Repository prose remains impersonal and
contains no private personal details. Specification v0.2 is unchanged.
CI results and downloadable artifacts belong to this branch's PR; only the
project's reviewed merge updates `historical`.

## Open work

1. Review and manually check F10 on current images: green consistency message,
   `0000 / 0000`, six-file table, repeat read, Esc and recovery access.
   The [guide](AdminAllocation.md) contains exact current cluster counts.
2. Extend ownership support deliberately for the journal and recovery files;
   design recovery-backed transactions, fresh identity allocation and controlled
   installer transitions. This audit observes current metadata and cannot alone
   authorize later writes or repair an arbitrary FAT filesystem.
3. Prepare a controlled original-OS test with separate start authorization
   and compatibility evidence. The exact T07 binding still authorizes only
   the owned probe, even when independent records and visibility match.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items
above. Interrupted builds/tests must restart; transient emulator state is not
a saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
