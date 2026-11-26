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
usual configuration records at cold boot.

## Saving the delay from the HDD menu

On a disk prepared with the F9-capable kit, **F9** opens the DOS boot delay in
the main menu. It displays the saved and proposed values, the destination copy
and its absolute LBA. Left and Right adjust the delay by one second. Home
selects zero (wait for a key) and End selects 60 seconds. Esc discards the
edit. Enter confirms it. Opening the editor cancels automatic boot for the
current session. The stored delay takes effect at the next boot.

The VM must have exclusive use of its disk. Opening the editor and confirming
a change each read the allocation of the eight management files, both FATs,
both configuration and installation records, both idle journals and the DOS
boot sector. The reviewed profile must match its READY installation, the
single active DOS primary and the hidden management volume. The firmware
compares the two raw configuration records and their addresses across both
reads. It also compares fingerprints of the allocation metadata, installation
record and live partition and volume observations.

A confirmed change issues one BIOS EDD write to the inactive configuration
sector. The other sector keeps the previous generation. The firmware then
loads the records and their disk context again. The expected new copy must
win selection and both sectors must match the expected bytes. A reported BIOS
error or a failed readback ends the attempt. A power loss can leave a sector
with a bad checksum. The external recovery procedure below restores the last
valid delay on a copy of that disk. Readback checks what the BIOS returns.
Persistence across loss of host power also depends on the storage cache.

### Cold-boot check in VirtualBox

1. Extract `RetroBoot-Countdown-Menue-DE.zip` or `RetroBoot-Countdown-Menu-EN.zip`
   from the `retroboot-dos` artifact. Attach the included `RetroBoot-F9.vdi`
   as primary IDE master (port 0, device 0) in a powered-off BIOS test VM.
   Boot from the hard disk. This fixture starts with automatic boot off and
   contains the project-owned test boot sector. Older prepared disks retain
   the menu version used to create them.
2. Press F9, press Right three times and confirm with Enter. The screen
   reports a verified delay of three seconds. Power off the VM and start it
   again. Without input, the test sector displays `RB HANDOFF PASS`.
3. Power off and start again. Press F9 before the timeout, then Home and Enter.
   After another cold boot the menu waits until Enter starts the test sector.

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

## Testing the installation boot block

1. Extract `RetroBoot-Startsperre-DE.zip` or `RetroBoot-Boot-Hold-EN.zip` from
   the `retroboot-dos` CI artifact. The included `RetroBoot-Status-Test.img`
   uses the project-owned test VBR and starts with a two-second delay.
2. On Windows with Python 3 and VirtualBox installed, drag that IMG onto
   `RetroBoot-Recovery-Required.cmd`. The review displays `RBSTATE.A` at
   generation 1 in `ready` and `RBSTATE.B` as the destination for generation 2
   in `recovery_required`. Confirm with **J** in German or **Y** in English.
   The new disk is `RetroBoot-DOS-Blocked.vdi`. Enter alone cancels.
3. Attach the new VDI as primary IDE master (port 0, device 0) in a powered-off
   BIOS test VM and boot from the hard disk. The German menu reads
   `DOS-Start gesperrt. Wiederherstellung erforderlich.` and waits.
   F6 shows generation `0x00000002` from copy B and check/detail
   `0x0007 / 0x0007`. Power off and boot again to repeat the check.

