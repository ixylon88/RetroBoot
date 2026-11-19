# Saving an explicitly reviewed MBR

RetroBoot can retain a later MBR alongside the original captured before the
first installation write. In the BIOS fixture, **R** reads the current sector
from the enrolled test HDD. The screen identifies both endpoints and the target
capacity. The review lists each changed byte, its offset and
its previous and current values. The comparison starts from the latest approved
sector, or from the original when no approval exists. A long list uses pages.
Approval is available after the last page. Esc rejects the candidate on any page.

## VirtualBox check

The `mbr-review-test-de/` and `mbr-review-test/` directories in the rescue
diagnostics contain the prepared start diskette `mbr-review.img`, recovery
diskette `mbr-original-data.img` and labelled test HDD `mbr-review-hdd.img`.
Each set comes from one BIOS test run. The start and recovery diskettes already
hold the original at revision 1. The test HDD contains a later sector with five
changed bytes and the same CRC32 as the original.

1. A BIOS VM boots `mbr-review.img` from A with the supplied test HDD attached
   as the first IDE hard disk. The VirtualBox test ZIP contains the same HDD
   sectors in `mbr-review-hdd.vdi`. Both diskette images must be writable.
2. **R** starts the review. The two diskette prompts name the image to insert
   in A. After `mbr-original-data.img` and then `mbr-review.img` have been
   inserted and confirmed with Enter, the screen shows `REVIEW 2`,
   `BASE REV 1`, `CHANGED BYTES 5` and the five differences.
3. **J** in German or **Y** in English approves the displayed revision.
   The same two diskette exchanges publish the approved sector.
   The final lines are `APPROVED REV 2` and `RB MBR REVIEW PASS`.
4. A cold boot from the same `mbr-review.img` can check the result with
   the HDD disconnected. **V** requests `mbr-original-data.img` once.
   The screen reports `ORIGINAL REV 1 VERIFIED`, `APPROVED REV 2`
   and `LAST ISSUED 2`. Esc during the original review instead yields
   `REVIEW REJECTED`. In that case **V** reports `APPROVED NONE`
   and `LAST ISSUED 2` on a fresh pair.

## Publication

The [synchronous publisher](../include/mbr_approval.h) owns the two media
and the target exclusively during review. The [number reservation](MbrReservation.md)
must complete before the candidate is presented. Reservation requires space
for two publication generations and consumes one number even if a later read,
decision or write fails. A cold reader has no pending ticket to reuse.

After an explicit approval, a fresh target read must match all 512 reviewed
bytes and the enrolled endpoint. The existing carrier writer verifies the
reserved state, writes the new payload and header to the inactive carrier slot
and reopens that slot twice. The returned witness must still match the reserved
state. The publisher stages the reviewed bytes in the inactive witness payload,
rereads the target, old witness and staged payload, then writes the witness
header last. The complete new witness is loaded twice before success is reported.
Its predecessor is the previous approved revision. A rejected review changes
only the highest issued number and its reservation generation.

| Interruption | Result of a new read-only verification |
| --- | --- |
| Before the approval header on the witness, including torn inactive payloads | The last committed roles remain readable. A fresh review uses a fresh number. |
| Complete approval header, including lost acknowledgment | The new approved sector is readable if both media agree in full. |
| Torn or invalid witness header, or mismatch in the selected carrier slot | Verification blocks. Neither interface authorizes a restore from an older slot. |

The carrier format and its immutable original sectors are unchanged. On
the witness, legacy header tag `RBWIT001` selects logical payload sector 2.
The additional tag `RBWIT002` selects sector 3 and requires an approved
revision. Reservation preserves that selection. Each new approval toggles it.
Both tags use the same checked header fields and original sector. The
four-sector legacy file can still be read with its existing fixture.
The approval fixture uses a separately provisioned five-sector FAT12 file
at LBAs 2875–2879, including its label. Its own disk adapter identifies that
layout on each exchange. Earlier readers stop on an unsupported header tag.

The [BIOS campaign](../tools/test_mbr_approval.py) starts with a genuine
[original capture and first witness](MbrProvenance.md). It checks whole images,
disk I/O, console output, cold approvals and rejections, repeated approvals of
identical bytes, stale and substituted records, and power loss at each approval
write. The source HDD is read-only to the guest routine. This step covers
controlled, independently labelled VM media. Installer enrollment of physical
endpoints and the separate targeted restore gate remain open.
