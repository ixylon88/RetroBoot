# Project state and resumption

Updated: 10 November 2026.

## Saved baseline

PR #8 (English/German builds) is merged into `historical` at
`70a3bc62edf1ec44fdf261a227c19c551527adc9`. Its CI passed. Manual success for
both language variants was subsequently reported, without new VM, machine or
BIOS details. Earlier manual reports cover the ABI floppy, HDD/C startup,
menu from PR #6 and partition scanner from PR #7. These reports remain
separate from evidence for a specific hardware configuration.

## Current increment: read-only FAT volume headers

Branch `codex/read-only-volume-probe` adds F3 to revalidate the partition
tables and inspect FAT16/FAT32 BPBs. Left/Right cycles through data entries;
empty slots and extended containers are skipped. Errors preserve menu access
and clear derived values. Types `07/17` remain unchecked, without claiming
NTFS validation. There is no write path or OS handoff.

The [volume guide](VolumeHeaders.md) records the exact supported profile,
manual expectations and limits. The probe reads only the first volume sector;
plausible arithmetic does not prove filesystem integrity or bootability.
`runtime/arith.asm` supplies the C16 unsigned 32-bit helpers without a DOS/CRT
dependency. The independent implementation is tested in the native C16 image.

English remains the default; `RB_LANGUAGE=de` selects the same logic with
German CP437 text, including umlauts and `ß`. Output paths remain separate.
Repository documentation uses neutral prose without personal address or
private personal data, as recorded in `AGENTS.md`. The frozen specification
v0.2 and archived material are unchanged in this increment.

Local evidence:

- 97 host tests and the reference layout report pass.
- Two byte-identical HDD builds per language.
- 88 boot cases, including 39 identical EDD/CHS sector-sequence pairs.
- Native C16 assertions: 26 menu/timer, 51 partition parser and 114 volume/
  arithmetic assertions, each exercised through both BIOS read paths.
- Per language: 75 general menu states, 204 scanner states and 318 volume
  states, for 1,194 total. Exact reads/retries, VGA, loaded bytes, BSS, stack
  protection, unchanged source hashes and absence of writes are checked.

The large reference image still exceeds the automatic CHS geometry in QEMU.
This remains a negative test; positive reference campaigns explicitly supply
the documented logical BIOS geometry. The reference layout is unchanged.
CI results and downloadable evidence belong to the PR for this branch.
Only a reviewed merge updates `historical`; a local checkout is not a durable
checkpoint by itself.

## Open work

1. Manually check the new F3 view in both languages, as described in the volume
   guide. Record VM/BIOS or machine details and the displayed read route when
   available. The PR #8 report does not cover this new view.
2. Implement and prove T07 with a purpose-built test VBR: a fresh target read,
   unmodified sector at `0000:7C00`, agreed register/stack state and a stable
   partition-entry pointer. No OS handoff is implemented yet.
3. Add valid profiles and integrate the complete start selection only after
   the handoff is proven. Persistent installation/media identity and target
   authorization are still missing; the current Disk-ID comparison is not
   sufficient for either.

## Resuming after a pause

Begin with the current GitHub branches/PRs, repository code and open items in
this file. Restart interrupted builds/tests; transient emulator state is not
saved project state. Completed increments are committed and proposed as PRs,
which remain open for project review and merge.
