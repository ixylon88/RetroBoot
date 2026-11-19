# MS-DOS 6.22 from the RetroBoot menu

The DOS kit creates a new BIOS hard disk from a local MS-DOS 6.22 installation.
The source is a powered-off, bootable disk with a single active FAT16 primary
of type `06h`, below 2 GiB and inside the original BIOS CHS reach. The system
volume has its original boot sector and the usual DOS system files in its root.
A standard 128 MiB VirtualBox IDE disk with a full DOS installation is one
suitable starting point. With VirtualBox snapshots, the input is the currently
attached disk in the snapshot chain. Installation media remain local.

## VirtualBox

1. Extract `RetroBoot-DOS.zip`. The `retroboot-dos` CI artifact contains the
   English menu under `hdd` and the German menu under `hdd-de`.
2. On Windows with Python 3 and VirtualBox installed, drag the DOS disk file
   onto `RetroBoot-DOS.cmd`. The resulting `RetroBoot-DOS.vdi` appears beside
   the launcher. On other hosts the equivalent command is
   `python3 RetroBoot-DOS.pyz "/path/to/MS-DOS.vdi"`.
3. Attach `RetroBoot-DOS.vdi` as the only hard disk (first IDE port) of a
   BIOS-mode DOS VM. Boot from the hard disk and select **MS-DOS 6.22**.
   Enter starts the selection. The default also starts after ten seconds.
   Esc cancels the countdown.
4. At the DOS prompt, type `VER` and press Enter to display the version.
   This manual command also works with an empty `AUTOEXEC.BAT`.

The command also accepts raw disk images and supports `--output` and
`--countdown 0..60`. Zero disables automatic boot. An existing output is
never overwritten. The DOS input holds the original system files. The public
kit contains RetroBoot and the preparation tool.

## Preparation and boot checks

The host copies the source disk, retains the full DOS partition at its original
LBA, appends a hidden logical FAT16 management volume, and installs the RetroBoot
MBR on the new copy. It preserves the original DOS partition entry and every
original byte after sector zero. A source without a disk signature receives
one on the copy. The empty journal records the complete new MBR and EDD capacity.
The generated VDI stores the DOS heads and sectors per track as its logical
BIOS geometry. The [VirtualBox VDI format](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Storage/VDICore.h)
defines this field.

During boot, the menu binds its selection to the displayed profile. Enter and
timeout use the same path. That path reloads the configuration and installation
state, requires a clean journal baseline, verifies partition visibility and
the original boot-sector CRC, and passes the same sector and its matching
partition entry to the [real-mode handoff](Handoff.md). The final sector-zero
observation must match the baseline. The BIOS CHS geometry must match the DOS
boot sector and cover the entire DOS partition. The prepared disk uses a BIOS
with EDD. RetroBoot performs only reads during this path.

Automated English and German tests import an owned instrumented boot sector,
exercise Enter, timeout and cancellation, verify its entry registers and sector
bytes, and reject changed sectors, stale selections, a withdrawn default or incompatible geometry. This tests the
boot manager. On 19 November 2026 the maintainer confirmed the handoff,
normal DOS operation and version 6.22 in VirtualBox.
[Manual test report](https://github.com/ixylon88/RetroBoot/pull/65#issuecomment-7001210054)
Installation of DOS from its original media and switching between systems are
later roadmap items.
