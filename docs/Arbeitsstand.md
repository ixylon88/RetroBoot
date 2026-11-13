# Project state and resumption

Updated: 13 November 2026.

## Saved baseline

PR #16 (transaction-journal model) is merged into `historical` at
`38425393924a0c75668d856eb2731ab7cf40dfd6`. Its PR and merge checks passed.
That increment introduced the pure record decoder, conservative A/B selection
and full-MBR observation; it did not add a runtime journal page.

The F10 status `0000 / 0000` was manually confirmed on 13 November 2026.
No additional image/language, machine/BIOS, repeated-read or navigation details
were supplied. The report confirms the allocation status without broadening
coverage to other keys or environments. A later general acknowledgement adds
no specific manual coverage for the new F8 page.

English F7 followed by F9 from PR #14 was confirmed under VirtualBox on
13 November 2026: matching preview, `0000 / 0000 / 0000`, unchanged masks,
the F9 hint, and `RB HANDOFF PASS`. That report established no BIOS version,
reboot observation, physical-hardware coverage or original-OS start. Earlier
reports cover the ABI floppy, HDD/C startup, menu, partition scanner,
English/German builds, F3, isolated T07, F5/F6 and German F7. Their coverage
remains limited to the reported results.

## Current increment: read-only journal diagnosis

Branch `codex/journal-diagnostics` adds **F8, then Enter** for a fresh journal
diagnosis. The page distinguishes an empty baseline, prepared/old, prepared/new,
committed/new and a divergent current MBR. Enter repeats all reads; F8 returns
to the Recovery landing page and Esc to the menu. F4/F9 are inert on this page.

F10 now owns eight files, including the two 1,536-byte `RBTXN.A/B` records.
The bounded allocation audit produces three sector addresses per copy, even
with fragmented chains. The reader performs its own fresh audit, checks both
configuration and both state records against one nonzero media identity, reads
both journals and rereads the complete MBR to detect changes during diagnosis.
An invalid or partial read cannot retain an earlier successful selection.
Private scratch is cleared on entry and exit. There is no disk writer.

The [diagnosis guide](JournalDiagnosis.md) contains the manual procedure,
status codes, trust boundary and automated evidence. The
[journal guide](TransactionJournal.md) retains the binary and pair contracts.
This increment changes both released normal/handoff images. A fresh VirtualBox
conversion is necessary when replacing raw media. Released samples contain an
EDD baseline; forced CHS deliberately reports a geometry mismatch. Dedicated
fixtures exercise matching EDD and CHS journals independently.

Verification scope:

- 134 host tests plus the reference layout report.
- 104 boot cases and 47 identical EDD/CHS sector-sequence pairs. Native
  assertions include 126 journal-model (`T=007E`), 42 journal-reader (`D=002A`)
  and 80 allocation checks (`A=0050`). Existing models retain 26 menu,
  51 partition, 114 volume/arithmetic, 29 handoff, 84 configuration, 86 state,
  52 visibility and 60 profile checks.
- Both languages build twice. UI campaigns cover 3,681 states per language,
  7,362 total, including 495 journal states and 370 allocation states each.
  Evidence includes screenshots, VGA/RAM, stack/BSS checks, exact read traces,
  unchanged source-image hashes and zero disk writes.
- Normal Stage 2 is 38,124 bytes EN / 38,732 bytes DE; handoff is
  42,482 / 43,150 bytes. Test-only native model variants omit unused UI code;
  the journal-model binary is 30,418 bytes and the journal-reader binary is
  29,854 bytes. The existing 48 KiB file and 8 KiB stack budgets remain.

Local native tests use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU `486`
and 16 MiB RAM; CI records its own versions and ROM hashes. English remains
the default; German uses the same logic and CP437 including `ÄÖÜäöüß`.
Repository prose remains impersonal and excludes private details. The frozen
specification v0.2 and archives are unchanged. PR checks/artifacts provide the
current branch's validation; merge remains part of project review. Manual F8
confirmation is still pending.

## Open work

1. Establish the independent external rescue path required by specification
   v0.2 before the first write tests. Define its own media/identity checks and
   the evidence needed to recover an interrupted transaction independently.
2. Add fresh ownership/identity checks and verified prepare/MBR/completion
   writes with interruption tests after every step. The present observation
   is neither an atomic snapshot, a durable-history proof nor a write lease.
3. Add fresh installation identities and controlled installer state transitions.
   Original-OS starts still need separate authorization and compatibility evidence;
   F9 remains bound to the exact owned T07 test sector.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items above.
Interrupted tests restart; transient emulator state is not a saved checkpoint.
Completed increments are committed and proposed as PRs for project review.
