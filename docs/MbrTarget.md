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
recovery diskette `mbr-original-data.img`. A current template receives fresh,
distinct target, carrier and witness IDs. The witness is a second record kept
on the start diskette. Both diskettes belong to one preparation. An existing
output is preserved.

## Operating the pair

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

## Source and recovery binding

The supported route is the legacy primary ATA master at ports 1F0h–1F7h with
alternate status at 3F6h, under exclusive controller access. IDENTIFY DEVICE
and the one-sector PIO read of LBA 0 select the same device directly. The
[reader](../core/mbr_ata.c) checks the full identity before and after each
sector read, including the rereads required by [original capture](MbrProvenance.md).
It accepts fixed ATA devices with LBA, printable nonblank model and serial, and
512-byte logical sectors. Capacity uses the supported 48-bit or legacy 28-bit
fields. Busy timeouts, transfer errors, unsupported devices and a bad optional
IDENTIFY checksum stop acquisition. The target adapter has no HDD write command.
Field definitions are in the [ATA command set, IDENTIFY DEVICE](https://read.seas.harvard.edu/cs161/2020/pdf/ata-atapi-8.pdf).

The read-only FAT12 file `RBTARGET.BIN` occupies LBA 2879. Both profile versions
store the tag, target ID (16 bytes), little-endian capacity (8 bytes), carrier
ID (16 bytes), serial (20 ASCII bytes) and model (40 ASCII bytes). ATA strings
are space-padded. The last four bytes contain the CRC32 of the first 508 bytes.

| Profile | Bytes 108–507 | Boot diskette |
| --- | --- | --- |
| `RBTARG01` | 400 reserved zero bytes | Existing capture-only pairs retain the original match, Esc and **E** sequence. Capture seals the original on carrier LBAs 1 and 2. |
| `RBTARG02` | Witness ID (16 bytes) and 384 reserved zero bytes | `RBWITNES.BIN` occupies LBAs 2874–2878. Its label precedes the commit header, original and two alternating approval payloads. |

In the second version, the writer checks the ATA identity before each floppy
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

The independently prepared boot diskette and the recovery diskette remain
under separate custody. ATA identity and copyable floppy labels do not
authenticate hardware cryptographically. General recovery-device enrollment
and targeted restore remain open.
