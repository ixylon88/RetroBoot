# Getting started with RetroBoot test builds

RetroBoot is being developed into a boot manager for classic BIOS PCs.
The current builds demonstrate startup, inspect disk metadata and check saved
backup files. Installation, real backup creation and restoration are still
under development. The published images are test media for a separate VM.

No knowledge of sector addresses or partition-table formats is needed for the
following checks. The useful information is **build, image, screen and key**.
A key by itself is ambiguous: the HDD menu and the rescue floppy are different
programs, and F4 has a different purpose in each.

## First check: a saved file on a demo floppy

This check needs VirtualBox on an x86 host and one floppy image. No guest OS,
installation ISO or virtual HDD is required. A previously working RetroBoot
test VM can be reused, with its power off when changing the boot image.

### 1. Download the matching build

1. Open the [RetroBoot Actions page](https://github.com/ixylon88/RetroBoot/actions)
   and select **BIOS ABI probe**.
2. Open the successful run for the intended PR or `historical` revision.
   Record its link. A green run for an older commit is a different build.
3. Under **Artifacts**, download **retroboot-rescue-diagnostics** and extract
   the ZIP into a new directory named for that run.
4. Select one image from the table below. English and German use the same
   program logic; the language is fixed in each image.

GitHub requires a signed-in account with repository read access for artifact
downloads. These workflow artifacts expire after 30 days. The repository's
**Code → Download ZIP** contains source files, not the compiled test images.
An artifact may also be uploaded after a failed run, so its presence alone
does not establish a successful build.

| Image inside the extracted artifact | Language | Contents |
| --- | --- | --- |
| `rescue/retroboot-rescue-demo.img` | English | Program plus a synthetic backup example |
| `rescue-de/retroboot-rescue-demo.img` | German | Program plus the same synthetic example |
| `rescue/retroboot-rescue.img` | English | Program without a backup file |
| `rescue-de/retroboot-rescue.img` | German | Program without a backup file |

For this first check, the filename ends in **`-demo.img`**. Every image in this
table is a 1,474,560-byte floppy image. The example is synthetic and cannot be used to restore a disk.

### 2. Attach the floppy in VirtualBox

With the test VM powered off:

1. In **Settings → System**, select legacy BIOS by disabling **UEFI/EFI**.
   Set **Floppy** first in the boot order.
2. In **Settings → Storage**, add a floppy controller if absent. Add its first
   floppy drive and choose the selected `retroboot-rescue-demo.img` as A:.
3. Start the VM. The title must read **RetroBoot Rescue**, with **Read only**
   or **Nur lesen** at the right.

The floppy `.img` is attached directly as a raw floppy image. HDD-to-VDI
conversion is only relevant to the separate HDD tests below. VirtualBox label
wording can vary with version and interface language.

### 3. Run the file check

From the initial **RetroBoot Rescue** page, press **F4**. The page now names
the saved file **RBBACKUP.RBB** on floppy A:.

| Field | Expected demo result | Meaning |
| --- | --- | --- |
| File / check / detail | `0x0000 / 0x0000 / 0x0000` | File access and saved-content checks passed |
| Record detail | `0x0000` | No nested record error |
| Volumes / FAT16 / FAT32 | `0x0002 / 0x0001 / 0x0001` | Two saved volumes: one of each format |
| Reserved sectors | `0x0021` | 33 sectors in hexadecimal notation |
| Matching READY VBRs | `0x0001` | One saved start-sector checksum matches its saved record |
| Floppy / saved-disk error LBA | Both `0x00000000` | No error location reported |
| Descriptor kind / index | `0x0000 / 0x0000` | No rejected descriptor reported |

The green message concerns the **saved file**. It does not confirm that an
attached HDD matches that file, that an OS boots, or that restoration is ready.

**Enter** repeats this file check. **Esc** returns to the initial HDD diagnosis
page. Enter on that initial page checks an attached HDD instead; without one,
the expected diagnosis is **BIOS reports no HDD**. F4 still checks the floppy
file without an HDD.

## Next check: compare with the matching HDD

The new **F5** page compares the saved file with an attached HDD. This needs
an additional file from the **same successful build**:
`rescue/retroboot-rescue-target-hdd.img`. Its copy under `rescue-de/` is identical.
The ordinary HDD and handoff images are different test fixtures.

The [F5 setup guide](RescueTargetCheck.md#manual-virtualbox-check) gives the
complete procedure: convert this new 128 MiB image into a new VDI, attach it
as the first IDE HDD, and boot the demo floppy as A:. From **RetroBoot Rescue**,
press **F5**. Expected: a green match message and check/detail/nested
`0x0000 / 0x0000 / 0x0000`. **Enter** repeats, **F4** returns to the saved-file check,
and **Esc** returns to diagnosis. With the HDD detached, F5 instead reports
`0x0003 / 0x0001 / 0x0000`; successful identity fields must be blank.

This pair contains synthetic test metadata. A green match confirms only the
supported comparison; no installation, restoration or OS start follows.

## Next check: preview a backup read plan

**F6 in RetroBoot Rescue** lists the sectors a future metadata backup would
need. This works on either normal or demo rescue floppy/CD, without a saved
backup file. It still writes nothing.

The current `retroboot-rescue-target-hdd.img` must be converted into a **new
VDI**: the older F5-only image lacks a FAT32 header now needed for planning.
With the current pair, F6 should show a green message, four zero codes, eight
ranges, two volumes and an estimated 23,040 bytes. **Right/Left** switches
between two pages; **Enter/F6** repeats from page one; **Esc** returns to
diagnosis. The [F6 guide](BackupCapturePlan.md#manual-virtualbox-check) includes
the exact values and optional no-HDD check.

## Which image and which key?

An optical drive can now replace the rescue floppy. The **retroboot-rescue-cd**
artifact contains English and German `retroboot-rescue-demo.iso` files. Attach
the ISO directly as a BIOS CD/DVD, eject the old floppy and place Optical first
in the boot order. No VDI conversion is needed for an ISO. The
[CD guide](RescueCD.md) gives the exact paths and short check. The same screen,
F4/F5/F6 results and matching HDD apply; references to floppy A: describe BIOS
emulation from the CD.

The following routes remain separate. The image names and screen titles identify
the test even when a chat message or screenshot is no longer nearby.

| Image and starting screen | Key sequence | Purpose and expected result |
| --- | --- | --- |
| `retroboot-rescue-demo.img`, **RetroBoot Rescue** | **F4** | Check the example backup file; the table above applies |
| `retroboot-rescue.img`, **RetroBoot Rescue** | **F4** | Expected missing-file result `0x0005 / 0x0000 / 0x0000` |
| `retroboot-rescue-demo.iso`, **RetroBoot Rescue** | **F4**, then **F5** with the matching HDD | Same saved-file and target checks, booted from CD |
| Demo rescue floppy plus `retroboot-rescue-target-hdd.img`, **RetroBoot Rescue** | **F5** | Compare saved/current metadata; expected `0x0000 / 0x0000 / 0x0000` |
| Either rescue floppy/CD plus the current target HDD, **RetroBoot Rescue** | **F6**, then **Right/Left** | Preliminary range/size plan; four zero codes, eight ranges, two pages |
| Either rescue image, initial diagnosis page | **Enter** | Read the first HDD's partition metadata; outcome depends on the attached HDD |
| `retroboot-hdd.img` or `retroboot-handoff.img`, **RetroBoot** menu | **F10** | Audit allocation of the eight management files; expected `0x0000 / 0x0000` |
| Either HDD image, **RetroBoot** menu | **F8**, then **Enter** | Read the transaction journal; see [journal diagnosis](JournalDiagnosis.md) |
| `retroboot-handoff.img`, **RetroBoot** menu | **F7**, then **F9** | Check the selected test profile, then run the test sector: `RB HANDOFF PASS` |
| `retroboot-handoff.img`, **RetroBoot** main menu | **F4** | Earlier isolated test-sector handoff: `RB HANDOFF PASS` |

The handoff test ends at a small test program. Restarting the VM returns to
RetroBoot. It does not launch DOS or Windows. The normal `retroboot-hdd.img`
has no handoff action. Detailed HDD setup, including conversion to a new VDI,
is in [HDD_Boot.md](HDD_Boot.md). Its images come from **HDD BIOS boot →
retroboot-hdd-bios**, under `hdd/` for English and `hdd-de/` for German.

**F4 checks the saved file; F5 compares it with current HDD metadata; F6
previews a backup read plan.** All three belong to the rescue program, on floppy or CD. HDD-menu F5 instead selects start-profile
configuration; the image and screen title remain essential.

## When the result differs

| Observation | First check |
| --- | --- |
| The title is **RetroBoot**, although a rescue test was intended | The HDD probably booted; check rescue floppy/CD attachment and boot priority |
| F4 reports `0x0005 / 0x0000 / 0x0000` | The normal rescue image intentionally has no backup; select `-demo.img` for the example |
| F5 reports `0x0001 / 0x0005 / 0x0000` | The backup file is absent; use the demo floppy |
| F5 reports `0x0003 / 0x0001 / 0x0000` | No HDD was found; check the target VDI attachment |
| F5 reports a capacity or identity difference | Confirm the matching target HDD image and a newly converted VDI |
| F6 rejects the volume header after an earlier successful F5 | Convert the current target HDD image into a new VDI; older F5 fixtures lack that header |
| Enter reports no HDD | This is expected with no HDD attached; F4 remains available |
| An HDD check still shows an older result or file count | Confirm the artifact run and replace any VDI converted from an older image |
| A key has no effect | Check the current screen, then click inside the VM to give it keyboard focus |
| Another status or a startup error appears | Record the exact result with its image, screen and key; consult the linked feature guide |

Diagnostic numbers belong to a particular page. A nonzero number can be an
expected result, such as the deliberately absent backup file. Conversely, zero
codes on one page say nothing about checks on another page.

A short text report is sufficient; screenshots are optional:

```text
Build: PR/commit and workflow-run link
Image: artifact name and exact path inside the ZIP
Environment: VirtualBox version; attached test HDD or no HDD
Screen and keys: RetroBoot Rescue → F4
Observed: file/check/detail; any differing message or counter
Repeat/return: Enter and Esc checked, or not checked
```

## Reading numbers and byte sequences

`0x00123456` is one hexadecimal number. `56 34 12 00`, under a **Bytes**
label, is a sequence of four separate bytes in their stored order. The two
can represent the same 32-bit value when its storage format is little endian.
The 16-byte media identity uses the byte-pair form; LBA addresses, capacities,
CRCs and status codes use numeric values. Decimal page and slot numbers stay
decimal. Older screenshots omit the prefix but show the same values.

## Terms used in the diagnostics

| Term | Plain meaning |
| --- | --- |
| Image / `.img` | A file containing the bytes of an entire virtual diskette or disk |
| ISO / `.iso` | A CD/DVD image; the rescue ISO emulates the embedded diskette through the BIOS |
| VM | A virtual PC, such as a VirtualBox machine |
| BIOS | Firmware that starts this classic PC before an operating system runs |
| MBR / EBR | Tables describing where disk partitions begin and end |
| VBR | The first sector of a volume, containing its format information and potentially startup code |
| FAT / cluster | The filesystem's allocation table / a group of sectors assigned to a file |
| LBA | A sector's numbered position; an error location, not a command to enter |
| CRC | A checksum for detecting inconsistency; it does not prove authenticity |
| READY | A saved installation-state label; additional checks are needed before an OS start |
| PR / CI / artifact | Proposed changes / automatic build and test runs / their downloadable output |

The [current project state](Arbeitsstand.md) records completed work and remaining
steps. Feature documents hold the detailed codes; the specification is intended
for implementation work. A later installation and recovery manual will need
the finished procedures, supported machines and recovery tests before those
operations can be described as available.

External references: GitHub's [artifact download procedure](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)
and Oracle's [VirtualBox 7.2 VM settings](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/working-with-vms.html).
