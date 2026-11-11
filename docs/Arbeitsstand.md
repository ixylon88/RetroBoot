# Project state and resumption

Updated: 11 November 2026.

## Saved baseline

PR #12 (independent installation-state records) is merged into `historical`
at `93791cd0769519114147e71c98cd7cb27f219e9b`. Its host, ABI and HDD CI passed.
The F6 manual test was reported complete. The normal image's check/detail
`0006 / 0000` was explicitly observed: no configured entry, no further detail.
Both A/B copy-status lines remain separate from that result. No machine,
BIOS, read-route or language-coverage details were added to the report.

Earlier manual reports cover the ABI floppy, HDD/C startup, menu, partition
scanner, English/German builds, F3, the T07 test-VBR handoff and F5. They do
not establish coverage beyond their stated environments and increments.

## Current increment: primary-partition visibility preview

Branch `codex/profile-visibility` adds F7: current and intended primary types
and active flags for the selected profile. DOS/Win9x requires exactly one
visible/active data primary; NT uses the explicitly configured visible group
and only the selected primary is active. Empty slots, the extended entry,
geometry, boot code and all non-type/active bytes remain identical.

The preview reuses the exact final MBR observation from the independent
record/current-VBR check. It also checks the hidden management volume and
startup pointer. Blocked checks clear the proposed table and masks. The
[visibility guide](Visibility.md) describes controls, status values, manual
checks and limits. F6's interface and read sequence remain unchanged.

This increment is read-only. It performs no partition writes, installer
transitions, countdown or real OS starts. Main-menu F4 remains limited to
the existing compiled T07 target; F4 and Enter are inert inside F7.

Verification scope:

- 117 host checks plus the reference layout report.
- Two byte-identical builds per language; unchanged 48 KiB Stage 2 and
  8 KiB stack budgets; normal variants remain below 28 KiB.
- 96 boot cases, including 43 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic, 29 handoff, 84 configuration, 86 installation-state and
  52 visibility checks.
- Per language: 75 menu, 204 scanner, 318 volume, 185 handoff, 678
  configuration, 650 installation-state and 370 visibility states;
  4,960 across both languages.
- F7's 37 campaigns per language include two different target identities,
  DOS/NT visibility, damaged/degraded/pending records, target I/O failures
  and retries, CP437 names, navigation, inert Enter/F4, VGA/RAM/BSS/stack,
  exact reads, unchanged handoff memory and unchanged images/no writes.

English remains the default; `RB_LANGUAGE=de` selects CP437 German including
umlauts and `ß`, with separate outputs. Repository prose remains impersonal
and contains no private personal details. Specification v0.2 is unchanged.
CI results and downloadable artifacts belong to this branch's PR; only the
project's reviewed merge updates `historical`.

## Open work

1. Review and manually check F7 on fresh normal and handoff images. The normal
   image reports `0002 / 0006 / 0000` without a plan; the handoff image reports
   `0000 / 0000 / 0000`, matching types/flags and changed mask `00`.
2. Integrate independently validated state and visibility into preparation of
   a suitably controlled original-OS test. Actual OS compatibility, start
   authorization and automatic start still need separate evidence.
3. Add recovery-backed writes and installation, including complete allocation/
   ownership checks, fresh identity allocation, journal handling and controlled
   state transitions. The current reader is not a full ownership audit, and
   a matching preview or CRC alone does not authorize a write or OS start.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items
above. Interrupted builds/tests must restart; transient emulator state is not
a saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