The external tool runs on a private copy. The supplied IMG retains its original
two-second delay.
[Installation-state checks and interrupted writes](InstallationState.md#saving-a-dos-boot-block)

## One DOS verification boot

The released test disk starts with the recovery hold already saved. It contains
the project-owned test VBR. A real DOS installation needs its own bootable disk
and its own matching READY record from immediately before the hold.

1. Extract `RetroBoot-Pruefstart-DE.zip` or `RetroBoot-Verification-Boot-EN.zip`
   from the `retroboot-dos` artifact. Attach `RetroBoot-Verify.vdi` as the only
   hard disk on the primary IDE master (port 0, device 0) of a powered-off BIOS VM.
2. Boot from the hard disk. Automatic boot is off. Press **V** to review the
   installation, boot-sector CRC and destination. The supplied image shows
   `RBSTATE.A` and generation `0x00000002 -> 0x00000003`. **Esc** cancels.
   Open the review again with **V** and confirm with **Enter**.
3. The test VBR displays `RB HANDOFF PASS`. Power off and cold-boot the same
   VDI. The German menu shows `DOS-Start gesperrt. Prüfung ausstehend.`
   **F6** shows generation `0x00000003` from A and check/detail
   `0x0007 / 0x0005`. The menu waits for input with the verification key
   and normal DOS entry disabled.

The verification attempt is consumed before handoff. A fresh extraction of the
test disk restores the initial fixture for another run. The result on the
tested disk remains `verification_required` pending a separate decision.
[Verification record and interruption behavior](InstallationState.md#consuming-one-verification-boot)

## Approving an observed verification boot

The test starts with the `RetroBoot-Verify.vdi` that reached `RB HANDOFF PASS`
and subsequently showed generation 3 from A under F6. The approval kit
contains the matching pre-trial reference and the external tool.

1. Power off the VM and extract `RetroBoot-DOS-Freigabe-DE.zip` or
   `RetroBoot-DOS-Approval-EN.zip`. On Windows with Python 3 and VirtualBox,
   drag the **tested** VDI onto `RetroBoot-Confirm-Verification.cmd`.
   The launcher reads the included `RetroBoot-Reference.img` automatically.
2. Review the installation ID, original VBR CRC, both state sectors and saved
   delay. Confirm with **J** in German or **Y** in English. An empty answer
   cancels. The tool writes `RetroBoot-DOS-Ready.vdi` beside the launcher.
   The tested input remains available in its pending state.
3. Attach the new VDI as the primary IDE master. At the menu press **F6**
   before the two-second delay expires. Both pairs show `0x0000 / 0x0000`,
   generation `0x00000004 A`, and check/detail `0x0000 / 0x0000`. F6 is
   a diagnostic view. The main menu starts the test VBR automatically on the
   next cold boot using the saved countdown.

For an actual MS-DOS installation, a successful controlled boot includes
reaching DOS, checking the version with `VER`, and returning to RetroBoot.
The operator records that observation for the installation under test. The
reference disk must come from that same installation. The distributed fixture
reference belongs only to the project-owned test VBR. With VirtualBox snapshots,
the current attached medium supplies the tested state.

```text
python3 RetroBoot-DOS.pyz tested.vdi --confirm-verification held-before-trial.img --output approved.vdi
```

[Record checks and interruption handling](InstallationState.md#approving-a-completed-prepared-dos-trial)

## Selecting a profile from the HDD menu

A prepared HDD with two or three approved DOS/9x profiles on distinct
FAT16 (`0x06`) or FAT32 (`0x0B`) primaries presents them in configuration
order. Each profile must match a READY installation record. The configured default is highlighted,
and the menu waits for a key. F5, F6 and F7 open on the highlighted profile.
F9 editing, automatic boot and the verification-boot command apply to the
single-installation disk.

Enter rereads configuration, installation records and both journal slots.
The selected entry is bound to its displayed identity, target, name and policy
across record reordering. An idle journal must match the current MBR. After
a completed transaction, the current MBR must match the committed after-image.
The final visibility observation must still agree with the cold-boot MBR and
the accepted journal snapshot. The installation proof checks the live VBR.

When the selected primary already has the requested visibility and active
flag, the BIOS geometry is checked and RetroBoot transfers control to that
VBR. When a change is needed, Enter shows the current and proposed type and
active flag of each primary slot. Esc returns to the selection. This path
only reads the disk. Opening the switch review from a main-menu selection
requires **S** on an EDD boot disk. F7 remains a diagnostic view.

### VirtualBox check with two test boot sectors

The archive contains two independently bootable VDIs. Both have profiles
`DOS-Test P1` and `DOS-Test P2` with project-owned test boot sectors. P1 is
active on the first disk. The second represents a completed switch to P2.
Attach one VDI at a time as the primary IDE master (port 0, device 0) in a
powered-off BIOS VM and boot from the hard disk.

| Disk | Selection showing the preview | Selection reaching the test boot sector |
| --- | --- | --- |
| `RetroBoot-P1.vdi` | P2, then Enter | P1, then Enter displays `Test VBR P1 OK.` |
| `RetroBoot-P2.vdi` | P1, then Enter | P2, then Enter displays `Test VBR P2 OK.` |

In either preview the previously active slot changes from type/flag
`0x06 / 0x80` to `0x16 / 0x00`, and the selected slot changes in the
opposite direction. The changed-slot mask is `0x03`. Press Esc before selecting
the active profile. Each successful boot displays `RB HANDOFF PASS` and
the matching slot marker. The German archive is `RetroBoot-Profilauswahl-DE.zip`
and the English archive is `RetroBoot-Profile-Selection-EN.zip`, both in
the `retroboot-dos` workflow artifact.

## Switching profiles on one disk

The German test archive is `RetroBoot-Umschaltung-DE.zip`. The English archive
is `RetroBoot-Partition-Switch-EN.zip`. Each contains one VDI with two
project-owned boot sectors that identify the partition they started from.
The archive provides a fresh P1-active disk for repeating the test.

1. Extract the VDI and attach it as the only hard disk at IDE port 0, device 0,
   in a powered-off BIOS VM. Boot from the hard disk.
2. Select **DOS-Test P2** and press **Enter**. The preview shows P1 becoming
   hidden and inactive and P2 becoming visible and active. The changed-slot
   mask is `0x03`. **S** opens the switch review with journal sequence
   `0x00000002` and the disk ID. **Esc** cancels. **Enter** confirms.
3. The target displays `RB HANDOFF PASS` and `Test VBR P2 OK.`. Cold-boot the
   same VDI. Selecting **DOS-Test P2** and pressing **Enter** now starts P2
   directly. The menu initially highlights P1 because P1 is the configured default.
4. Cold-boot the same disk again. Select **DOS-Test P1**, press **Enter**,
   **S**, then **Enter**. This time the sequence is `0x00000003`, and the
   target displays `Test VBR P1 OK.`.

The firmware reopens the reviewed disk, checks ownership of both journal slots,
and verifies the installation, VBR and geometry before writing. The first
switch on this disk writes five sectors. The return switch writes seven.
The difference comes from previously stored snapshots that already match
the requested bytes. Neither path writes an EBR or a system volume.
[Journal ordering](TransactionJournal.md#confirmed-hdd-switch) · [Interrupted return to P1 in VirtualBox](LaterProfileRecovery.txt)

## Switching between FAT16 and FAT32

`RetroBoot-FAT16-FAT32-DE.zip` and `RetroBoot-FAT16-FAT32-EN.zip`
contain the localized `RetroBoot-FAT16-FAT32.vdi`. The disk starts with P1
active. Each test VBR checks the real-mode handoff and the exact 16-byte
primary partition entry before displaying its slot number.

1. Attach the extracted VDI as the only hard disk on IDE port 0, device 0
   in a powered-off BIOS VM. Eject the rescue floppy and boot the hard disk.
2. Select the target in the table and press **Enter**. Check the types and
   flags in the preview. **S** opens the confirmation. **Esc** cancels
   the review. **Enter** confirms the displayed change.
3. After the slot marker appears, restart from the same VDI for the next
   row. P1 remains the menu default. Pressing **Enter** on the currently
   active profile boots its VBR directly.

| From | Select | New visible type | Changed-slot mask | Expected marker |
| --- | --- | --- | --- | --- |
| P1 | FAT32-Test P2 | `0x0B` | `0x03` | `Test VBR P2 OK.` |
| P2 | FAT32-Test P3 | `0x0B` | `0x06` | `Test VBR P3 OK.` |
| P3 | FAT16-Test P1 | `0x06` | `0x05` | `Test VBR P1 OK.` |

The hidden types are `0x16` for FAT16 and `0x1B` for FAT32.
The test volumes contain two FATs, a root directory and project-owned boot
code. The two FAT32 volumes also have FSInfo and a backup boot region.
Original Windows installations are tracked in [issue #53](https://github.com/ixylon88/RetroBoot/issues/53).

## Protecting an unregistered primary

The profile scope kit contains two independent VirtualBox hard disks.
Both have a FAT16 P1 and FAT32 P2/P3. Only P1 and P2 have an approved
profile. The normal menu checks which physical slots would change before
offering a switch. A READY installation record by itself grants no profile
switch rights. F7 still displays the full partition table for diagnosis.

Use each extracted VDI separately as the only hard disk on IDE port 0,
device 0 in a powered-off BIOS VM. Boot from the hard disk.

| German kit disk | Action | Expected result |
| --- | --- | --- |
| `P3-aktiv.vdi` | Select **FAT32-Test P2** and press **Enter**. | The refusal page names the missing approval and displays slot mask `0x04` for P3. **Esc** returns to the menu. The disk receives zero writes. |
| `P3-verborgen.vdi` | Select **FAT32-Test P2**, press **Enter**, inspect P3, then press **S** and **Enter**. | P3 shows `0x1B / 0x00` in both columns. The changed-slot mask is `0x03`. The target prints `RB HANDOFF PASS` and `Test VBR P2 OK.`. |
| Same disk, after a cold boot | Select **FAT16-Test P1** and confirm the return switch. | The VBR prints `Test VBR P1 OK.`. P3 keeps its original partition entry and contents. |

The archives are `RetroBoot-Profilschutz-DE.zip` and
`RetroBoot-Profile-Scope-EN.zip`. The English disks use the names
`P3-active.vdi` and `P3-hidden.vdi`. Both packages contain project-owned
test boot sectors.

## Preparation and boot checks

The host copies the source disk, retains the full DOS partition at its original
LBA, appends a hidden logical FAT16 management volume, and installs the RetroBoot
MBR on the new copy. It preserves the original DOS partition entry and every
original byte after sector zero. A source without a disk signature receives
one on the copy. The empty journal records the complete new MBR and EDD capacity.
The generated VDI stores the DOS heads and sectors per track as its logical
BIOS geometry. The [VirtualBox VDI format](https://github.com/VirtualBox/virtualbox/blob/main/src/VBox/Storage/VDICore.h)
defines this field.

On a single-installation disk, the menu binds its selection to the displayed profile. Enter and
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
Installation from original media and validation of a switch between two original
operating systems remain later roadmap items.
