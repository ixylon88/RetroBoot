# RetroBoot

A BIOS boot manager for classic x86 PCs: isolated primary DOS/Windows 9x
systems, shared data volumes and optional chainloading of existing NT loaders.
Development currently targets the `historical` branch.

**Current stage: read-only profile, installation-state and visibility checks.**
The custom MBR uses BIOS EDD or automatic CHS fallback to load the hidden FAT16
management volume and a fragmented Stage 2 file. Custom startup code establishes
the C environment, clears BSS and passes the BIOS context to C. The separate
C/assembly test floppy remains available. F5 now validates stored start-profile
records against the actual disk layout. F6 compares independent installation
records with the current target VBR. F7 previews current and intended primary
partition types and active flags. OS authorization, chainloading,
partition changes and installation are future steps. An independent test VBR now
checks the real-mode transition in an explicitly selected test image.

## Documentation

- [English and German builds, character encoding](docs/Languages.md)
- [Current specification v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build commands, verification and next steps](docs/Entwicklung.md)
- [BIOS/ABI test floppy](docs/ABI_Probe.md)
- [HDD boot, memory contract and QEMU/VirtualBox instructions](docs/HDD_Boot.md)
- [Menu operation and verification](docs/Menue.md)
- [MBR/EBR checks and their limits](docs/Partitionen.md)
- [F3 FAT volume header checks and their limits](docs/VolumeHeaders.md)
- [T07 test-VBR handoff and manual test](docs/Handoff.md)
- [F5 configuration copies, profile format and manual check](docs/Configuration.md)
- [F6 installation state, identity binding and manual check](docs/InstallationState.md)
- [F7 current/intended partition preview and manual check](docs/Visibility.md)
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

The full test runs 96 boot cases covering both BIOS read paths, the 8 GB
reference layout, fragmented files and injected failures. Each language also
runs 75 general menu states, 204 scanner/error/paging states and 318 volume
header states, 185 handoff states, 678 configuration states, 650 installation-state states
and 370 visibility states through emulated keyboard input, with VGA, memory
and disk-write checks: 4,960 states across both languages. There are 117 host tests.

The compact 64 MiB image opens an 80×25 text menu after the startup checks.
Arrow keys select, Enter opens a page, Esc returns, F2 scans MBR/EBR tables,
Page Up/Down changes partition pages and F8 opens recovery information.
F3 checks FAT16/FAT32 headers; Left/Right cycles through data partitions.
Header plausibility does not establish filesystem integrity or OS bootability.
F5 reads the two configuration files and displays validated profile descriptions.
F6 checks independent installation records and the current target VBR.
F7 previews current and intended primary-partition visibility and active flags.
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
confirmed; F7 is the new manual check.

For T07, boot `retroboot-handoff.img` and press **F4 from the main menu**.
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
| `boot/` | MBR, FAT16 VBR and bootstrap |
| `core/` | Stage 2 startup, C entry, menu, partition/header/configuration parsers and linker script |
| `bios/` | VGA, keyboard, BIOS ticks and sector-reader C interface |
| `runtime/` | ABI/BIOS helpers, HDD unsigned 32-bit arithmetic and linker end markers |
| `.github/workflows/` | Host and BIOS checks for pull requests to `historical` |

Operating-system media and BIOS ROMs are not included in this repository.
