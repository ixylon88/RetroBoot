# Project state and resumption

Updated: 13 November 2026.

## Saved baseline

PR #15 (F10 management-volume allocation audit) is merged into `historical`
at `2da5c3c284bb9f031af60718ef883534d3a52fc9`. Its PR host, ABI and HDD CI
passed. The published artifact was downloaded and verified: 86 image/binary/
ROM components matched local builds, all 6,372 UI-state reports were present,
and 740 F10 VGA/RAM states were checked. The merge tree matched the tested tree.

The F10 status `0000 / 0000` was manually confirmed on 13 November 2026.
No additional image/language, machine/BIOS, repeated-read or navigation details
were supplied. The report confirms the allocation status without broadening
coverage to other keys or environments.

English F7 followed by F9 from PR #14 was confirmed under VirtualBox on
13 November 2026: matching preview, `0000 / 0000 / 0000`, unchanged masks,
the F9 hint, and `RB HANDOFF PASS`. That report established no BIOS version,
reboot observation, physical-hardware coverage or original-OS start. Earlier
reports cover the ABI floppy, HDD/C startup, menu, partition scanner,
English/German builds, F3, isolated T07, F5/F6 and German F7. Their coverage
remains limited to the reported results.

## Current increment: transaction-journal model

Branch `codex/transaction-journal-model` adds a pure C16 decoder, conservative
A/B pair selection and current-MBR observation for three-sector `RBTXN`
records. Each record contains a header plus complete old/new MBR snapshots,
with CRC32 protection of all bytes, sequence, disk/layout/media identity and
BIOS geometry. Only supported primary type/active bytes may change.

A prepared record can follow the immediately preceding empty/committed record
only when the old/new snapshots form an exact bytewise chain. A completion
must match the prepared transaction's sequence and both complete snapshots.
Corrupt/missing copies, contradictory pairs or skipped/reset sequences never
select an older fallback as authority. Current-MBR observations distinguish
baseline, prepared/old, prepared/new, committed/new and divergence. These are
byte comparisons and record claims, not proof of write history or durability.

The [journal guide](TransactionJournal.md) defines the binary format, trust
boundary, pair rules and limitations. The decoder has no disk reader/writer
callback, static scratch or retained pointers. It is linked only into the native
model test variant. The six-file F10 format, normal/handoff binaries and all
pre-existing generated image/binary components remain byte-identical to PR #15.
No new manual VM test is needed for this increment.

Verification scope:

- 130 host tests plus the reference layout report. Four new tests cover literal
  journal fields/CRCs, the host-to-C16 vector, every-byte checksum coverage,
  fixture transitions and rejected inputs.
- 126 native journal assertions (`T=007E`, `RB JOURNAL MODEL PASS`) through
  EDD and CHS, including every observation, both slot orders, geometry/identity
  changes, protected MBR bytes, all six torn three-sector replacement combinations,
  sequence exhaustion and stale-result cleanup.
- 102 boot cases with 46 identical EDD/CHS sector-sequence pairs. Existing
  native models retain 26 menu, 51 partition, 114 volume/arithmetic, 29 handoff,
  84 configuration, 86 state, 52 visibility, 60 profile and 72 allocation checks.
- Both languages build twice in CI. The unchanged UI suites cover 3,186 states
  per language, 6,372 total, with RAM/BSS/stack checks and zero writes.
- Normal Stage 2 remains 32,496 bytes EN / 33,060 bytes DE; handoff remains
  36,856 / 37,482 bytes. Journal-model binaries are 43,070 / 43,634 bytes,
  within the existing 48 KiB file and 8 KiB stack budgets.

Local native tests use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU `486`
and 16 MiB RAM; CI records its own versions and ROM hashes. English remains
the default; German uses the same logic and CP437 including `ÄÖÜäöüß`.
Repository prose remains impersonal and excludes private details. The frozen
specification v0.2 and archives are unchanged. PR checks/artifacts provide the
current branch's validation; merge remains part of project review.

## Open work

1. Add explicit eight-file allocation support for `RBTXN.A/B`, each 1,536 bytes,
   then a bounded reader and read-only F8 journal diagnosis. The current F10
   auditor intentionally rejects those files until ownership support is added.
2. Establish the independent external rescue path required by specification
   v0.2 before the first write tests. Then implement fresh ownership/identity
   checks and verified prepare/MBR/completion writes with interruption tests
   after every step. This model is not a writer or a recovery authorization.
3. Add fresh installation identities and controlled installer state transitions.
   Original-OS starts still need separate authorization and compatibility evidence;
   F9 remains bound to the exact owned T07 test sector.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items above.
Interrupted tests restart; transient emulator state is not a saved checkpoint.
Completed increments are committed and proposed as PRs for project review.
