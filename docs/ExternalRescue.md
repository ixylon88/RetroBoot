# Independent rescue-floppy diagnosis

The FAT12 floppy starts its own C program without executing the HDD MBR,
management VBR, FAT16 bootstrap or Stage 2. Enter probes BIOS drive `80h`
afresh and reads its MBR and bounded EBR chain. This first external increment
is **read-only diagnosis**. Backup import, independently verified media identity,
targeted restore, ISO boot and installation are still open.

The [ABI floppy](ABI_Probe.md) remains a runtime test without FAT or HDD access.
The [HDD F8 page](JournalDiagnosis.md) depends on a working HDD loader.
Neither that page nor this floppy is a completed recovery implementation
under specification v0.2.

## Manual check

The **retroboot-rescue-diagnostics** artifact in the **BIOS ABI probe** workflow
contains these normal images:

| Language | Artifact path | Size |
| --- | --- | ---: |
| English | `rescue/retroboot-rescue.img` | 1,474,560 bytes |
| German | `rescue-de/retroboot-rescue.img` | 1,474,560 bytes |

1. With the BIOS test VM powered off, attach the selected image as floppy A:
   and place floppy before hard disk in the boot order. In VirtualBox this is
   a floppy-controller attachment, not a raw-to-VDI conversion. The existing
   PR #17 HDD test image can stay attached as the first HDD. The four
   published HDD images are unchanged by this increment.
2. Boot. The title is **RetroBoot Rescue**, with **Read only** or **Nur lesen**.
   The initial page requests Enter; the rescue program has not read HDD sectors.
3. Press **Enter**. A normal compact or handoff fixture produces a green
   result, probe/layout `0000 / 0000`, boot/target `0000 / 0080`,
   signature/marker `AA55 / 0001` and entries/EBRs `0005 / 0001`.
   The count includes all four primary slots, including unused slots.
   Disk ID and MBR CRC describe the attached image; they are not identity
   authorization. Capacity depends on the image and BIOS route.
4. Press **Enter** again. With unchanged media, the observations remain equal.
   **Esc** clears the diagnosis; Enter performs new discovery and reads.
   F4 and F9 have no action. There is no HDD handoff.
5. Optionally repeat with the HDD detached while the VM is powered off.
   The floppy still starts. Enter then reports `0001 / 0000`, with no retained
   capacity, identity, CRC or partition-count fields.

The German rescue floppy was confirmed under VirtualBox on 13 November 2026
with both published HDD fixtures, no HDD and an unrelated HDD. The initial
page without diagnostic fields was also shown. Observed values:

| Attached medium | Reachable sectors, hex | Probe/layout | Disk ID | MBR CRC32 | Signature/marker | Entries/EBRs |
| --- | --- | --- | --- | --- | --- | --- |
| Compact 64 MiB fixture | `0000000000020000` | `0000 / 0000` | `52425431` | `90835F6A` | `AA55 / 0001` | `0005 / 0001` |
| Handoff 128 MiB fixture | `0000000000040000` | `0000 / 0000` | `52425431` | `E75726EB` | `AA55 / 0001` | `0005 / 0001` |
| No HDD | Blank | `0001 / 0000` | Blank | Blank | Blank | Blank |
| Unrelated 2 GiB HDD | `0000000000400000` | `0000 / 0000` | `00000000` | `4661F29B` | `AA55 / 0000` | `0004 / 0000` |

Attached disks used EDD; boot/target was `0000 / 0080`. The unrelated disk's
zero observed ID grants no identity match. Its count includes the four primary
slots and does not establish four populated partitions. No VirtualBox/BIOS
version, separate repeated-Enter/Esc result, English manual test, I/O trace,
physical-hardware coverage or original-OS start was established by this report.
Evidence is retained as text; PR #18 is merged into `historical`.

A visible QEMU start with the existing compact fixture is available as:

```sh
qemu-system-i386 -machine pc-i440fx-8.2,accel=tcg -cpu 486 -m 16 \
  -drive file=build/rescue/retroboot-rescue.img,format=raw,if=floppy,readonly=on \
  -drive file=build/hdd/retroboot-hdd.img,format=raw,if=ide,snapshot=on \
  -boot a -nic none -no-reboot
```

## Builds and evidence

```sh
make toolchain
make rescue-test RB_LANGUAGE=en
make rescue-test RB_LANGUAGE=de
```

`make rescue` builds once; `make rescue-check` builds twice and compares all
binary artifacts and manifests. Output directories are `build/rescue/` and
`build/rescue-de/`; evidence is under `build/rescue-test/` and
`build/rescue-test-de/`. The builder uses the pinned NASM/Watcom toolchain.
Separate `ui/rescue/` catalogs reuse the CP437 encoder, including umlauts and
`ß`, without changing HDD catalogs.

