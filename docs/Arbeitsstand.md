# Project state and resumption

Updated: 10 November 2026.

## Saved baseline

PR #11 (read-only configuration records) is merged into `historical` at
`5b0aa7452ae5e02d5e9fb954bf697c33d13e2058`. Its host, ABI and HDD CI passed.
The manual test was also reported complete. No machine, BIOS, read-route or
language-coverage details were added to that report. F5 is no longer an open
manual-test item for that increment.

Earlier manual reports cover the ABI floppy, HDD/C startup, menu, partition
scanner, English/German builds, F3 and the T07 test-VBR handoff. They do not
establish coverage beyond their stated environments and increments.

## Current increment: independent installation-state records

Branch `codex/installation-state` adds preallocated `RBSTATE.A/B` files,
configuration version 2 and F6. Configuration and state copies are loaded and
selected independently. Media IDs and installation IDs prevent matching an
old profile to a newer synthetic installation merely because its slot and
geometry are unchanged. Profile names, Entry IDs and configuration generations
remain independent of installation identity. Legacy v1 configurations remain
readable in F5 and cannot satisfy F6's binding requirement.

F6 compares healthy record pairs, phases, identities and declarations, then
freshly scans the layout and validates the current VBR. It calculates CRC from
that exact validation read. Degraded copies, conflicting records, pending or
recovery states and stale identities cannot produce a successful comparison.
The [installation-state guide](InstallationState.md) specifies formats,
selection rules, limitations, status values and manual checks.

This is a read-only consistency check, not OS-start authorization. The seven
installation phases are represented but no installer transitions are executed.
Runtime writes, visibility changes, countdown and real OS starts remain
inactive. F4 is still limited to the existing main-menu compiled T07 target.

The normal 64 MiB image has two identical empty generation-1 records in each
family. The 128 MiB handoff image has a synthetic ready installation record
and a declared `2 / 1` profile for its owned `Test VBR`. This is not evidence
of a real operating-system installation. Fixed fixture IDs are reproducible
test values, not the future production identity-allocation algorithm.

Verification scope:

- 113 host checks plus the reference layout report.
- Two byte-identical builds per language; unchanged 48 KiB Stage 2 and
  8 KiB stack budgets; both normal variants remain below 26 KiB.
- 94 boot cases, including 42 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic, 29 handoff, 84 configuration and 86 installation-state checks.
- Per language: 75 menu, 204 scanner, 318 volume, 185 handoff, 678
  configuration and 650 installation-state states; 4,220 across both languages.
- F6's 65 campaigns include actual read failures/retries, degraded/conflicting
  copies, cross-family cluster aliases, stale installation/media IDs, all
  seven phases, pending state on another primary, CP437 names, navigation,
  inert Enter/F4, VGA/RAM/BSS/stack, exact reads and unchanged images/no writes.

English remains the default; `RB_LANGUAGE=de` selects CP437 German including
umlauts and `ß`, with separate outputs. Repository prose remains impersonal
and contains no private personal details. Specification v0.2 is unchanged.
CI results and downloadable artifacts belong to this branch's PR; only the
project's reviewed merge updates `historical`.

## Open work

1. Review and manually check F6 on fresh normal and handoff images as described
   in the installation-state guide. Both pairs should show `0000 / 0000`.
   The normal image has no selected profile; the handoff image reports a
   matching current VBR. Enter/F4 stay on F6; Esc returns to the main menu.
2. Integrate profile selection, current/intended visibility and independently
   validated state into the preparation of a suitably controlled original-OS
   test. DOS/Win9x isolation, optional NT groups and automatic start need their
   own evidence. A matching CRC alone does not authorize an OS start.
3. Add the recovery-backed write/installer phase later, including complete
   allocation/ownership checks, fresh identity allocation, journal handling
   and controlled state transitions. The current file reader is not a
   complete filesystem ownership audit.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items
above. Interrupted builds/tests must restart; transient emulator state is not
a saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
