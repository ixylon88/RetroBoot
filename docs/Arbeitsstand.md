# Project state and resumption

Updated: 12 November 2026.

## Saved baseline

PR #13 (primary-partition visibility preview) is merged into `historical`
at `ee939ddea422d14f1ae4e78bacd1884867858032`. Its host, ABI and HDD CI passed.
German F7 screenshots were confirmed under VirtualBox: the normal image
reported `0002 / 0006 / 0000` without a plan; the handoff image reported
`0000 / 0000 / 0000`, P1 `06 / 80`, P4 `05 / 00`, visible/active masks
`01 / 01` and changed mask `00`. This report does not establish English F7
manual coverage, other key paths, a BIOS version or physical hardware.

Earlier manual reports cover the ABI floppy, HDD/C startup, menu, partition
scanner, English/German builds, F3, the T07 test-VBR handoff, F5 and F6.
They do not establish coverage beyond their stated environments and increments.

## Current increment: checked-profile test handoff

Branch `codex/checked-profile-test` connects F7 to the known T07 sector with
an explicit F9 action in the handoff image only. Every attempt rereads both
configuration and state pairs, reselects the unchanged displayed profile by
Entry ID, repeats the current-target/visibility check and requires an already
matching primary view. A changed selected identity, name, target or policy
requires another review; reordering and independent generation changes alone
do not replace the selection.

The final MBR entry and VBR must also equal the compiled fixture byte for
byte. A matching state CRC alone cannot authorize another sector. The exact
captured bytes feed the existing assembly handoff; failed preparation clears
the staging buffer. The [profile-test guide](ProfileTest.md) records the
controls, error codes, read sequence and English manual check.

The normal image ignores F9. Main-menu F4 remains the earlier isolated T07
test; F4 and Enter remain inert inside F7. F9 rejection requires an F7 review
before another attempt. There are no disk writes, installer transitions,
journal, countdown or original-OS starts in this increment.

Verification scope:

- 121 host checks plus the reference layout report.
- Two byte-identical builds per language in CI; unchanged 48 KiB Stage 2
  and 8 KiB stack budgets. Normal Stage 2 is 28,244 bytes (EN) and 28,696
  bytes (DE); the handoff variants are 32,594 bytes (EN) and 33,106 bytes (DE).
- 98 boot cases, including 44 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser, 114 volume/
  arithmetic, 29 handoff, 84 configuration, 86 installation-state,
  52 visibility and 60 checked-profile checks.
- Per language: 75 menu, 204 scanner, 318 volume, 185 handoff, 678
  configuration, 650 installation-state, 370 visibility and 336 checked-profile
  states; 5,632 across both languages.
- F9's 37 campaigns per language cover successful second-profile selection,
  DOS/NT visibility, damaged/degraded/pending records, stale identities,
  substituted VBR bytes with a matching CRC, wrong raw entry/slot, real I/O
  failures and retries, legacy/empty records, inert keys, VGA/RAM/BSS/stack,
  exact sector reads and receipts, unchanged images and zero writes.

Local emulator checks use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU
`486` and 16 MiB RAM. CI records its own versions and ROM hashes. English
remains the default; `RB_LANGUAGE=de` selects CP437 German including umlauts
and `ß`, with separate outputs. Repository prose remains impersonal and
contains no private personal details. Specification v0.2 is unchanged.
CI results and downloadable artifacts belong to this branch's PR; only the
project's reviewed merge updates `historical`.

## Open work

1. Review and manually check the English handoff image: F7, matching preview,
   F9, then `RB HANDOFF PASS`. Reboot returns to RetroBoot. The normal image
   has no F9 action. This new manual result remains pending.
2. Prepare a controlled original-OS test with separate start authorization
   and compatibility evidence. The current exact T07 binding authorizes only
   the owned probe, even when independent records and visibility match.
3. Add recovery-backed writes and installation, including complete allocation/
   ownership checks, fresh identity allocation, journal handling and controlled
   state transitions. The current reader is not a full ownership audit.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items
above. Interrupted builds/tests must restart; transient emulator state is not
a saved checkpoint. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
