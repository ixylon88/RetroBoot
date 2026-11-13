# RetroBoot

A BIOS boot manager for classic x86 PCs: isolated primary DOS/Windows 9x
systems, shared data volumes and optional chainloading of existing NT loaders.
Development currently targets the `historical` branch.

**Current stage: read-only HDD checks and independent rescue-floppy diagnosis.**
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

- [English and German builds, character encoding](docs/Languages.md)
- [Current specification v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build commands, verification and next steps](docs/Entwicklung.md)
- [BIOS/ABI test floppy](docs/ABI_Probe.md)
- [Independent FAT12 rescue-floppy diagnosis and manual check](docs/ExternalRescue.md)
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

The host tools require Python 3.12 and its standard library. With GNU Make:

```sh
make check
```

Without Make, for example on Windows:

```powershell
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

The **retroboot-rescue-diagnostics** artifact in the **BIOS ABI probe** workflow
contains `rescue/retroboot-rescue.img` and `rescue-de/retroboot-rescue.img`.
Both are FAT12 floppies with an independent loader and C startup. They boot
without a working HDD MBR, FAT16 bootstrap or Stage 2. Enter probes the first
HDD and reads its MBR/EBRs; Esc clears the diagnosis. There is no write,
restore or OS-start action. Media identity and backup binding remain open.

For the next manual test, attach either image as floppy A: in the existing
BIOS VM, boot floppy first and press **Enter**. With the existing normal HDD
fixture, expect `0000 / 0000` and boot/target `0000 / 0080`. The HDD image
needs no replacement or VDI conversion for this increment. The
[rescue guide](docs/ExternalRescue.md) includes the no-HDD test and limitations.
Automated rescue checks add 76 boots and 434 VGA/keyboard states across both
languages. The original ABI floppy remains unchanged.

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
across both languages. There are 140 host tests.

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
