# RetroBoot

A BIOS boot manager for classic x86 PCs: isolated primary DOS/Windows 9x
systems, shared data volumes and optional chainloading of existing NT loaders.
Development currently targets the `historical` branch.

**Current stage: read-only HDD checks and independent rescue-floppy/CD diagnosis.**
The custom MBR uses BIOS EDD or automatic CHS fallback to load the hidden FAT16
management volume and a fragmented Stage 2 file. Custom startup code establishes
the C environment, clears BSS and passes the BIOS context to C. The separate
C/assembly test floppy remains available. F5 now validates stored start-profile
records against the actual disk layout. F6 compares independent installation
records with the current target VBR. F7 previews current and intended primary
partition types and active flags. F10 audits allocation of the eight current
management files, both FAT copies and unowned allocated clusters. OS authorization, chainloading,
partition changes and installation are future steps. An independent test VBR now
checks the real-mode transition in an explicitly selected test image.

## Documentation

- [Getting started: downloads, VirtualBox, images and keys](docs/GettingStarted.md)
- [English and German builds, character encoding](docs/Languages.md)
- [Current specification v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build commands, verification and next steps](docs/Entwicklung.md)
- [BIOS/ABI test floppy](docs/ABI_Probe.md)
- [Independent FAT12 rescue-floppy diagnosis and manual check](docs/ExternalRescue.md)
- [Bootable rescue CD: ISO download, VirtualBox and verification](docs/RescueCD.md)
- [External metadata container and native validation boundary](docs/ExternalBackup.md)
- [Native metadata encoding and standalone test floppy](docs/BackupEncoding.md)
- [Live payload checksums and standalone test floppy](docs/BackupPayloads.md)
- [Provisional container output and standalone test floppy](docs/BackupStreaming.md)
- [Saved partition/record consistency and remaining recovery checks](docs/BackupRecords.md)
- [F5 rescue file/HDD comparison and matching-image setup](docs/RescueTargetCheck.md)
- [Read-only target-claim comparison core and its limits](docs/BackupTarget.md)
- [HDD boot, memory contract and QEMU/VirtualBox instructions](docs/HDD_Boot.md)
- [Menu operation and verification](docs/Menue.md)
- [MBR/EBR checks and their limits](docs/Partitionen.md)
- [F3 FAT volume header checks and their limits](docs/VolumeHeaders.md)
- [T07 test-VBR handoff and manual test](docs/Handoff.md)
- [F5 configuration copies, profile format and manual check](docs/Configuration.md)
- [F6 installation state, identity binding and manual check](docs/InstallationState.md)
- [F7 current/intended partition preview and manual check](docs/Visibility.md)
- [F9 checked-profile test handoff and manual check](docs/ProfileTest.md)
- [F10 management-volume allocation and manual check](docs/AdminAllocation.md)
- [Transaction-journal format and native observation model](docs/TransactionJournal.md)
- [Saved project state and resumption](docs/Arbeitsstand.md)
- [Windows/Linux CI explained](docs/CI.md)
- [All documents and archived drafts](docs/README.md)

Most detailed design and development documents are currently in German.
Specification v0.2 is authoritative; earlier notes contain superseded layouts.
Repository prose uses impersonal language and excludes private personal details;
the conventions are recorded in [AGENTS.md](AGENTS.md).

## Host checks

The host suite requires Python 3.12 and the pinned ISO packaging library.
With GNU Make on Linux, create an isolated Python environment first:

```sh
python3.12 -m venv build/host-venv
. build/host-venv/bin/activate
make iso-deps
make check
```

Ubuntu's system Python may require the `python3-venv` package for this setup.
The environment keeps the dependency separate from OS-managed Python packages.

Without Make, for example on Windows:

```powershell
py -3.12 -m pip install --require-hashes -r tools/requirements-iso.txt
py -3.12 -m unittest discover -s tests -v
py -3.12 tools/retroboot_layout.py profiles/rb-8g-chs255.json
```

