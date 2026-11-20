# Identifying the source disk for MBR capture and review

An independently prepared boot diskette identifies one hard disk by its complete
ATA model, serial number and capacity in 512-byte sectors. Capture and review show the expected and observed values. A different serial number blocks either operation before a review number is issued, even when the model, capacity and MBR match. The original and latest approved sector can later be verified with the source HDD disconnected.

## Preparing the external media

The template is `mbr-target.img` in the English or German rescue build.
The model, serial and sector count come from an independently checked inventory
of the intended device. An example with synthetic identifiers is:

```sh
python3 tools/prepare_mbr_target.py build/rescue-de/mbr-target.img \
  --model "VBOX HARDDISK" --serial VB69696969-11111111 --sectors 10080 \
  --output target-pair.zip
```

The new ZIP contains the personalized `mbr-target.img` and its dedicated
recovery diskette `mbr-original-data.img`. The diskette pair receives fresh,
distinct target, carrier and witness IDs. The witness is a second record kept
on the start diskette. Both diskettes belong to one preparation. An existing
output is preserved.

## Operating the diskette pair

The personalized `mbr-target.img` boots in drive A. **P**, **E** and **R**
use the first IDE master. The HDD is only read. **E** and **R** need writable
diskettes. Each prompt names the image to insert in drive A before Enter.

| Key | Operation | Result |
| --- | --- | --- |
| **P** | Compare the enrolled ATA model, serial and sector count with the attached disk. | `TARGET MATCH` or a blocked check. |
| **E** | Under independent first-install custody, before the first installation write, capture the complete original on `mbr-original-data.img`, then return to `mbr-target.img` to publish its first witness. | `INITIAL WITNESS PUBLISHED`. The initial revision is 1. |
| **R** | Reserve a review number on the same pair. Compare the current MBR with the last approved sector, or with the original on the first review. **J** (German) or **Y** (English) approves after the last difference. Esc rejects. | An approval stores the new revision alongside the original. A rejected review consumes its number and preserves the previous approval. |
| **V** | Check the witness on the start diskette and insert the recovery diskette once. Both diskettes may be write-protected. | The screen reports the original, the last approval and the highest issued review number. The HDD can be disconnected. |

The rescue diagnostics contain a prepared pair in `mbr-review-test-ata-de/`
and `mbr-review-test-ata/`. Each pair went through first capture and explicit
approval in the guest. **V** on the two images from one directory reports:

```text
ORIGINAL REV 1 VERIFIED
APPROVED REV 2
LAST ISSUED 2
RB ATA TARGET PASS
```

## Using a dedicated IDE recovery disk

The source disk is the primary IDE master. The separate recovery disk is the
secondary IDE master. The start diskette stays in drive A and retains the
independent witness. The drive that holds the backup is enrolled by its own
model, serial and capacity. A copy of its sectors on another drive with a
different serial is rejected before any saved record is read.

The preparation tool accepts the independently checked ATA fields of both
disks. It creates a new directory with `mbr-target.img` and a newly labelled,
sparse raw `mbr-recovery.img` of the requested recovery capacity. It opens
only the new image files for writing. Source and recovery must have distinct
model/serial combinations, including when their capacities differ. The
following example uses synthetic device identities.

```sh
python3 tools/prepare_mbr_target.py build/rescue-de/mbr-target.img \
  --model "VBOX HARDDISK" --serial VB69696969-11111111 --sectors 10080 \
  --recovery-model "VBOX HARDDISK" --recovery-serial VB71717171-11111111 \
  --recovery-sectors 10080 --output new-recovery-pair
```

**P** compares both installed drives and checks the external label. **E** and
**R** display the observed identities and require confirmation before writing
to the recovery disk. The original, review decision and witness use the same
publication and retry rules as the diskette pair. **V** verifies the saved
original, approved MBR and last issued number with the source disk disconnected.

The [packaging check](../tools/package_mbr_recovery.py) writes the bilingual
`RetroBoot-Sicherungsfestplatte.zip` to `mbr-review-test-recovery-package/`
in the GitHub rescue diagnostics. For the prepared VirtualBox test, the VM boots `mbr-target.img` from A.
The supplied `Sicherung.vdi` occupies the **secondary IDE master** (IDE port 1,
device 0). **V** reports `RECOVERY MATCH`, original revision 1, approval 2
and `RB ATA TARGET PASS`. Replacing it at the same port with `Vergleich.vdi`
offers identical guest-visible sectors under a different serial and ends at
`RB ATA TARGET BLOCKED`. Both runs are read-only. A virtual CD/DVD occupying
that port can use a different IDE position in the test VM.

