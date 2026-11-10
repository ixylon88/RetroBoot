# Project state and resumption

Updated: 10 November 2026.

## Saved baseline

PR #10 (T07 test-VBR handoff) is merged into `historical` at
`ea677bfdae4977644a856f43292f849473780dfe`. Its host, ABI and HDD CI passed.
Manual success for the test-VBR handoff was subsequently reported. No new
machine, BIOS, read-route or language-coverage details were supplied.
Earlier manual reports cover the ABI floppy, HDD/C startup, menu, partition
scanner, English/German builds and F3 volume-header view. Those reports do
not establish coverage beyond their stated environments and increments.

## Current increment: read-only configuration records

Branch `codex/profile-records` adds F5 and preallocated `RBCFG.A/B` files to
the generated management volume. Each request freshly scans the tables,
checks the management pointer/BPB, derives the root and FAT locations, validates
both file allocations and selects the newest completely valid configuration.
A rejected copy remains visible as a warning; conflicting equal generations
or a wholly invalid configuration expose no profile data.

The versioned 512-byte records bind disk signature, structural layout and
management extent. Up to eight profiles carry stable Entry IDs, names, exact
primary extents/types, profile kind, intended visibility and declared status.
The [configuration guide](Configuration.md) specifies every byte, status,
selection rule, read boundary and manual check. Configured status/approval is
not independent installation evidence. No configuration value enables a
countdown, OS jump or write. The existing T07 main-menu F4 gate is unchanged.

The normal 64 MiB image has two identical generation-1 records and no entries.
The 128 MiB handoff image has one unapproved `Test VBR` profile. Dedicated
negative and eight-entry fixtures are used only by automated tests.

Verification scope:

- 108 host checks plus the reference layout report.
- Two byte-identical builds per language; unchanged 48 KiB Stage 2 and
  8 KiB stack budgets; both normal Stage 2 variants remain below 21 KiB.
- 92 boot cases, including 41 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic, 29 handoff and 76 configuration checks through both BIOS routes.
- Per language: 75 menu, 204 scanner, 318 volume, 185 handoff and 678
  configuration states; 2,920 states across both languages. The configuration
  suite has 63 campaigns, including a run without an instrumentation ROM.
- Real read failures/retries, copy fallback/conflict, directory/FAT faults,
  full-root bounds, all eight entries, CP437 names, inactive declared approval/
  countdown, VGA/RAM/BSS/stack, exact reads, unchanged images and no writes.

English remains the default; `RB_LANGUAGE=de` selects CP437 German including
umlauts and `ß`, with separate outputs. Repository prose remains impersonal
and contains no private personal details. Specification v0.2 is unchanged.
CI results and downloadable artifacts belong to this branch's PR; only the
project's reviewed merge updates `historical`.

## Open work

1. Manually check F5 on current normal and handoff images. Both copies should
   have status `0000`, generation `00000001`, selected copy A. The normal image
   has no entries; the handoff image has the unapproved `Test VBR` entry.
   Esc returns; F4 remains limited to the handoff image's main menu.
2. Add independent installation/media-state records (`RBSTATE.A/B`) and the
   cross-check with profile declarations. Structural CRC plus disk signature
   alone cannot identify an installation or distinguish identical clones.
3. Integrate profile selection, current/intended visibility and fresh target
   validation before a suitably prepared original-OS test. DOS/Win9x isolation,
   optional NT groups and automatic start need their own evidence. Runtime
   writes remain deferred to the later recovery-backed phase; this file reader
   is not a complete allocation audit for a future writer.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items
above. Interrupted builds/tests must restart; transient emulator state is not
a saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