The layout checker reads a JSON plan and prints a report. It does not open
images or physical drives, partition or format media. Successful arithmetic
does not establish BIOS or operating-system compatibility.

## BIOS test floppy

On Linux x86_64 (reference: Ubuntu 24.04), with Python 3.12, GCC, GNU Make
and `qemu-system-x86`:

```sh
make toolchain
make boot-test
```

The toolchain downloads are versioned and SHA-256 checked. The test builds
twice and verifies one successful and two deliberately failing QEMU boots.
`build/abi/abi-probe.img` is an isolated test floppy displaying `RB ABI PASS`.
The **retroboot-abi-probe** CI artifact includes the image and evidence.
It is not an installation or recovery disk.

## Independent diagnostic floppy

```sh
make rescue-test RB_LANGUAGE=en
make rescue-test RB_LANGUAGE=de
```

The **retroboot-rescue-diagnostics** artifact in the **BIOS ABI and Rescue** workflow
contains `rescue/retroboot-rescue.img` and `rescue-de/retroboot-rescue.img`.
Both are FAT12 floppies with an independent loader and C startup. They boot
without a working HDD MBR, FAT16 bootstrap or Stage 2. Enter probes the first
HDD and reads its MBR/EBRs; Esc clears the diagnosis. There is no write,
restore or OS-start action. The separate F5 path compares supported saved and
live metadata; unique physical identity and recovery authorization remain open.

The **F4** path checks `RBBACKUP.RBB` on the boot floppy. The artifact also
contains `rescue/retroboot-rescue-demo.img` and its German counterpart under
`rescue-de/`, with synthetic metadata. Booting a demo as floppy A: and pressing
F4 should produce `0x0000 / 0x0000 / 0x0000`, volumes `0x0002 / 0x0001 / 0x0001`, reserved
sectors `0x0021` and one READY VBR match. Enter repeats; Esc returns to HDD
diagnosis. The normal image intentionally has no backup file (`0x0005 / 0x0000 / 0x0000`).
The [file-validation guide](docs/RescueBackupFile.md) describes the manual test
and boundaries. A matching result never identifies an attached HDD or permits
restoration. F4 alone needs no HDD.

**F5 in RetroBoot Rescue** now compares the saved file with freshly discovered
HDD metadata. The same artifact includes `retroboot-rescue-target-hdd.img`
under both language directories: identical synthetic 128 MiB HDDs matching
the demo backup. The [F5 guide](docs/RescueTargetCheck.md) gives the exact pair,
new-VDI setup, codes and limits. Expected success is `0x0000 / 0x0000 / 0x0000`;
Enter repeats, F4 selects the file-only check, and Esc clears the comparison.
This HDD is nonbootable and is not the ordinary HDD/handoff fixture.

