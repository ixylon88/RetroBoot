# Project state and resumption

Updated: 10 November 2026.

## Saved baseline

PR #9 (read-only FAT volume headers) is merged into `historical` at
`c9fbc512f068d4f2f954a9dcb41391067c081f2b`. All its CI passed. Manual success
for the F3 view was subsequently reported, without new platform details.
Earlier reports cover the ABI floppy, HDD/C startup, menu (PR #6), partition
scanner (PR #7) and English/German builds (PR #8). No machine or BIOS version
is inferred from those reports.

## Current increment: T07 test-VBR handoff

Branch `codex/test-vbr-handoff` adds an explicit, separate 128 MiB test image.
F4 on its main menu freshly validates the tables, exact primary entry and
FAT BPB, then compares the same captured VBR against the compiled test sector.
Only that owned sector can run. Failures clear staged data and remain operable.
The normal 64 MiB diagnostic images ignore F4 and retain their existing logic.

The transition copies all 512 bytes to `0000:7C00` and the raw entry to
`0000:0800`, restores the agreed register/stack state and transfers execution.
The independent VBR captures/checks its entry state and displays
`RB HANDOFF PASS` or `RB HANDOFF FAIL`. It does not return to the menu; a
reboot is required. The [handoff guide](Handoff.md) records the exact contract,
fixture limits, failure codes and manual instructions. There are no disk
writes, OS profiles or original-OS startup claims in this increment.

Local evidence:

- 102 host tests and the reference layout report pass.
- Two byte-identical builds per language.
- 90 boot cases, including 40 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic and 29 handoff-preparation checks, each through EDD and CHS.
- Per language: 75 menu, 204 scanner, 318 volume and 185 handoff states,
  totaling 1,564 states across both languages. Handoff tests inspect exact
  loaded bytes, stable entry, captured registers/stack and unchanged INT 13h.
  Real read errors, nine injected transition faults, negative authorization,
  VGA/RAM/BSS/stack, exact reads, unchanged images and no writes are checked.

The large reference layout and its positive/negative CHS geometry tests are
unchanged. English remains the default; `RB_LANGUAGE=de` selects CP437 German,
including umlauts and `ß`, with separate outputs. Neutral repository prose
and exclusion of private personal details remain required by `AGENTS.md`.
The frozen specification v0.2 is unchanged. CI results and downloadable
artifacts belong to this branch's PR; only a reviewed merge updates `historical`.

## Open work

1. Manually check `retroboot-handoff.img` in both languages. F4 from the main
   menu should reach `RB HANDOFF PASS`. Record platform and read-route details
   when available. The PR #9 report does not cover this new test image.
2. Define persistent installation/media identity and valid start profiles,
   including intended partition visibility. The exact compiled T07 fixture
   binding is not a general OS authorization or installation record.
3. Integrate selection and fresh target validation with that profile model;
   then test a suitably prepared original system under phase 5. Automatic
   start, DOS/Win9x isolation and optional NT groups still need their own
   evidence. Writes remain deferred to the later recovery-backed phase.

## Resuming after a pause

Begin with current GitHub branches/PRs, repository code and the open items
above. Restart interrupted builds/tests; transient emulator state is not a
saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