The diagnostic scope is 38 boots and 217 keyboard/VGA states per language:
76 boots and 434 states total, plus 28 native C/16 assertions in each rescue
model boot (`R=001C`, `RB RESCUE MODEL PASS`). The subsequent
[container model](ExternalBackup.md), [saved-record model](BackupRecords.md)
and [FAT boot-area model](BackupBootAreas.md) each add one test-only boot per
language, bringing the current total to 82 boots and 434 states. Host checks
now total 161 tests. Diagnostic coverage includes:

- Metadata-only HDDs with no executable boot path or filesystem contents,
  unrecognized boot code, erased MBRs, bad MBR/EBR signatures, unsupported
  GPT-protective type, looping EBRs and actual block-read errors/retries.
- EDD/CHS, absent disks, invalid BIOS capability/geometry/capacity replies,
  an uninstrumented boot and exact sector sequences. The successful fixture
  reads only LBAs `0, 63, 0` per Enter; other tested keys perform no HDD reads.
- Floppy BIOS retries, persistent read failure, corrupt payload/header,
  invalid initialized data and omitted BSS clearing. CRC failure produces
  `RB RESCUE LOAD ERROR`; C startup failure produces
  `RB RESCUE STARTUP ERROR`. Neither reaches the normal UI.
- Every UI state's text, fields, colors, cleared fields, unchanged program,
  zeroed BSS, stack guard and unused memory. Screenshots supplement direct
  VGA-byte comparisons.
- Unchanged source-media and disposable HDD-copy hashes, no staged HDD
  boot-sector handoff, no IDE/block writes and no BIOS write attempts in
  instrumented cases. The disposable raw HDD is writable so a write cannot
  be masked by a read-only attachment. Fixed physical/logical geometry avoids
  QEMU's own MBR geometry probe consuming a once-only error before boot.

CI reuses the ABI job and toolchain setup, publishing both rescue images and
their evidence separately. Damaged floppy variants and HDD fixtures are not
published as bootable downloads. Reports require every campaign to pass;
artifacts from failed jobs are partial evidence. Local tests use QEMU
10.0.13/SeaBIOS, `pc-i440fx-8.2`, CPU `486`, 16 MiB RAM. CI records its actual
QEMU and ROM hashes. Physical BIOS compatibility remains outside this evidence.

## Format and trust boundary

The 1,440 KiB superfloppy has 512-byte sectors, one sector per cluster, one
reserved sector, two nine-sector FAT12 copies and 224 root entries. Data starts
at LBA 33; there are 2,847 data clusters. `RBRESCUE.BIN` is contiguous from
cluster 2. File dates are fixed at 1980-01-01; unused final file-sector bytes
are `A5h`. Independent host vectors decode FAT12 packing and reconstruct the
file, including FAT entries crossing a sector boundary. The format follows the
[Microsoft FAT specification, version 1.03](https://www.isdaman.com/alsos/protocols/fats/fatgen103.pdf).

The boot sector pins the layout, payload length and whole-file CRC32. It reads
one floppy sector per call, with at most three attempts, checks the complete
payload before jumping, then establishes its own C startup. This is not a
general FAT12 loader: moving or replacing the file requires rebuilding the
paired image. CRC detects corruption; it is not cryptographic authentication.
The medium is defined for floppy A: (`00h`) and the first HDD (`80h`).
Additional disks and alternate boot-drive numbering are not selected.

Code/data/BSS/stack share segment `1000h`, with the existing 48 KiB file limit,
guard at `E000h` and stack top `FFFEh`. Payload sizes are 8,410 bytes EN and
8,478 bytes DE. Fresh BIOS discovery establishes only a reader context. An
unavailable EDD read capability selects validated CHS geometry; EDD parameter
failure does not silently fall back. Sector size must be 512 bytes.

The diagnostic captures the first MBR, parses its bounded table/chain, then
rereads and compares all 512 MBR bytes. Initial/final MBR read failure or a
change clears the selected observations. Parser failure retains only the raw
MBR observation and error location, without partial successful partition counts.
This is not an atomic snapshot of all EBRs, backup validation, a durable-history
proof or permission to write. A plausible partition layout says nothing about
the missing HDD loader/files in the metadata-only fixtures.

| Probe status, hex | Meaning |
| --- | --- |
| `0000` | MBR observation completed; the separate layout code still applies |
| `0001` | No HDD reported in the BIOS data area |
| `0002` | Invalid EDD parameters or reader context |
| `0003` | Invalid CHS geometry |
| `0004` | Initial/final MBR read failed after bounded retries |
| `0005` | MBR changed during observation |

Layout codes follow the [partition scanner contract](Partitionen.md).
An EBR read failure is a layout error with its LBA; it does not turn the raw
MBR observation into a verified partition map.

The independent boot portion of T16 and floppy portion of T17 now have bounded
evidence. Full acceptance remains open: an external backup must bind media
identity, geometry and all required MBR/EBR/VBR metadata, including FAT32 backup
headers and configuration/state, before a targeted restore can be confirmed.
That recovery path and interruption tests must exist before transaction writes
are enabled. Specification v0.2 remains unchanged.
