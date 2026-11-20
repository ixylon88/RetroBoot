# Identifying the source disk before the first MBR capture

An independently prepared boot diskette identifies one hard disk by its complete
ATA model, serial number and capacity in 512-byte sectors. The guest first shows
the expected and observed values. A different serial number blocks capture even
when the two disks have the same model, capacity and identical sectors.

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
recovery diskette `mbr-original-data.img`. Each invocation assigns fresh target
and carrier IDs. An existing output is preserved. The template and source HDD
are never opened for writing by the preparation tool.

## Checking and capturing

1. A BIOS VM boots the personalized `mbr-target.img` in drive A with the target
   as the primary IDE master. The boot diskette can be write-protected.
2. `TARGET MATCH` means all three enrolled fields match. Esc finishes the
   check. A missing or different disk ends at `RB ATA TARGET BLOCKED` before
   any HDD sector read or carrier write.
3. When first-install custody has independently been established before any
   installation write, **E** selects capture. At the prompt, the matching
   writable `mbr-original-data.img` goes in A. Enter saves the original.
   Success ends with `ORIGINAL REV 1 VERIFIED` and `RB ATA TARGET PASS`.
   A cold repeat compares the sealed original and the live MBR byte for byte.
   A different carrier or changed sealed original blocks the operation.

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

The read-only, one-sector FAT12 file `RBTARGET.BIN` in the boot image occupies
LBA 2879. It contains `RBTARG01`, target ID (16 bytes), capacity (8 bytes
little-endian), carrier ID (16 bytes), serial (20 ASCII bytes), model (40 ASCII
bytes), 400 reserved zero bytes and a trailing CRC32. Text is space-padded.
The initial capture reuses the existing recovery label, record layout, seal
and readback checks. Only carrier LBAs 1 and 2 are writable through this path.

The operator retains custody of the boot profile and its paired recovery
medium. A copied recovery label or duplicated ATA identity can be replayed.
The ATA fields and record CRC provide no cryptographic authentication. This
increment covers original capture on the specified IDE route. General
recovery-device identification, binding this route to independent witness and
approval flows, additional controllers and targeted restore remain open.
The [guest campaign](../tools/test_mbr_target.py) compares screen output,
device reads and writes, and every persisted byte.
