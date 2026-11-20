# Original and approved MBRs

An original MBR answers “what was on this disk before RetroBoot first wrote
to it?” An approved MBR answers “which exact sector did the operator last
accept for this disk?” A current observation can differ from both.
The native model records those decisions against synthetic disk and recovery
readers. Its public operations are defined in [mbr_provenance.h](../include/mbr_provenance.h).

## Enrollment and review

| Operation | Required evidence | Result |
| --- | --- | --- |
| First installation | A trusted pre-write installer session, an identified target and a separate identified recovery medium | Read the current 512 bytes, read back the external original at revision 1, then reread the target. All three copies must agree before the original becomes available. |
| Review current | Fresh sector 0 from the enrolled target | Retain the exact bytes for review. Issue a ticket bound to both identities and a new revision, even if the bytes equal an earlier observation. |
| Reject | Explicit decision for the pending ticket | Discard the candidate. The original and the last approved revision remain available. |
| Approve | Explicit decision for the pending ticket | Compare the live target, staged external approved record and live target again with the reviewed bytes. Publish the approved revision in memory only after all three checks succeed. |
| Read a role | Original revision 1, or the latest accepted revision for approved | Re-read the external record and compare its complete sector with the enrolled version. A failure clears all 512 output bytes. |

The installer must establish first-install custody **before its first target
write**, including partitioning or preparing the management volume. A known
installed `RBM1` marker conflicts with first installation. An absent marker,
blank sector, valid signature or matching CRC cannot establish the sequence
of events. An existing installation with no independently retained original
must report the original as unavailable. A later approval cannot fill that gap.

Each enrollment binds a nonzero 16-byte target identifier, a 64-bit capacity
in 512-byte sectors and a distinct nonzero 16-byte recovery-medium identifier.
The acquisition layer must identify the physical target on each live read and
the carrier independently of the file on each external read. It must keep the
endpoints stable under exclusive access. The record also carries both binding
identities, capacity, role and revision. A BIOS drive number, MBR signature or
ID read from the candidate file alone cannot identify the physical carrier.
A byte-for-byte clone presented as the same trusted endpoint is outside what
these callbacks can distinguish.

Each reader must return exactly 512 sector bytes. Short reads, substituted
endpoints, mismatched tags and changed contents invalidate the operation.
A failed fresh observation on the enrolled target clears the old candidate.
A failed explicit approval consumes that review and preserves the last
accepted record. Foreign or stale tickets cannot cancel a newer candidate.
The 32-bit sequence stops at its maximum and never wraps. The caller owns
the trusted, zero-initialized session state and serializes access to it.

## Capturing the original sector on a separate medium

The [first-install capture routine](../include/mbr_original.h) reads sector
zero from the bound target and writes the original to an identified recovery
carrier. The caller holds exclusive custody of both endpoints and supplies
the first-install decision before any installation write. The routine checks
the complete target identifier and capacity on each acquisition. A managed
`RBM1` sector or unknown origin stops capture.

