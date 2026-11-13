# Project state and resumption

Updated: 13 November 2026.

## Saved baseline

PR #18 (independent read-only rescue diagnosis) is merged into `historical` at
`b696df7e2665168289e51ac69b5ef2a42063a91d`. Its four PR checks passed.
The German rescue floppy was manually confirmed under VirtualBox with the
64 MiB compact fixture, 128 MiB handoff fixture, no HDD and an unrelated 2 GiB
HDD. The initial page was also shown. Exact observations and coverage limits
are recorded as text in [ExternalRescue.md](ExternalRescue.md).

PR #17 remains the read-only HDD journal baseline.
F8 followed by Enter reads the identity-bound A/B journal records and compares
the current MBR; F10 audits eight management files. The manual procedure
provided after PR #17 was reported checked and confirmed. No additional
image/language, machine/BIOS, individual field values or separate key-path
observations were supplied for that earlier report.

The F10 status `0000 / 0000` was separately confirmed on 13 November 2026.
English F7 followed by F9 from PR #14 was confirmed under VirtualBox that day:
matching preview, `0000 / 0000 / 0000`, unchanged masks, the F9 hint and
`RB HANDOFF PASS`. No BIOS version, physical-hardware coverage or original-OS
start was established. Earlier reports cover the ABI floppy, HDD/C startup,
menu, partition scanner, English/German builds, F3, isolated T07, F5/F6 and
German F7. Their coverage remains limited to the reported results.

## Current increment: external metadata container

Branch `codex/external-backup-format` defines a bounded sector-based container,
a Python encoder/inspector and a streaming native C/16 validator. Its header
stores claimed media/disk identity, layout, capacity and geometry; descriptors
carry original/approved MBRs, EBRs, multi-sector or discontiguous boot areas and
configuration/state copies. Bounds, ordering, overlap, required roles and CRCs
are checked. Failed validation clears all selected metadata.

The [container contract](ExternalBackup.md) specifies the wire format, status
codes, host command and exact trust boundary. Structural validity does not
prove snapshot completeness, record semantics, provenance, live-media identity
or permission to restore. Only synthetic format examples are generated. Real
collection, rescue file loading, independently checked target binding and
restore remain open. No normal-menu change or new manual VM check is needed.

Verification adds nine host tests (149 total) and 72 native scenarios with
216 assertions (`B=00D8`, `RB BACKUP MODEL PASS`) per build language. The model
includes a 1 MiB streamed file, boot areas over 64 KiB, 42 descriptors, separated
boot regions, resealed malformed fields, payload damage and final-sector I/O
failure. Normal rescue binaries/images are unchanged; backup code is linked
only into an additional model variant.

## Independent rescue baseline

Merged PR #18 adds a separate 1,440 KiB FAT12
floppy in English and German. It has its own CRC-pinned loader, C startup,
BIOS discovery and MBR/EBR diagnostic page. No HDD code or filesystem is needed
to start. Enter reads drive `80h`; Enter repeats; Esc clears. The observed disk
ID is explicitly not an independently verified identity. There is no backup
import, disk writer, restore, HDD handoff or ISO yet.

The [external rescue guide](ExternalRescue.md) contains the manual procedure,
format, codes, trust boundary and evidence. CI publishes the two floppies as
**retroboot-rescue-diagnostics** in the existing ABI workflow. The earlier ABI
floppy and four normal/handoff HDD images remain byte-identical. The
[journal diagnosis](JournalDiagnosis.md) and [journal format](TransactionJournal.md)
remain the HDD baseline.

Verification scope:

- 149 host tests plus the reference layout report, including the container tests.
- Rescue: both languages built twice, 38 boots and 217 UI states each
  (76 boots, 434 states total), including absent/damaged HDDs, EDD/CHS,
  BIOS faults, read retries and rejected floppy/C-startup variants.
  Each native rescue model executes 28 assertions (`R=001C`).
  The additional backup-model boot brings the current total to 78 boots and
  434 UI states across both languages.
- Every rescue UI state checks VGA, program bytes, BSS/stack guard,
  exact HDD reads and absence of writes. Source media and disposable HDD
  copies remain unchanged. Independent host vectors decode FAT12 packing
  and file allocation. Payload sizes: 8,410 bytes EN / 8,478 bytes DE.
- Existing HDD scope remains 104 boot cases, 47 identical EDD/CHS sector
  sequence pairs and 7,362 UI states across both languages. Native models
  retain 126 journal, 42 journal-reader, 80 allocation, 26 menu, 51 partition,
  114 volume/arithmetic, 29 handoff, 84 configuration, 86 state, 52 visibility
  and 60 profile assertions. The ABI floppy retains three boot cases.
- Normal HDD Stage 2 remains 38,124 bytes EN / 38,732 bytes DE; handoff
  remains 42,482 / 43,150 bytes. The 48 KiB file and 8 KiB stack budgets remain.

Local native tests use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU `486`
and 16 MiB RAM; CI records its own versions and ROM hashes. PR checks/artifacts
provide validation for the proposed commit; merge remains part of project
review. The German external floppy has the manual evidence recorded above.

English is the default; German shares the logic and CP437 encoder including
`ÄÖÜäöüß`. Repository prose is impersonal and excludes private details.
The frozen specification v0.2 and archives are unchanged.

## Open work

1. Complete independent external recovery before the first write tests:
   collect and import a semantically complete backup using the new bounded
   container, with independent media/geometry binding and
   all required MBR/EBR/VBR metadata, including FAT32 backup headers and
   configuration/state. Add verified, explicitly confirmed targeted restore
   and interruption tests. Diagnosis alone does not satisfy this requirement.
   ISO boot remains open too.
2. Add fresh ownership/identity checks and verified prepare/MBR/completion
   writes with interruption tests after every step. The present observation
   is neither an atomic snapshot, a durable-history proof nor a write lease.
3. Add fresh installation identities and controlled installer state transitions.
   Original-OS starts still need separate authorization and compatibility evidence;
   HDD F9 remains bound to the exact owned T07 test sector.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items above.
Interrupted tests restart; transient emulator state is not a saved checkpoint.
Completed increments are committed and proposed as PRs for project review.