Across both programs, hexadecimal numbers now carry `0x`; media IDs use
space-separated byte pairs in stored order. The [display convention](docs/Languages.md#numbers-and-byte-sequences)
distinguishes numeric values from byte sequences. Decimal counters and debug
markers keep their existing form.

Automated rescue floppy checks cover 252 boots and 1,848 VGA/keyboard states across both
languages. The original ABI floppy remains unchanged.

## Rescue CD

The same workflow also publishes **retroboot-rescue-cd**. Its
`rescue-iso/retroboot-rescue-demo.iso` and German counterpart under
`rescue-iso-de/` start the unchanged rescue program from an optical drive.
The BIOS emulates floppy A: from the CD, so F4/F5 and their expected results
remain the same. Normal ISOs without the example backup are included too.
The [CD guide](docs/RescueCD.md) covers direct ISO attachment in VirtualBox,
the matching HDD and the build commands. No ISO-to-VDI conversion is needed.
CD tests add 56 boots and 538 states, including starts without a test ROM.
The English F4/F5 success pages were reported from a VirtualBox CD boot on
14 November 2026. Exact ISO revision and old-floppy removal were not separately
recorded; the [CD evidence](docs/RescueCD.md#manual-evidence) states the limits.

## Preliminary backup planning

**F6 in RetroBoot Rescue** lists live HDD metadata ranges, estimates backup
size and checks complete supported FAT boot areas, including FAT32 FSInfo,
primary/backup copies and READY first-VBR checksums. Its CRC32 column now shows
each complete live range after two validated payload passes. The
[F6 guide](docs/BackupCapturePlan.md#manual-virtualbox-check) identifies the
exact workflow, good/bad HDD fixtures, keys and expected results.
Both normal/demo floppies and CDs work. The good target still yields eight
ranges, two pages and 23,040 bytes. The new `retroboot-rescue-bad-fsinfo-hdd.img`
must produce `0x0000 / 0x0009 / 0x0007 / 0x0001` and no ranges. No backup file
is written. Enter/F6 repeats; Left/Right pages; Esc clears.

The expanded native model has 139 scenarios / 710 assertions per language.
Its optional `backup-plan-model.img` shows `G=02C6` and `RB BACKUP PLAN PASS`
on VGA; the 2,188-address success trace remains in debug logs. Live F6 tests
cover 86 floppy/CD boots and 884 states across both languages. The preceding
German range preview was confirmed under VirtualBox on 15 November 2026;
manual evidence and its limits are retained in the F6 guide.

The [payload observer](docs/BackupPayloads.md), now used by F6, adds per-extent CRCs
from two freshly validated passes. Its standalone `backup-payload-model.img`
shows `I=03F6` and `RB BACKUP PAYLOAD PASS` without an attached HDD. No payload
bytes are retained, no MBR role is approved and no backup file is written.

The separate [stream assembler](docs/BackupStreaming.md) emits complete
container bytes from explicitly described sources into a provisional sink.
It checks payload CRCs before output and again during output, and rejects
different body/tail fingerprints or callback failures. Its standalone
`backup-stream-model.img` shows `J=03E3` and `RB BACKUP STREAM PASS` without an
HDD.

**F7 in RetroBoot Rescue** runs the complete stream against a reference
`RBBACKUP.RBB`. A fresh BIOS probe brackets the live reads. Each generated
sector is compared with the corresponding reference bytes. The verified count
appears after the closing checks. The intact test pair reports **45 sectors**.
The [F7 guide](docs/BackupLiveSources.md#f7-in-normal-rescue) lists the floppy,
target HDD and expected failures.

The [MBR provenance model](docs/MbrProvenance.md) preserves the pre-installation
original and tracks later explicit approvals. Its standalone test floppy boots
without an HDD and ends with `N=00DB` and `RB MBR PROVENANCE PASS`.
The [cold-start test](docs/MbrRestart.md) boots a trusted witness, then
accepts a current recovery floppy or rejects an older one after a power
cycle. Durable publication and targeted restoration remain open.

## HDD builds and tests

```sh
make hdd-test                   # English: repeat build, boot tests and UI tests
make hdd-ui-test RB_LANGUAGE=de # German: repeat build and the same UI tests
```

English is the default. The menu language is selected at build time; the
program logic is shared. The German catalog includes `ÄÖÜäöüß`. Builds can
alternate between languages without cleaning or overwriting the other output:

```sh
make hdd RB_LANGUAGE=en         # build/hdd/retroboot-hdd.img
make hdd RB_LANGUAGE=de         # build/hdd-de/retroboot-hdd.img
```

The full test runs 104 boot cases covering both BIOS read paths, the 8 GB
reference layout, fragmented files and injected failures. Each language also
runs 75 general menu states, 204 scanner/error/paging states and 318 volume
header states, 185 handoff states, 678 configuration states, 650 installation-state states
and 370 visibility states, plus 336 checked-profile, 370 allocation-audit and 495 journal-diagnosis states, through
emulated keyboard input with VGA, memory and disk-write checks: 7,362 states
across both languages. There are 186 host tests.

The compact 64 MiB image opens an 80×25 text menu after the startup checks.
Arrow keys select, Enter opens a page, Esc returns, F2 scans MBR/EBR tables,
Page Up/Down changes partition pages and F8 opens recovery information.
F3 checks FAT16/FAT32 headers; Left/Right cycles through data partitions.
Header plausibility does not establish filesystem integrity or OS bootability.
F5 reads the two configuration files and displays validated profile descriptions.
F6 checks independent installation records and the current target VBR.
F7 previews current and intended primary-partition visibility and active flags.
F8 followed by Enter reads the transaction journal; Enter repeats the diagnosis.
F10 checks the eight management files and the complete FAT allocation.
Automatic boot remains disabled pending OS-start authorization.

The **HDD BIOS boot** workflow publishes both compact diagnostic images, both
128 MiB handoff-test images and their evidence
in **retroboot-hdd-bios**. These images are test media for an empty BIOS VM.
The [HDD guide](docs/HDD_Boot.md) includes QEMU and VirtualBox instructions.
Manual success was reported for the earlier floppy, HDD startup, menu (PR #6)
and partition scanner (PR #7), followed by the English/German builds (PR #8) and F3 view (PR #9).
T07 from PR #10 was also manually confirmed, without further platform details.
The F5 test from merged PR #11 was also reported complete, without additional
platform or language-coverage details. F6 from merged PR #12 was subsequently
confirmed. German F7 screenshots from PR #13 confirmed both expected views
under VirtualBox. English F7 followed by [F9](docs/ProfileTest.md) was confirmed
there on 13 November 2026: matching preview and `RB HANDOFF PASS`.
No BIOS version, physical-hardware coverage or original-OS start was established.

For the allocation check, boot either current image and press **F10**.
The expected result is a green consistency message, `0000 / 0000` and an
eight-file table. F10 rereads; Esc returns. The [allocation guide](docs/AdminAllocation.md)
records expected counts and limitations. F10 status `0000 / 0000` was manually
confirmed on 13 November 2026, without additional coverage details.

The [journal diagnosis](docs/JournalDiagnosis.md) is available through
**F8, then Enter**. On the standard EDD route, expect a green empty-baseline
message, `0000 / 0000`, journal codes `0000 / 0000 / 0000`, sequence
`00000001`, phase/copy `0000 / A` and equal old/new MBR CRCs. Enter rereads;
Esc returns. The PR #17 manual procedure was reported checked and confirmed,
without additional image/language or platform details. The linked guide
explains the intentionally rejected geometry on a forced CHS boot and the
matching CHS fixtures used in automated tests.

For the checked-profile test, boot `hdd/retroboot-handoff.img`, press
**F7**, then **F9**. A fresh record and visibility check must pass before
the exact T07 sector can run. The expected result is `RB HANDOFF PASS`.
The normal diagnostic image has no F9 action.

For the earlier isolated T07 test, boot `retroboot-handoff.img` and press **F4 from the main menu**.
The expected result is `RB HANDOFF PASS`; rebooting returns to RetroBoot.
F4 is absent from the normal diagnostic image. The [handoff guide](docs/Handoff.md)
describes the contract and why this result does not yet authorize an OS start.

## Source layout

| Path | Contents |
| --- | --- |
| `docs/` | Specification, development status and archived material |
| `profiles/` | Machine-readable layouts, initially RB-8G-CHS255 |
| `ui/` | UTF-8 menu catalogs; converted to CP437 during the build |
| `tools/`, `tests/` | Host tools, native builds, emulator checks and test fixtures |
| `tests/abi/`, `include/` | BIOS probe, C interfaces and memory contracts |
| `boot/` | MBR, FAT16 VBR/bootstrap and independent FAT12 floppy loader |
| `core/` | Stage 2 startup, C entry, menu, partition/header/configuration parsers and linker script |
| `bios/` | VGA, keyboard, BIOS ticks and sector-reader C interface |
| `runtime/` | ABI/BIOS helpers, HDD unsigned 32-bit arithmetic and linker end markers |
| `.github/workflows/` | Host and BIOS checks for pull requests to `historical` |

Operating-system media and BIOS ROMs are not included in this repository.