## Source and recovery binding

The source route is the legacy primary ATA master at ports 0x1F0–0x1F7 with
alternate status at 0x3F6, under exclusive controller access. IDENTIFY DEVICE
and the one-sector PIO read of LBA 0 select the same device directly. The
[reader](../core/mbr_ata.c) checks the full identity before and after each
sector read, including the rereads required by [original capture](MbrProvenance.md).
It accepts fixed ATA devices with LBA, printable nonblank model and serial, and
512-byte logical sectors. Capacity uses the supported 48-bit or legacy 28-bit
fields. Busy timeouts, transfer errors, unsupported devices and a bad optional
IDENTIFY checksum stop acquisition. The primary adapter only issues IDENTIFY and a read of LBA 0.
Field definitions are in the [ATA command set, IDENTIFY DEVICE](https://read.seas.harvard.edu/cs161/2020/pdf/ata-atapi-8.pdf).

The read-only FAT12 file `RBTARGET.BIN` occupies LBA 2879. All profile versions
store the tag, target ID (16 bytes), little-endian capacity (8 bytes), carrier
ID (16 bytes), serial (20 ASCII bytes) and model (40 ASCII bytes). ATA strings
are space-padded. The last four bytes contain the CRC32 of the first 508 bytes.

| Profile | Bytes 108–507 | Boot diskette |
| --- | --- | --- |
| `RBTARG01` | 400 reserved zero bytes | Existing capture-only pairs retain the original match, Esc and **E** sequence. Capture seals the original on carrier LBAs 1 and 2. |
| `RBTARG02` | Witness ID (16 bytes) and 384 reserved zero bytes | `RBWITNES.BIN` occupies LBAs 2874–2878. Its label precedes the commit header, original and two alternating approval payloads. |
| `RBTARG03` | Witness ID (16 bytes), recovery serial (20 bytes), model (40 bytes), little-endian capacity (8 bytes), 316 reserved zero bytes | Same independent witness file. The read-only profile additionally identifies the secondary master. |

In the diskette-pair version, the writer checks the ATA identity before each floppy
write. On selection and before writing the witness it checks the original
profile, FAT copies, directory entries and file extents. The carrier writer
accepts LBAs 1–6 according to the publication phase. First capture seals the
original before the initial carrier checkpoint. Returning to the start
diskette publishes the witness header last. A cold retry can finish from a
matching staged record. **V** checks the saved sectors in full against the
independently retained witness.

The [capture campaign](../tools/test_mbr_target.py) exercises the earlier
profile. The [paired history campaign](../tools/test_mbr_ata_history.py)
exercises the full ATA capture, review and detached verification, including
wrong disks, exchanged media, interrupted publications and equal-CRC sectors.
See [MBR approval](MbrApproval.md) for the publication sequence and freshness
rules.

For `RBTARG03`, the secondary channel is fixed at 0x170–0x177 with alternate
status at 0x376. Reads check the observed identity before and after each
sector transfer. The device and the enrolled label at LBA 0 must agree for
each record access. The sole HDD write entry point selects only the secondary
master and accepts only LBAs 1–6. An individual write must complete and the
same drive must acknowledge FLUSH CACHE before the publisher reads the sector
back. A timeout or error stops publication. Both endpoints are rechecked before
writing the external disk or advancing the independent witness. The raw
recovery image reserves its first seven sectors for the label, immutable
original (header and sector) and the two alternating checkpoint slots. The
source MBR and the remainder of the recovery disk stay outside the writer's
address range. [ATA command and IDENTIFY word definitions](https://read.seas.harvard.edu/cs161/2019/pdf/ata-atapi-8.pdf).

The [two-drive guest campaign](../tools/test_mbr_recovery_disk.py) checks full
images, per-drive I/O and the order of writes and cache flushes. It reboots
with the source disconnected, substitutes a copy with a different serial,
and exercises interruptions and stale records. The external boot diskette,
independent device inventory and recovery disk remain under trusted custody.
ATA identities and on-disk labels are not cryptographic credentials. Other
controller families and the targeted restore gate are separate work.