The first two logical sectors on the carrier use the existing
[restart format](MbrRestart.md#records-and-selection). The payload is staged
first. After a byte-for-byte readback and a fresh read of the target, the
routine publishes the `RBORG001` header for revision 1. It rereads both
carrier sectors and the target before reporting success. Approval and
publication slots remain available for later stages.

| Carrier state on entry | Action |
| --- | --- |
| Original header, payload and publication slots are blank | Capture the live original. An all-zero original is valid under established pre-write custody. |
| Header is blank and the complete staged payload matches the live target | Recheck the empty publication slots and resume at the header. |
| Sealed original matches the binding and all 512 live bytes | Verify both endpoints again using reads only. |
| Conflicting or torn evidence, changed target, or later publication slots alongside a missing header | Stop. Retain the available evidence. |

An interruption can leave the complete original on the carrier even when the
caller received an error. A new first-install session with continuing custody
verifies the actual bytes. Loss or replay of both an endpoint label and its
history requires independently retained evidence. The [first witness](#publishing-and-checking-the-first-witness)
records this capture separately. A later [explicitly reviewed sector](MbrApproval.md) can now be
published on controlled media. Targeted restore requires the additional backup gates in #45 and
#46.

### BIOS evidence

The standalone fixture uses three project-owned images. `mbr-original.img`
boots the capture program. `mbr-original-hdd.img` supplies a 10,080-sector
test HDD. `mbr-original-data.img` is the recovery carrier. Under exclusive
VM control, the fixture checks separately provisioned endpoint labels around
every data access. The target label occupies the final HDD sector and the
carrier label occupies LBA 0. The BIOS supplies the target capacity. These
fixture labels support controlled VM tests. The [enrolled ATA capture](MbrTarget.md)
uses the operating device’s model, serial and capacity on a legacy IDE route.
General installer enrollment and recovery endpoint identification remain open.

At the prompt, Enter confirms first-install custody and Esc cancels. The
fixture writer addresses only LBAs 1 and 2 of the labelled recovery floppy.
The [automated campaign](../tools/test_mbr_original.py) checks the full media
after each boot, every physical write, every target read, the VGA transcript
and the guest memory guards. Independent QEMU processes test cold retries,
write protection, missing or swapped endpoints, live changes before and after
sealing, and different sectors with the same CRC32. Power cuts interrupt
each of the two writes before completion, after completion and after a
128-byte prefix. A lost acknowledgment and a silently dropped write are
also followed by a cold retry on the exact resulting images.

## Publishing and checking the first witness

The external recovery system can verify the saved first-install MBR with the
source HDD disconnected. It starts from a separately held boot floppy containing
a copy of all 512 original bytes and the binding to the target and recovery
carrier. Entering verification mode reads this witness and reopens the carrier
using the [cold-start reader](MbrRestart.md). A complete match verifies original
revision 1. Targeted restore requires a separate operation.

### VirtualBox check

The `retroboot-rescue-diagnostics` artifact contains the pair produced by the
running guest under `mbr-witness-test-de/` and `mbr-witness-test/`. Each
directory contains both files from a single run.

1. A BIOS VirtualBox VM with the HDD disconnected boots `mbr-witness.img`
   from floppy drive A. At the menu, **V** selects verification.
2. At `INSERT RECOVERY FLOPPY AND PRESS ENTER`, replace the disk in A with
   `mbr-original-data.img` and press Enter. Both files may be read-only.

Expected final lines:

```text
ORIGINAL REV 1 VERIFIED
RB WITNESS PASS
```

### Enrollment and interruption

The [publisher](../include/mbr_first_witness.h) runs under continuing exclusive
first-install custody, after the [original capture](#capturing-the-original-sector-on-a-separate-medium).
The separate witness starts with three blank record sectors in its allocated
`RBWITNES.BIN` file. The installer supplies the target and carrier binding and
a distinct, independently known witness identity.

1. Read the current MBR from the identified HDD. Check the unpublished witness.
   A complete matching payload can resume a staged write. An existing header
   closes enrollment.
2. Compare the immutable carrier header and every original byte with the live
   sample. Require an empty approval payload and an empty later slot. After
   another live sample, stage the generation-1 commit header, or verify an
   identical staged header. Reopen the carrier twice using the normal reader.
3. Reinsert the witness and compare its pending state with its state at the
   first exchange. Stage and read back the complete original. Recheck the
   live target and the pending witness before publishing its header last.
   Reload the published witness twice and compare both sectors and all counters.

| Result after an interruption | Subsequent action |
| --- | --- |
| Complete carrier commit or matching witness payload, witness header blank | Verification blocks. Under continuing first-install custody, enrollment resumes from the verified bytes. |
| Inconsistent or torn record | Enrollment stops and retains the evidence. |
| Complete witness header, acknowledgment or final read lost | A cold, read-only verification of both media can confirm the original without the HDD. |

Only carrier LBA 3 and witness LBAs 2878 and 2877 can be written by this
fixture. It publishes generation 1, issued revision 1 and no later approval.
The [BIOS campaign](../tools/test_mbr_first_witness.py) first runs the original
capture from PR #66, then boots the publisher, then starts a fresh VM without
the HDD. It checks the physical write order, complete image bytes, cold
retries and rejections, including different original sectors with equal CRC32.
The retained boot medium must remain independently identifiable and current.
Detecting a coordinated rollback of all evidence requires separate custody.

The [later approval workflow](MbrApproval.md) preserves this original while
recording a freshly reviewed MBR on both media.

## Evidence across a restart

The first-install and approval model keeps its history in RAM. The separate
[cold-start reader](MbrRestart.md) now reopens independently provisioned
records after a power cycle. Issuing and retaining evidence on real media
requires the following steps.

1. Establish the disk and separate recovery carrier under operator control.
   Preserve the first-install record, its complete sector, both identities,
   capacity and revision outside the target disk. Keep this original write-once.
2. Reserve each review revision durably before issuing it. Present the exact
   reviewed bytes or their differences, target, carrier and revision to the
   operator. Keep the recorded decision associated with that observation.
3. Stage approved records separately from the original and previous approval.
   Read the staged record back from the independent medium before publishing
   it. Publish a recoverable commit identifying the previous and new approved
   revisions. Keep the last committed record available through interruption.
4. On restart, discard pending tickets and verify the latest committed revision
   against an independently retained record of the latest issued and committed
   revisions. An older but internally consistent carrier can omit a later
   decision. A missing or conflicting history restricts recovery to diagnosis.
   An interrupted, rejected or completed ticket number must never be reissued.

`RBBAK` version 1 carries two complete MBR payloads. Its role labels and CRCs
check the supplied file. They cannot establish capture time, physical custody
or the operator's decision. The normal [F7 dry run](BackupLiveSources.md#f7-in-normal-rescue)
continues to use these file bytes as an explicit comparison reference.

## Evidence for targeted recovery

Before proposing a write, independent rescue must identify the current target
again, verify the externally committed roles and complete backup, and check
current geometry, partition layout, affected ranges and the proposed bytes.
The operator must see the target, affected range, current and proposed values
and backup status. Restoration needs its own explicit confirmation. Approval
of a historical MBR only establishes which bytes belong to that revision.

| Finding | Evidence and scope for a future repair |
| --- | --- |
| Only RetroBoot MBR code was replaced | Verify the release code, loader parameters and current management volume. Preserve the current disk signature and reserved bytes at 440–445 and the validated partition table at 446–509. |
| Partition table or visibility flags differ | Compare current and approved layouts and full EBR chains. Identify the exact affected entries, geometry and expected profile before offering a targeted change. |
| First-install history is missing, endpoints conflict, or foreign code is ambiguous | Show the observations and the unavailable role. Keep the target read-only. |

The remaining recovery packages cover verification of a completed stream,
external persistence and readback, and an independently demonstrated targeted
restore. The full requirements are in sections 9 and 13 of the
[frozen specification](spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md).

## Booting the standalone model

The BIOS ABI and Rescue workflow includes `mbr-provenance-model.img` under
both language directories in `retroboot-rescue-diagnostics`. The two images
are byte-identical. A BIOS test VM can boot the image from floppy A with the
HDD and CD disconnected. The model runs automatically and halts with this
transcript on VGA and the debug port.

```text
ORIGINAL SEALED
CURRENT REJECTED
REVISION 3 APPROVED
STALE REVIEW BLOCKED
READBACK FAILURES BLOCKED
N=00DB
RB MBR PROVENANCE PASS
```

The hexadecimal count `00DB` records 219 native assertions. These cover
enrollment, rejection, approval, stale and foreign tickets, exhausted
revisions, incomplete reads and swapped endpoints. One fixture has different
bytes and identical CRC32 values after resealing. An exclamation mark and
source line identify a failing assertion. The emulator runner verifies the
complete report, memory guards, zero HDD reads and zero guest writes.

On 18 November 2026, a manual VirtualBox run displayed all seven lines above.
The transcript is recorded in [PR #62](https://github.com/ixylon88/RetroBoot/pull/62).
