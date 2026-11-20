# Reserving an MBR review number

The standalone BIOS fixture boots from a writable witness floppy in A. A
second writable test floppy holds two publication slots. Reserving a number
advances the generation and the highest issued review number by one while
preserving the original, the latest approved MBR and its predecessor. This
operation releases a number only. The [approval publisher](MbrApproval.md)
uses its successful checkpoint to bind an explicit decision to fresh live bytes.
[Reservation interface](../include/mbr_reservation.h) · [Record format](MbrRestart.md)

## Write and restart contract

1. Read the trusted witness twice. Reject invalid evidence and exhausted
   32-bit counters before any write.
2. After the swap, reopen the current carrier against the witness. Write the
   unchanged approved payload to the inactive slot and verify all 512 bytes.
   Write and verify the new commit header. Reopen the entire staged version
   twice, including the immutable original.
3. On reinserting the start floppy, reread the old witness twice. Its binding,
   counters and both complete sectors must still match. Write and read back
   only the witness header, then verify the complete new witness twice.
4. Return the reserved number after the last check. A failure returns zero.
   A future boot starts with a fresh read of both media.

| Interruption | Outcome on the next boot |
| --- | --- |
| Before the witness changes, including a torn inactive slot | The old checkpoint still selects its intact slot. The unseen number remains available. |
| The witness sector is completely written, but its acknowledgment, final read or return to the caller is lost | The new number is spent. The next successful reservation skips over it. |
| The witness header is torn and fails validation | Issuance stops. A readable older carrier slot cannot authorize a fallback. |
| Either 32-bit counter reaches its maximum | Further reservation stops before either disk is written. |

One writer must have exclusive custody of both enrolled media for the entire
exchange. The storage adapter must preserve write order and return success
only for durable sector writes. Independent readback compares the bytes on
the selected medium. Hardware or host controllers that acknowledge volatile
cache contents require their own durability guarantee. A rolled-back or
cloned witness paired with a matching retained carrier slot can reproduce
old history. Freshness against restoration of the authority itself requires
independent custody outside these two images.

## Standalone media

The fixture recognizes dedicated enrolled carrier and witness IDs. Every
record operation reads and checks the complete physical label before and
after access. The bounded BIOS writer addresses only drive A. It can write
carrier LBAs 3–6 and witness LBA 2877, which is inside the preallocated
`RBWITNES.BIN` FAT12 file. It never writes the original MBR, either label,
the FAT, an HDD or an installed system. The normal rescue and HDD payloads
do not link this writer.

The distributed carrier already contains an unfinished publication in its
inactive slot. Its currently witnessed state is generation 6, issued number
5 and approved revision 3. The first reservation safely reuses the inactive
slot. Only the two mutable test floppies are required.

## Manual VirtualBox test

Extract `mbr-reserve.img` and `mbr-reserve-data.img` once as a writable pair.
Use a BIOS test VM with floppy A and with the HDD and CD detached. Keep the
same extracted files across all boots.

1. Boot `mbr-reserve.img`. At `INSERT DATA DISK AND PRESS ENTER TO RESERVE`,
   exchange A for `mbr-reserve-data.img` and press Enter. After
   `STAGED DATA VERIFIED` and `REINSERT START DISK AND PRESS ENTER`, power
   off the VM with the data floppy still inserted. No number has been released.
2. Reinsert the same start floppy, cold-boot, and repeat the first exchange.
   This time reinsert `mbr-reserve.img` at the second prompt and press Enter.
   Expect `RESERVED REVIEW 6` and `RB MBR RESERVE PASS`.
3. Fully power off and boot the same start floppy again. Complete both swaps
   with the same files. Expect `RESERVED REVIEW 7` and `RB MBR RESERVE PASS`.

## Automated evidence

For each language the suite runs 49 boots, including ten abrupt power cuts.
Separate QEMU processes boot and mutate temporary copies of the actual
distributed files. Whole-image comparisons verify every byte against an
independent expected result after each boot. The block trace verifies the
address and size of every write, and the VGA and debug logs confirm when a
number became visible. Negative inputs include protected and foreign media,
stale or changed witnesses with matching payload CRCs, and counter limits.

A test BIOS option ROM interrupts the first, second or third physical write
before completion, after completion and after a 128-byte prefix. It can also
silently drop a write, report failure after applying it, or corrupt only the
final witness read after all three writes have completed. Each interrupted
or ambiguous run is followed by a fresh unmodified SeaBIOS process on the
exact files left by the previous process. The interactive diskette exchange
and normal consecutive reservations also run without an option ROM.
