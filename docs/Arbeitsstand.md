# Project state and resumption

Updated: 14 November 2026.

## Saved baseline

PR #22 (backup files on the rescue floppy) is merged into `historical` at
`d0348f359bd48ce42d8a4c54bb98e9c25b1f0b43`. All four checks passed, including
the HDD regression workflow. That baseline has 167 host tests and 138 rescue
boots / 812 UI states. The German demo's F4 result was manually confirmed under
VirtualBox on 14 November 2026: codes and error locations zero, volumes
`0002 / 0001 / 0001`, reserved sectors `0021`, READY matches `0001`.
Enter-repeat and Esc-return were not separately reported. No English F4,
physical-hardware or BIOS-version coverage is implied.

PR #21 remains the saved FAT boot-area baseline (65 scenarios / 325 assertions),
PR #20 the saved-record baseline (74 / 296), and PR #19 the container baseline
(72 / 216), per language. No disk writes were introduced.

PR #18 remains the independent read-only rescue baseline; its four checks passed.
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

## Current increment: target-comparison model and beginner guide

Branch `codex/backup-target-check` adds `rb_backup_match_target`, linked only
into a native test model. It independently discovers current MBR/EBR/FAT
metadata and all four configuration/state files, then compares observed
identity, layout, capacity and geometry with supplied backup claims. Backup
addresses never steer physical reads. Two complete acquisitions detect tested
changes, including correctly resealed record changes. No normal UI or BIOS
adapter integration is claimed.

Verification: 170 host tests; both rescue builds reproduced; 140 rescue boots /
812 UI states. The new model runs 178 assertions (`F=00B2`) per language, with
an independently checked 542-read sequence. All 68 previously published
rescue binary/image/ROM/example files are byte-identical to PR #22. Normal
rescue payloads remain 22,158 / 22,296 bytes (EN/DE). HDD and ABI implementation
sources are unchanged. CI results remain attached to the proposed PR.

The [model contract](BackupTarget.md) records failure codes and limitations.
The [getting-started guide](GettingStarted.md) explains downloads, VirtualBox,
images, screens, keys and expected results without assuming hardware expertise.
No new manual VM test is required for this model. In particular, rescue F4
still checks only the saved file; HDD F10 still audits management allocation.

## Backup-file baseline on the rescue floppy

Merged PR #22 adds a read-only F4 path for `RBBACKUP.RBB`
on the boot floppy. A bounded FAT12 reader checks both FATs and all regular
root-file chains before constructing a fragmented file map. The file is then
streamed through the existing container, saved-record and FAT boot-area checks.
Metadata is reread after success. The HDD context is not used or modified.
Enter repeats the selected file check; Esc returns to HDD diagnosis.

The [file-validation guide](RescueBackupFile.md) contains the manual procedure
and status codes. Separate EN/DE `retroboot-rescue-demo.img` images carry
synthetic data and expect `0000 / 0000 / 0000` on F4. The normal images contain
no backup file and expect `0005 / 0000 / 0000`. The German demo has the manual
confirmation recorded above. F4 success is about saved content, never a live
target or restore.

Verification: 167 host tests; 138 rescue boots / 812 UI states; both languages
built twice. A new native model adds eight scenarios / 32 assertions, including
a 1 MiB file map, range rejection, changed metadata, read failure and clearing
of stale maps. Twenty-seven real file/keyboard campaigns per language check
fragmentation, bad media metadata, content errors, retries and HDD-context
isolation. Normal rescue payloads are 22,158 / 22,296 bytes (EN/DE); HDD and
ABI implementations are unchanged. Runtime initialization was separated from
the menu so native checker models remain within the segment budget.

## External container baseline

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
collection, independently checked target binding and
restore remain open. The subsequent F4 path loads and validates the file; it does not restore it.

Verification adds nine host tests (149 total) and 72 native scenarios with
216 assertions (`B=00D8`, `RB BACKUP MODEL PASS`) per build language. The model
includes a 1 MiB streamed file, boot areas over 64 KiB, 42 descriptors, separated
boot regions, resealed malformed fields, payload damage and final-sector I/O
failure. At PR #19, normal rescue binaries/images were unchanged and backup code was
linked only into an additional model variant. F4 now uses the checkers too.

## Independent rescue baseline

Merged PR #18 adds a separate 1,440 KiB FAT12
floppy in English and German. It has its own CRC-pinned loader, C startup,
BIOS discovery and MBR/EBR diagnostic page. No HDD code or filesystem is needed
to start. Enter reads drive `80h`; Enter repeats; Esc clears. The observed disk
ID is explicitly not an independently verified identity. That initial baseline had no backup
file reader. F4 now supplies one; disk writes, restore, HDD handoff and ISO
remain unavailable.

The [external rescue guide](ExternalRescue.md) contains the manual procedure,
format, codes, trust boundary and evidence. CI publishes the two floppies as
**retroboot-rescue-diagnostics** in the existing ABI workflow. The earlier ABI
floppy and four normal/handoff HDD images remain byte-identical. The
[journal diagnosis](JournalDiagnosis.md) and [journal format](TransactionJournal.md)
remain the HDD baseline.

Verification scope:

- 170 host tests plus the reference layout report, including file access, all three backup layers and target-model boundaries.
- Rescue: both languages built twice, 38 boots and 217 UI states each
  (76 boots, 434 states total), including absent/damaged HDDs, EDD/CHS,
  BIOS faults, read retries and rejected floppy/C-startup variants.
  Each native rescue model executes 28 assertions (`R=001C`).
  The additional checker models and file campaigns bring the current total to
  140 boots and 812 UI states across both languages.
- Every rescue UI state checks VGA, program bytes, BSS/stack guard,
  exact HDD reads and absence of writes. Source media and disposable HDD
  copies remain unchanged. Independent host vectors decode FAT12 packing
  and file allocation. Current payload sizes: 22,158 bytes EN / 22,296 bytes DE.
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
   extend supported saved boot formats and validate original-MBR provenance; collect
   a complete backup using the bounded container, saved-record and FAT boot-area
   checkers, with independent media/geometry binding and
   all required MBR/EBR/VBR metadata, including FAT32 backup headers and
   configuration/state. The F4 file-validation path is available, but does not
   establish provenance, live target binding or recovery completeness. The
   target-comparison core is model-tested; integration with fresh rescue BIOS
   discovery and file validation remains open. Add
   verified, explicitly confirmed targeted restore
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
