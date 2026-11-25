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

## Changing the countdown on a prepared disk

The existing RetroBoot DOS hard disk supplies the installation and its identities.
With the VM powered off, dragging the currently attached prepared disk onto
`RetroBoot-Countdown.cmd` displays its saved delay. Entering a number from
0 to 60 confirms the new delay on a **new disk copy**, written beside the
launcher as `RetroBoot-DOS-Countdown.vdi`. An empty response cancels.
The command-line equivalent for disabling the timer is:

```text
python3 RetroBoot-DOS.pyz RetroBoot-DOS.vdi --set-countdown 0 --output RetroBoot-DOS-Countdown.vdi
```

For the VirtualBox check, the new disk goes on the primary IDE master
(port 0, device 0) in place of the previous disk. With a zero delay the German
menu shows `Automatischer Start: aus`. It waits past the previous timeout and
Enter starts MS-DOS 6.22. Another cold boot still waits. Reattaching the
previous disk returns to the original delay. To create another VDI in the
same directory, the command line accepts a fresh output name.

The editor reads the live MBR, EBR and DOS boot sector on the private copy.
It checks the hidden volume's complete file allocation, both FATs, both
ready-state records, the two idle journals and the disk, media, profile and
installation identities. Both version-2 configuration copies must validate.
Equal generations must agree byte for byte. Successive generations may
differ in the timer, generation and CRC. Any other disagreement requires
separate diagnosis.

A change advances the generation in the inactive configuration sector.
Identical peers select A, so the first update writes B. The next update
writes A. An unchanged delay consumes no generation, and a change at
`0xFFFFFFFF` is rejected. The tool rechecks the disk after confirmation,
flushes the new sector, and reads both copies back through the selector
before publishing the output name. Interruption or failed verification
leaves the input disk available for boot or retry. Firmware reads the
usual configuration records at cold boot. Installation-state updates and
editing from inside the BIOS menu are tracked in #48.

## Recovering an interrupted countdown update

The external DOS kit can restore the saved delay when one configuration copy
has a bad checksum and its profile and disk identity still match the valid
peer. On a powered-off prepared disk, `RetroBoot-Countdown-Recovery.cmd`
shows the valid file, its generation and delay, and the sector to replace in
the new image. The German kit accepts `J` and the English kit accepts `Y`.
An empty response cancels. The command-line equivalent is
`python3 RetroBoot-DOS.pyz input.vdi --recover-countdown --output recovered.vdi`.

Recovery copies the verified sector into the damaged slot and retains its
generation, including at `0xFFFFFFFF`. It checks allocation, installation
identity and the idle journal again after confirmation, flushes the write,
and reads both sectors back before publishing the disk. Two healthy copies
need no repair. Two bad checksums, a disagreement outside the countdown
fields or conflicting valid copies stop the operation. The input disk stays
available for retry.

### VirtualBox test

1. Extract `RetroBoot-Countdown-Recovery-DE.zip` or its English counterpart
   from the `retroboot-dos` CI artifact. The included
   `RetroBoot-Countdown-Test.img` contains the project-owned test boot sector.
   Copy A holds a zero delay. Copy B contains an interrupted change to one second.
2. Drag that IMG onto `RetroBoot-Countdown-Recovery.cmd`. Confirm the displayed
   repair of `RBCFG.B` from `RBCFG.A`. The output is `RetroBoot-DOS-Recovered.vdi`.
3. Attach the output as the primary IDE master (port 0, device 0) of a
   powered-off BIOS VM. Boot from the hard disk. The menu waits with automatic
   boot off. Enter reaches `RB HANDOFF PASS`. Power off and start again to
   repeat the check.

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
