# Project state and resumption

Updated: 14 November 2026.

## Saved baseline

PR #28 (preliminary capture-plan core) is merged into `historical` at
`d5e01296fad319ac43210ee3a5eb77a895497f3a`. All four PR checks passed;
its rescue binaries/fixtures, four ISOs and case/read/VGA results matched the
local build. The model's `G=0157` and `RB BACKUP PLAN PASS` were subsequently
reported from VirtualBox on 14 November 2026. The long visible address trace
caused confusion. Exact artifact revision, attached drives and VM/BIOS version
were not separately reported. The [plan guide](BackupCapturePlan.md) retains
that text evidence; the supplied screenshot was discarded.

PR #27 (short BIOS CD-mode explanations) is merged into `historical` at
`e353caf22a54c0534f0ba3cd866c3fd1496b13a8`. PR #26 (rescue ISO) was merged at
`6968062d68cead1678fcf75d24f43165901445e0`; all four PR #26 checks passed.
Its published ISOs matched local builds, and all four CD reports matched the
local case/read/VGA results. English F4/F5 success was subsequently reported
from a VirtualBox CD boot. The [CD evidence](RescueCD.md#manual-evidence)
records the values and limits: exact revision, old-floppy removal, VM/BIOS
version, repeats, no-HDD and German CD use were not separately established.
The supplied screenshots were discarded after retaining text evidence.

PR #25 (numeric values and byte sequences) is merged into `historical` at
`c95289b9c4fabc1154b78df6c2d1117f0c1d6865`. All four PR checks passed.
The German initial rescue page and successful F5 result were subsequently
confirmed under VirtualBox on 14 November 2026, including the `0x` notation,
spaced media-ID bytes and German text. The exact values match the
[F5 table](RescueTargetCheck.md#manual-virtualbox-check). Workflow/image paths,
BIOS version, repeat keys and HDD-menu formatting were not separately reported.
The supplied screenshots were discarded after retaining this text evidence.

PR #23 (target-comparison core and beginner guide) is merged into `historical`
at `3e3063903c95b2327efaab583e53f75a2686d258`. All four PR checks passed,
including HDD regression. That baseline has 170 host tests and 140 rescue
boots / 812 UI states. Its native target model has 178 assertions per language
and a 542-read oracle; it introduced no normal-UI action.

PR #22 remains the saved-file baseline. The German demo's F4 result was
manually confirmed under VirtualBox on 14 November 2026: codes and error
locations zero, volumes `0002 / 0001 / 0001`, reserved sectors `0021`, READY
matches `0001`. Enter-repeat and Esc-return were not separately reported.
No English F4, physical-hardware or BIOS-version coverage is implied.

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

## Current increment: live rescue F6 preview

Branch `codex/rescue-capture-preview` integrates the existing read-only planner
with **F6 in RetroBoot Rescue**. A fresh BIOS probe precedes every plan and a
second probe must agree before success. No saved file or F5 result is reused.
The page shows diagnostics, estimated size and five ranges at a time;
Left/Right pages without I/O, Enter/F6 starts over and Esc clears the result.
Failed probes/plans clear all ranges and size. The 908-byte result is on the
existing guarded stack; planner scratch remains private and non-reentrant.

Both normal/demo floppies and CDs support the action. The published target HDD
adds the complete synthetic FAT32 reserved area while preserving its earlier
F5 metadata. A new VDI conversion is required for F6; an old F5 fixture lacks
the system VBR and is correctly rejected. The [beginner guide](GettingStarted.md)
and [F6 procedure](BackupCapturePlan.md#manual-virtualbox-check) identify the
exact files, key sequence and expected eight ranges / two pages / 23,040 bytes.
This is only a preliminary plan: full capture, original-MBR provenance,
current-MBR approval, a writable export destination and restoration remain open.

The standalone model retains 67 scenarios / 343 assertions and the exact
2,122-read oracle. Its long trace now goes only to the debug port; VGA shows
`G=0157` and `RB BACKUP PLAN PASS`, checked independently by the test harness.
The unchanged target model retains 178 assertions and its 542-read trace.

The live F6 campaign adds 19 floppy boots / 194 states per language, plus four
instrumented and three uninstrumented CD boots / 78 states per language.
It checks paging, fresh repeats, F4/F5 transitions, absent/damaged HDDs,
EDD/CHS, failed/changed discovery, read failures and stale-result clearing
following a host mutation. An unread damaged FSInfo sector deliberately still
allows a preliminary plan, testing its stated limit. Four new host tests bring
the total to 190. Full rescue coverage is 280 boots / 2,130 UI states.

Both rescue languages reproduce. Payloads are 33,332 / 33,606 bytes; BSS ends
at 55,646 / 55,920, below the 57,344 stack guard. The German build leaves
1,424 bytes before that guard; the separate 8 KiB stack remains guarded in
every UI state. Disk formats, HDD implementation and frozen specification
are unchanged. Published checks and artifact verification belong to the PR.
Manual confirmation of the new live F6 path is still pending.

## Numeric/byte display and F5 baseline

Merged PR #24 integrates the existing comparison core
with the normal rescue program. F5 opens and fully validates `RBBACKUP.RBB`,
rediscovers the first HDD, performs two independent live-metadata acquisitions,
reprobes the device and revalidates the complete saved file before success.
Ordered half-sector fingerprints also reject tested correctly resealed changes.
Every failure clears successful device/identity/layout/generation fields.
Enter repeats; F4 selects the file-only check; Esc clears to diagnosis.
There are no writes, restore actions or OS starts.

Merged PR #25 displays hexadecimal numeric values with one `0x`
prefix and opaque media IDs as sixteen space-separated byte pairs in stored
order. Both normal HDD menus and rescue pages use this convention in English
and German. Numeric 64-bit fields have one prefix for the complete value;
decimal counters and ASCII debug markers retain their existing form. Status
columns have been widened without changing codes, disk formats or checks.
The [display conventions](Languages.md#numbers-and-byte-sequences) describe the
number/byte distinction. German rescue confirmation is recorded above.

PR #24 is merged into `historical` at
`5fa5c2ac155ca1e3ba908ad2373b3f8e02e16034`. All four checks passed for its
F5 commit `ad6bbb60f96fc1b4d58809a127d54f5913680e79`. PR #25 builds on that tree.

The artifact adds `retroboot-rescue-target-hdd.img`, a nonbootable 128 MiB
synthetic HDD paired with the existing demo backup. It is not the normal or
handoff HDD image. The [F5 guide](RescueTargetCheck.md) gives the exact two-file
setup, new-VDI conversion, expected values and boundaries.

The English F5 success page was manually confirmed under VirtualBox on
14 November 2026: green match, check/detail/nested and record detail zero,
disk ID `52425431`, media ID `A6216F345CD2467790ABC0137D8452E9`, layout CRC
`6FF4FB5E`, management `0000007E / 0001F5C9`, capacity `0000000000040000`,
EDD with zero heads/sectors, generations `00000001 / 00000001` and both
error LBAs zero. The screenshot did not separately establish the workflow
revision, exact image paths, BIOS/version or Enter/F4/Esc results. Evidence
is retained as text; the supplied image was discarded as requested.

Verification at the display baseline: 175 host tests; both rescue builds reproduced; 188 rescue boots /
1,244 UI states. The new 24 nine-state campaigns per language include real EDD
and CHS reads, damaged/missing file or HDD metadata, failed/changed reprobes,
changed and correctly resealed saved content, and stale-result clearing after
an initially successful operation. An independent oracle checks 1,058 HDD and
267 floppy reads for each successful EDD comparison. Native target assertions
and all earlier models remain exercised. Test ROM modes 0..13 are byte-identical
to PR #23. Normal payloads are 29,686 / 29,908 bytes (EN/DE), with BSS ending at
50,440 / 50,662, below the 57,344 stack guard. The HDD menu changes only
presentation; BIOS adapters, validators, disk formats and ABI implementation
sources remain unchanged. CI results remain attached to the proposed PR.

The [core contract](BackupTarget.md) records comparison codes and limitations.
The [getting-started guide](GettingStarted.md) now distinguishes rescue F4,
rescue F5 and HDD F10, including the new matching HDD fixture. Cloned identity,
non-atomic observation and original-MBR provenance remain explicit limitations.

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
collection and restore remain open. The later F5 path compares supported
current metadata, without proving unique physical identity or provenance. The subsequent F4 path loads and validates the file; it does not restore it.

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
file reader. F4 now supplies one; disk writes, restore and HDD handoff remain
unavailable. The current increment adds ISO packaging of the same floppy.

The [external rescue guide](ExternalRescue.md) contains the manual procedure,
format, codes, trust boundary and evidence. CI publishes the two floppies as
**retroboot-rescue-diagnostics** in the existing ABI workflow. The earlier ABI
floppy and four normal/handoff HDD images remain byte-identical. The
[journal diagnosis](JournalDiagnosis.md) and [journal format](TransactionJournal.md)
remain the HDD baseline.

Verification scope:

- 190 host tests plus the reference layout report, including file access, all three backup layers, target comparison, capture planning and ISO packaging.
- Rescue: both languages built twice, 38 boots and 217 UI states each
  (76 boots, 434 states total), including absent/damaged HDDs, EDD/CHS,
  BIOS faults, read retries and rejected floppy/C-startup variants.
  Each native rescue model executes 28 assertions (`R=001C`).
  The additional checker models and file campaigns bring the current total to
  190 floppy boots and 1,244 UI states across both languages before F6.
  F6 adds 38 floppy boots / 388 states. All CD campaigns total 52 boots /
  498 states, bringing the combined scope to 280 / 2,130.
- Every rescue UI state checks VGA, program bytes, BSS/stack guard,
  exact HDD reads and absence of writes. Source media and disposable HDD
  copies remain unchanged except for explicitly recorded host mutations in two
  F5 cases and one F6 case per language; no guest writes occur. Independent host vectors decode FAT12 packing
  and file allocation. Current payload sizes: 33,332 bytes EN / 33,606 bytes DE.
- Existing HDD scope remains 104 boot cases, 47 identical EDD/CHS sector
  sequence pairs and 7,362 UI states across both languages. Native models
  retain 126 journal, 42 journal-reader, 80 allocation, 26 menu, 51 partition,
  114 volume/arithmetic, 29 handoff, 84 configuration, 86 state, 52 visibility
  and 60 profile assertions. The ABI floppy retains three boot cases.
- Normal HDD Stage 2 remains 38,000 bytes EN / 38,610 bytes DE; handoff
  remains 42,342 / 43,012 bytes. The 48 KiB file and 8 KiB stack budgets remain.

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
   read-only F5 path integrates fresh rescue BIOS discovery and file validation
   with the target-comparison core. Unique physical identity and recovery
   authorization remain outside that result. Add verified, explicitly confirmed targeted restore
   and interruption tests. Diagnosis alone does not satisfy this requirement.
   The preliminary range/size plan now has a live rescue F6 path; complete
   source capture and provenance remain open. The rescue ISO has automated CD-boot coverage and
   reported English VirtualBox F4/F5 success; broader manual and physical BIOS
   compatibility remain open.
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
