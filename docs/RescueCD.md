# Booting RetroBoot Rescue from CD

The rescue CD starts the same read-only program as the rescue floppy. The BIOS
presents an unchanged embedded diskette as drive A:, so Enter, F4 and F5 keep
their existing meanings. A physical or virtual floppy drive is not required.
This adds a boot medium, not backup creation or restoration.

## Download and VirtualBox check

From a successful **BIOS ABI probe** run for the intended PR or revision,
download **retroboot-rescue-cd** and extract it into a fresh directory.
The [getting-started guide](GettingStarted.md) explains workflow downloads.

| Path inside the artifact | Language | Saved file |
| --- | --- | --- |
| `rescue-iso/retroboot-rescue-demo.iso` | English | Synthetic `RBBACKUP.RBB` |
| `rescue-iso-de/retroboot-rescue-demo.iso` | German | Same synthetic example |
| `rescue-iso/retroboot-rescue.iso` | English | None |
| `rescue-iso-de/retroboot-rescue.iso` | German | None |

Each ISO is 1,529,856 bytes. For the first CD check, select **`-demo.iso`**.

1. Power off the existing BIOS test VM. Keep **EFI/UEFI disabled**. Eject the
   old floppy image so that a successful start cannot come from that diskette.
2. In **Settings → Storage**, attach the selected ISO directly to an optical
   CD/DVD drive on an IDE controller. No conversion to VDI is needed. Set
   **Optical** before **Hard Disk** in the boot order.
3. Start the VM. The title must be **RetroBoot Rescue**, with **Read only** or
   **Nur lesen**. References to floppy A: are expected: the BIOS emulates it
   from the CD. The initial page performs no HDD diagnosis yet.
4. Press **F4**. Expect the green saved-file result and
   `0x0000 / 0x0000 / 0x0000`. Enter repeats. This needs no HDD.
5. With the matching target HDD attached, press **F5**. Expect the green match
   result and `0x0000 / 0x0000 / 0x0000`. Enter repeats; F4 returns to the file
   check; Esc clears the result and returns to diagnosis.

F5 needs `retroboot-rescue-target-hdd.img` from **retroboot-rescue-diagnostics**
in the same workflow run, converted to a separate VDI and attached as the
first IDE HDD. The [F5 setup guide](RescueTargetCheck.md) gives the procedure
and expected fields. Its bytes are unchanged from PR #24, so an unchanged
matching VDI from that test can remain attached. The ordinary
`retroboot-hdd.img` and `retroboot-handoff.img` are different fixtures.

With no HDD attached, demo F4 still succeeds; F5 reports
`0x0003 / 0x0001 / 0x0000` and leaves identity fields blank. On the normal
ISO, F4 reports the expected missing-file result `0x0005 / 0x0000 / 0x0000`;
F5 reports `0x0001 / 0x0005 / 0x0000`. Enter on the initial diagnosis page
checks the first HDD instead. These page-specific codes are unchanged.

A useful manual report records the workflow run, exact ISO path, language,
VirtualBox version, attached HDD, confirmation that the old floppy was ejected,
and F4/F5/Enter/Esc results. Screenshots are optional. Manual VirtualBox and
physical BIOS CD checks remain pending; earlier floppy results do not establish
CD compatibility. EFI, USB boot and no-emulation CD boot are outside this path.

## Build and automated evidence

The native Linux toolchain remains the one described in [ABI_Probe.md](ABI_Probe.md).
Python 3.12 additionally needs the hash-pinned dependency in
[`tools/requirements-iso.txt`](../tools/requirements-iso.txt):

```sh
make iso-deps
make toolchain
make rescue-check RB_LANGUAGE=en
make rescue-check RB_LANGUAGE=de
make rescue-iso-test RB_LANGUAGE=en
make rescue-iso-test RB_LANGUAGE=de
```

An isolated Python environment can be selected with `PYTHON=path/to/python`.
`make rescue-iso` packages existing verified rescue images without rebuilding
them; it requires their current language manifest and checks their SHA-256
values. Output is under `build/rescue-iso/` and `build/rescue-iso-de/`.
The package manifest records ISO and embedded-floppy hashes, catalog/image
addresses and the packaging version. Both ISOs are built twice and compared.

PyCdlib 1.22.0 writes ISO9660 level 1 and an x86 El Torito catalog using
1.44 MiB floppy emulation. The catalog selects media type 2, the default
load address and one initial 512-byte sector. No boot-info table is patched;
all 1,474,560 embedded floppy bytes must equal the existing image. ISO dates
are fixed at 1980-01-01 UTC, including the library's freshly serialized PVD
modification date. Independent raw-field checks cover catalog checksum,
routing, image bounds and payload equality. Host tests also check directory
mapping, dates, clock/timezone independence and rejection of damaged inputs.
There are **181 host tests** in total.

Each language adds **19 CD boots / 171 keyboard and VGA states** in QEMU:
ten with the BIOS-call observation ROM, then nine without that ROM. Both
campaigns boot from the optical drive with no attached floppy. They cover
the actual published demo/normal ISOs, missing HDD/file, damaged saved content,
capacity/identity mismatch and MBR/record read failures. The instrumented
campaign additionally forces CHS. The nine-state sequence exercises F5,
Enter, F4, Esc and ordinary diagnosis, including repeated comparisons.

Both campaigns check exact HDD read sequences, VGA text/attributes, memory
and stack bounds, unchanged media and absence of guest block writes. The ROM
campaign additionally checks BIOS discovery calls and virtual-floppy read
sequences; the bare campaign has no such floppy-call observation and labels
its floppy addresses as expected values only. Evidence is in
`rescue-iso-test/`, `rescue-iso-test-de/`, `rescue-iso-test-bare/` and
`rescue-iso-test-bare-de/`, including `match-results.json`, VGA/RAM dumps,
screenshots and read traces. Every result identifies the boot medium and
whether the BIOS-call ROM was attached.

These **38 boots / 342 states** supplement the existing floppy campaigns
(188 boots / 1,244 states). Guest binaries, floppy/HDD images, validators,
disk formats and UI catalogs are unchanged. A green comparison still means
supported metadata correspondence only, not unique physical identity,
snapshot provenance or permission to restore.

Format references: Phoenix/IBM's
[El Torito Bootable CD-ROM Format Specification 1.0](https://www.ardent-tool.com/storage/specscdrom.pdf)
and the maintainer's [PyCdlib API reference](https://clalancette.github.io/pycdlib/api/pycdlib.html).
