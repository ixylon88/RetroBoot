# Recovering MBR history after a cold boot

The standalone restart probe recovers the original MBR, the last approved
MBR and the highest issued review number from two separately held floppies.
The boot floppy supplies a trusted witness from the enrolled installation.
After that floppy is removed, a BIOS reader checks the recovery carrier
against the witness. The target HDD can be disconnected throughout.

## Manual VirtualBox test

The BIOS ABI and Rescue workflow publishes three images in
`retroboot-rescue-diagnostics` under both language directories. The EN and
DE copies are identical.

1. A BIOS test VM boots from `mbr-restart.img` in drive A with the HDD
   and CD disconnected. The screen displays `WITNESS READY` and
   `INSERT RECOVERY FLOPPY AND PRESS ENTER`.
2. With the VM still running, replace A with `mbr-restart-current.img`
   and press Enter. The screen ends with the five lines below.

```text
ORIGINAL REV 1
APPROVED REV 3
LAST ISSUED 5
PENDING NONE
RB MBR RESTART PASS
```

3. Power off the VM. Put `mbr-restart.img` back in A and boot again.
   At the same prompt, insert `mbr-restart-older.img` and press Enter.

```text
STALE CHECKPOINT
RB MBR RESTART BLOCKED
```

Both data floppies have valid records and contain exactly the same original
and approved MBR bytes. The older floppy records review 3 as its highest
issued number. The trusted witness records review 5. Reopening the older
history would lose the fact that reviews 4 and 5 were already issued.

Both transcripts were confirmed in VirtualBox on 18 November 2026.
[PR #63](https://github.com/ixylon88/RetroBoot/pull/63)

## Records and selection

Each metadata header occupies 512 bytes. The tag selects the record type
and format version. Integers use little-endian encoding. A checkpoint names
one publication generation and the last issued, approved and previous
approved review numbers. An enrollment starts at generation 1 and revision 1.
An approval has a revision of at least 2. Zero means that role has no value.

| Header bytes | Field |
| --- | --- |
| 0–7 | Eight-byte tag `RBWIT001`, `RBORG001` or `RBCMT001` |
| 8–23 | Enrolled target identifier |
| 24–31 | Target capacity in 512-byte sectors |
| 32–47 | Recovery-carrier identifier |
| 48–63 | Four 32-bit numbers for publication generation, highest issued review, latest approval and its predecessor |
| 64–71 | CRC32 values of the original and approved payloads. The absent approval uses zero |
| 72–507 | Reserved zero bytes |
| 508–511 | CRC32 of bytes 0–507 |

The generation must be at least the highest issued number, which must be
positive. An approved revision cannot exceed that number. A predecessor
must be a strictly earlier approval. Generation 1 describes initial
enrollment and has no approval. The witness carries both complete sectors
after its header. A missing approval occupies a zero-filled sector.

| Recovery-carrier logical sectors | Contents |
| --- | --- |
| 0–1 | Immutable enrollment header at revision 1 and the original sector |
| 2–3 | Commit header and approved sector for odd generations |
| 4–5 | Commit header and approved sector for even generations |

The independently retained generation selects the slot. The reader checks
the original and the selected slot twice. Each pass compares the enrollment
IDs, full 64-bit capacity, record types, all revision fields and every
payload byte. Only a complete second pass supplies a result. A later record
staged in the inactive slot can coexist with the last committed state. If
the witness has advanced and the selected slot is missing, torn or stale,
the reader clears the result. It cannot fall back to a previous approval.

The public API reads a separately identified witness and returns a
read-only observation. It has no pending candidate and cannot issue or
accept a review ticket. Reopening an unchanged checkpoint a second time
therefore cannot reuse a consumed review number.
[Native API](../include/mbr_restart.h)

## What the boot test establishes

The boot fixture contains a four-sector FAT12 file `RBWITNES.BIN` at
LBAs 2876–2879. Its first sector identifies the fixture medium and the
following sectors hold the witness. Each nonbootable data floppy starts with
its own medium label at LBA 0 followed by the six logical carrier sectors.
The BIOS adapter re-reads the label before and after each record-sector
read. The label uses `RBMEDIA1`, a 16-byte endpoint ID, 484 reserved
zero bytes and a CRC32 in the last four bytes.

The host build provisions this example enrollment and its approvals. The
[first-witness fixture](MbrProvenance.md#publishing-and-checking-the-first-witness)
also exercises the same reader with an original and a witness written by the
running BIOS code. Each
emulator case starts a fresh process. The regular and unmodified-SeaBIOS
boots use the same distributed files read-only across power cycles. Tests
include loss of an issued number, fully staged and torn inactive slots,
failure of the selected slot with an older good copy, a wrong carrier or
target, and distinct payloads with equal resealed CRC32 values. The runner
checks the full VGA and debug transcript, program and stack guards, media
hashes, physical floppy-read order on instrumented boots, zero HDD reads and
zero guest writes.

After a successful BIOS read of both fixture media, the native test replays the acquired
sectors in RAM. It injects error, short and overlong responses, changed
endpoints and changed bytes at each of the six witness reads and eight
carrier reads. One additional case changes the closing original while
preserving its CRC. Each failure must clear the entire destination.

A trusted operator or installation service must independently establish the
first-install origin, the target and the freshness of the separately held
witness. A copied label cannot authenticate physical hardware. Replaying
both the trusted witness and its matching carrier together requires an
independent record of the latest generation to detect. The read-only probe
assumes that custody and stable media during each acquisition. A separate
[writable fixture](MbrReservation.md) reserves numbers and advances its witness
after verified external staging. Publication of a new approval remains open.
Targeted repair also
requires the independent backup and confirmation gates in the
[provenance contract](MbrProvenance.md#evidence-for-targeted-recovery).
