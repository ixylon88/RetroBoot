# Preliminary metadata capture plan

The native core can now list the live HDD sectors needed by a future metadata
backup and estimate the container size. This increment is a **model test**;
the normal rescue menu has no new key or capture action.

## Optional VirtualBox check

The **retroboot-rescue-diagnostics** artifact contains
`rescue/backup-plan-model.img` and `rescue-de/backup-plan-model.img`.
Either image can be attached as a floppy and booted without a HDD. After the
address trace, expected terminal output is:

```text
G=0157
RB BACKUP PLAN PASS
```

`0157` is the hexadecimal count of 343 assertions. The self-test uses synthetic
metadata in memory; it neither scans an attached HDD nor creates a backup.
No keyboard input is needed. A restart exits the halted test program. The
normal rescue CD/floppy still provides the existing Enter, F4 and F5 checks.

## Core contract

[`rb_backup_plan_capture`](../include/backup_plan.h) accepts a freshly discovered
first-HDD device description and a read-only physical-sector callback. The
caller supplies a writable, non-overlapping result. Sources must remain stable
for the call; private scratch makes the operation non-reentrant. No BIOS probe
occurs inside the core.

Each of two planning passes:

1. Calls `rb_backup_observe_target`, the independent acquisition part of the
   [target-comparison core](BackupTarget.md). It validates two complete live
   MBR/EBR/allocation/configuration/state acquisitions and exposes their scan
   and four physical record addresses only on success.
2. Lists the current MBR and every observed EBR.
3. Probes the first VBR of every nonempty data partition, including the
   management volume. Supported FAT16/FAT32 headers supply the complete
   reserved-sector count. FAT32 must use the layout already supported by the
   [saved boot-area checker](BackupBootAreas.md): FSInfo at offset 1, at least
   three reserved sectors, and either no backup or a three-sector backup area
   wholly inside the reserved region and starting at offset 3 or later.
4. Adds the four discovered config/state sectors and rereads the complete MBR.

Ranges must fit the device and their owning partition, must not overlap, and
must fit the existing 42-descriptor / 1 MiB container limits. One descriptor
and one sector remain reserved for a separately sourced original MBR. The
estimated size is five container sectors, all listed live sectors and that
additional original-MBR sector. The plan supplies no file offsets, payload
CRCs, backup generation or serialized container.

Current-MBR kind **0** deliberately differs from both on-disk MBR kinds.
It cannot be passed to the container encoder as an approved or original MBR.
Other kinds reuse EBR, boot-area, config A/B and state A/B identifiers.
Entries are ordered by kind; EBR indices follow the scan, boot indices follow
data-partition scan order, and each record kind has index zero.

Both planning passes must have identical read counts and ordered half-sector
CRC32 fingerprints. Every observed byte and physical LBA enters those chains,
including the VBR probes. Within a pass, all MBR reads must also match exactly.
As with the target observer, CRCs do not authenticate data and repeated reads
do not create an atomic snapshot. Later use requires fresh validation.

## Results

Success returns observed identities, layout and record generations, the copied
device description, volume/range counts, physical ranges and sector totals.
Failure clears all of those fields, retaining only the following diagnostics.

| Status | Meaning | Detail / nested / index |
| --- | --- | --- |
| `0x0000` | Preliminary plan available | Zero |
| `0x0001` | Missing device or reader | Zero; no reads |
| `0x0002` | Target observation failed | Target status / target detail / zero |
| `0x0003` | Unsupported or invalid volume header | Volume status / zero / scan index |
| `0x0004` | Unsupported FAT32 reserved-area layout | Zero / zero / scan index |
| `0x0005` | Container size or descriptor limit | Kind / zero / kind-local index |
| `0x0006` | Observed metadata changed | Inner target diagnostics if applicable |
| `0x0007` | VBR or final MBR read failed | Volume I/O code for VBR / zero / scan index |
| `0x0008` | Out-of-bounds or overlapping range | Kind / zero for bounds or one for overlap / kind-local index |

The error LBA is physical, not file-relative. Zero can denote the MBR or a
whole-pass mismatch without one identifiable failing address.

## Evidence and remaining work

The model runs **67 scenarios / 343 assertions** per language. Success cases
cover EDD, CHS, known/unknown EDD geometry, 64-bit capacity, FAT16/FAT32, hidden
types, varying backup positions, reserved areas over 64 KiB and the exact 1 MiB
container boundary. Failures cover bad parameters, allocation/record errors,
unsupported headers, excessive size, 26 selected read failures and changes to
MBR, EBR, management VBR, root metadata, correctly resealed records and system
VBR bytes/counts. Guards and failure clearing are checked. The independent
observer's optional address result and null-source use are also exercised.

The successful fixture lists eight ranges, two volumes and 39 live sectors;
the estimated container is 45 sectors / 23,040 bytes. Its complete **2,122-read**
trace is checked by an independent host oracle: two planning passes, each
containing two 529-read target acquisitions plus two first-VBR reads and a
closing MBR read. Five host tests check seed bindings, sparse-byte transfer,
size boundaries and rejection of incomplete or redirected traces.

The listed reserved areas have **not** been fully read: FSInfo contents,
backup copies and READY-VBR CRCs still require collection and the existing
saved-content validators. Profile/installation cross-links, current-MBR
approval, original-MBR provenance, backup-file creation, a writable export
destination and targeted restore remain open. No program, journal payload or
user-data backup is claimed. An intact owned management layout is required;
damaged metadata is rejected without falling back to untrusted saved addresses.
