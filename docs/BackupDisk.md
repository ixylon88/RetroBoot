# First durable metadata backup on a dedicated IDE recovery disk

The BIOS start diskette offers **S** to save and **V** to verify. The system
disk is the primary IDE master. The separate recovery disk is the secondary
IDE master. The operating system, its boot code and Stage 2 are unnecessary
for verification. The bilingual VirtualBox kit contains two prepared,
disposable disks with a synthetic layout and an already approved MBR history.

## VirtualBox check

1. With the BIOS VM powered off, attach `RB73-System.vdi` at IDE port 0,
   device 0 and `RB73-Sicherung.vdi` at IDE port 1, device 0.
2. Boot `Deutsch/backup-disk.img` or `English/backup-disk.img` in A and
   select **S**. The program reports 45 verified sectors and approved MBR
   revision 2, followed by `RB BACKUP DISK PASS`.
3. Power off and detach the system disk. Leave the recovery disk and start
   diskette attached. Boot from A and select **V**. The German completion
   screen includes the following lines.

```text
Sicherung von der Sicherungsfestplatte gelesen.
Geprüfte Sektoren 45
Freigegebene MBR-Revision 2
RB BACKUP DISK PASS
```

The [German VirtualBox check on 21 November 2026](https://github.com/ixylon88/RetroBoot/pull/73#issuecomment-7065510774)
confirmed both the save and the cold verification with the system disk detached.
Both operations displayed 45 verified sectors and approved MBR revision 2.

## Source and publication

The read-only profile and witness on the start diskette retain the enrolled
hardware identities and original and approved MBR checkpoints. The matching
carrier holds independent copies. The primary disk supplies the actual EBRs,
FAT boot areas and management records. Planning requires BIOS EDD and checks
each BIOS drive 80h read against the same LBA on the identified primary IDE
master. The PIO check supports the first 2²⁸ sectors. The existing
[completion check](BackupVerification.md) reopens the provisional bytes on
the secondary disk and compares them with a fresh live serialization. Each
ATA write is followed by FLUSH CACHE.

| Recovery disk LBA | Content |
| --- | --- |
| 0–6 | Existing recovery label and MBR history |
| 7 | Provisioned store label, including the three enrollment IDs and bounded slot capacity |
| 8 | Single publication sector, initially zero |
| 9–15 | Reserved; the publication sector has its own aligned 4 KiB region |
| 16 onward | Contiguous version-1 `.rbb` file, up to 2,048 sectors |

All counts in the store records are little endian. The layout sector begins
with `RBSTORE1`, followed by the 16-byte target, carrier and witness IDs,
a 32-bit capacity, zero padding and a CRC32 over the first 508 bytes. The
publication sector starts with `RBDONE01` and the same IDs. Five 32-bit
fields record file sectors, witness generation, approved revision and the
two ordered body/tail fingerprints. Zero padding and the sector CRC follow.
The fixed LBA bounds are enforced independently by the low-level writer.
The session checks the actual ATA identity, carrier label, allocation and
free space before writing. Each data write rechecks the empty slot.

Publication writes LBA 8 last, after successful independent readback. A
zero publication sector permits a fresh attempt and leaves staged bytes
unavailable to **V**. Any occupied slot blocks **S**, including a damaged
publication record. The first version supports one published snapshot per
provisioned disk. A retry never replaces an existing completed snapshot.
A failure reported while the final publication sector is being written or
flushed has an uncertain physical outcome. A fresh **V** determines whether
a complete valid publication reached the disk.

Verification reopens and checks the container, saved records, complete FAT
boot areas, both ordered fingerprints and both exact MBR sectors. It rechecks
the separately held witness, the carrier and the complete publication sector.
An unissued revision, a mismatched carrier, a short or corrupted file, or
an interrupted candidate fails verification. This check confers no restore
authority. Targeted restoration is tracked in #46.

## Automated evidence

`tools/test_backup_disk.py` boots separate QEMU processes for publication and
cold verification. An independent host encoder predicts every byte of the
resulting 45-sector file and publication record. The campaign compares both
complete disks against expected contents, checks each ATA write and flush,
and verifies the boot diskette and stack guard. Failure cases cover insufficient
capacity, an occupied slot, a different or absent drive, final-sector I/O
errors, a flush error, interrupted publication, a damaged last sector and a
substituted approved MBR with a matching sector CRC. The package builder boots
the extracted source and recovery VDIs in both languages, powers them down,
and opens each saved backup in a fresh VM with the source detached.

### Recovery disk removed during an operation

The QEMU test pauses at a selected secondary-disk transfer before the guest
receives its result. The monitor detaches the recovery disk's backing image.
The test verifies that the image is absent and that the other drives still
have their original media, then resumes the same guest. A fresh VM reopens
the exact recovery image left by the preceding boot. This exercises loss of
the medium while the IDE controller is still present.

| Point of removal | Result in the running VM | Result after reconnecting the disk |
| --- | --- | --- |
| Eighth data-sector write | Save stops after seven successfully flushed data sectors | **V** reports an empty publication slot |
| Final publication write | Save stops with all 45 data sectors flushed and the publication sector empty | **V** reports an empty slot. A fresh **S** publishes the complete file |
| Read of the final data sector of an already published backup | **V** reports a failed verification | A fresh **V** reads the original 45 sectors and MBR revision 2 with the system disk detached |

The campaign checks the complete recovery image against independently
predicted bytes after each boot. The source disk and the start diskette stay
byte-identical throughout the sequence.

## From MBR capture to a cold-verified backup

The combined `mbr-backup.img` diskette offers **1** for MBR capture and
approval and **2** for metadata backup. Both choices reopen the same enrolled
disk pair and the same witness on the diskette. The boot sector checks the
length and CRC32 of the selected program before starting it.

For a new pair, `tools/prepare_mbr_target.py` accepts the combined template
and the ATA model, serial and capacity of each disk. For example, the
following invocation uses the identities and capacities of the disposable
VirtualBox fixtures. It creates `pair/mbr-backup.img` and a new sparse raw
recovery hard-disk image, `pair/mbr-recovery.img`. The recovery disk starts
with its carrier and allocation labels, an empty MBR history and an empty
publication sector. The existing capture-only templates retain their layout.

```sh
python3 tools/prepare_mbr_target.py build/rescue-de/mbr-backup.img \
  --model 'VBOX HARDDISK' --serial VB75757575-11111111 --sectors 262144 \
  --recovery-model 'VBOX HARDDISK' --recovery-serial VB76767676-22222222 \
  --recovery-sectors 10080 --output pair
```

1. Before installation, boot with the writable start diskette and both
   enrolled disks. Select **1**, then **E** twice to capture the original MBR.
2. After a separate change to the system MBR, boot from the same diskette,
   select **1**, then **R** twice. Review the byte differences and explicitly
   approve the revision (**J** in German, **Y** in English).
3. Boot from A again and select **2**, **S** to save. The file contains the
   captured original, the explicitly approved MBR and the live boot and
   management metadata. A first capture on its own cannot publish a backup.
4. Power off, detach the system disk and select **2**, **V** on the next boot.
   The recovery disk and the independent witness on the start diskette verify
   the saved file and report its approved MBR revision.

`tools/package_backup_handoff.py` runs these steps in both languages. It also
runs the documented preparation command with fresh enrollment IDs and verifies
the resulting raw disk through capture, approval, save and cold read. The
downloadable `RetroBoot-MBR-Sicherung.zip` starts after the actual first
capture, with a four-byte change waiting for review. The test boots the
extracted VDIs, checks the 45-sector file against an independent encoder and
retries with an older witness. A further save with a later, unreviewed live
MBR checks both saved MBR roles byte for byte. The [bilingual VirtualBox
instructions](BackupHandoff.txt) give the three boots for the packaged pair.

The container covers boot and management metadata. User files and operating
systems have their own backup requirements.
