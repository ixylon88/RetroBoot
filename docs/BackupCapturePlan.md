# Preliminary metadata capture plan

**F6 in RetroBoot Rescue** now builds a preliminary read plan from the first
HDD. It lists the metadata ranges needed by a future backup and estimates its
size. Both normal and demo rescue floppies/CDs support the same action; no
`RBBACKUP.RBB` is required. This remains a read-only planning step.

## Manual VirtualBox check

Use a successful **BIOS ABI probe** run containing this F6 increment.
The **retroboot-rescue-diagnostics** artifact provides the rescue floppy and
`retroboot-rescue-target-hdd.img`; the **retroboot-rescue-cd** artifact provides
the equivalent ISO. English files are under `rescue/` or `rescue-iso/`, German
files under `rescue-de/` or `rescue-iso-de/`.

1. Convert the **current** `retroboot-rescue-target-hdd.img` into a new VDI and
   attach it as the first IDE HDD. This version adds the synthetic FAT32
   reserved area needed by F6. A VDI from the earlier F5-only build lacks that
   header and is expected to fail the volume check. Ordinary HDD/handoff images
   are different fixtures. The [F5 setup](RescueTargetCheck.md#manual-virtualbox-check)
   also explains conversion and attachment.
2. Boot the current normal or demo rescue floppy, or attach the current ISO
   and eject any old floppy. The title must be **RetroBoot Rescue**.
3. Press **F6**. Expect a green preliminary-plan message and the values below.
4. **Right** shows the remaining three ranges on page two; **Left** returns.
   At either end, another arrow stays on that page. Paging performs no reads.
5. **Enter** or **F6** runs a fresh plan and returns to page one. **Esc** clears
   the result and returns to diagnosis. On the demo image, F4/F5 retain their
   saved-file/comparison behavior; F6 can be entered from either page.
6. Optionally detach the HDD while the VM is powered off and repeat. Expect
   BIOS/plan/detail/nested `0x0001 / 0x0000 / 0x0000 / 0x0000`, with no range
   rows, size or page count. No detached-HDD test is implied by a green run.

| F6 field | Expected value for the current target fixture |
| --- | --- |
| BIOS / plan / detail / nested | `0x0000 / 0x0000 / 0x0000 / 0x0000` |
| Error LBA / index | `0x00000000 / 0x0000` |
| Ranges / volumes / estimated bytes | `0x0008 / 0x0002 / 0x00005A00` |
| Live / estimated container sectors | `0x00000027 / 0x0000002D` |
| Pages | `0x0001 / 0x0002`, then `0x0002 / 0x0002` |

Eight ranges cover the current MBR, EBR, two FAT reserved areas, `RBCFG.A`,
`RBCFG.B`, `RBSTATE.A` and `RBSTATE.B`. The estimate is **23,040 bytes**
(22.5 KiB), including space for a separately sourced original MBR. No file
has been created, and a listed range does not mean its full contents have
already been validated. F6 is distinct from installation-state F6 in the HDD
program, whose title is **RetroBoot**.

## Optional standalone model check

The rescue artifact also contains `backup-plan-model.img` in both language
directories. Either image boots as a floppy without an HDD. Expected output:

```text
G=0157
RB BACKUP PLAN PASS
```

`0157` is the hexadecimal count of 343 assertions. The self-test uses synthetic
metadata in memory; it neither scans an attached HDD nor creates a backup.
No keyboard input is needed. A restart exits the halted test program.
The long address trace now goes only to the emulator debug log. The two result
lines remain on VGA, and the automated test still checks every trace address.

The earlier model's `G=0157` and `RB BACKUP PLAN PASS` were reported from a
VirtualBox screenshot on 14 November 2026. Its visible address trace caused
confusion but accompanied a passing result. Exact artifact revision, attached
drives and VM/BIOS versions were not separately reported. The supplied image
was discarded after retaining this text evidence. This confirms the model,
not the new live F6 path.

## BIOS adapter and result lifetime

[`rb_rescue_capture_plan`](../core/rescue_plan.c) rediscovers the first HDD on
every F6/Enter invocation and calls the existing planner with the BIOS sector
reader. After a successful plan it probes again and compares the complete
device description. A failed second probe clears the plan; a changed device
clears it with plan status `0x0006`, detail `0x0001`. There is no reuse of F5
results, saved-file addresses or earlier device information. The caller keeps
the 908-byte display result on its stack, inside the existing 8 KiB stack area.
Leaving the page clears it. Paging shows that completed observation without
new I/O; it is not continuous monitoring.

The first displayed code is the BIOS probe status (`0x0000` success, `0x0001`
no HDD, `0x0002` invalid parameters, `0x0003` unusable CHS geometry). The other
three codes are the planner status/detail/nested fields described below.
A zero planner code alone is not success when the BIOS code is nonzero.

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

## Automated evidence and remaining work

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

The live F6 campaign adds **19 boots / 194 keyboard/VGA states per language**:
EDD/CHS, normal/demo images, page boundaries, fresh repeats, F4/F5 transitions,
missing HDD, invalid discovery, failed/changed re-probes, invalid ownership or
records, unsupported boot metadata, excessive size and persistent read errors.
A host mutation between a successful plan and a new check must remove the old
ranges and size. A deliberately damaged, unread FSInfo sector still produces
a preliminary plan, explicitly testing that this step does not certify it.
Four host tests cover the published target extension, read/discovery oracles,
that unread-sector limit and rejection of stale failure-screen fields.

CD tests add four instrumented and three uninstrumented boots per language,
including the exact published normal/demo ISOs, no attached floppy, no HDD,
and CHS with the test ROM. Every live UI state checks raw VGA, program bytes,
BSS/stack guards, exact HDD reads and unchanged media. Instrumented runs also
check BIOS discovery/retries, floppy reads and attempted writes. F6 itself
never reads the saved backup file. PNGs are supplemental; raw VGA provides the
complete text/attribute evidence. Reports are under `build/rescue-plan-test*`
and `build/rescue-plan-iso-test*`, and included in the respective artifacts.
The combined rescue scope is 280 boots / 2,130 states across both languages.

The listed reserved areas have **not** been fully read: FSInfo contents,
backup copies and READY-VBR CRCs still require collection and the existing
saved-content validators. Profile/installation cross-links, current-MBR
approval, original-MBR provenance, backup-file creation, a writable export
destination and targeted restore remain open. No program, journal payload or
user-data backup is claimed. An intact owned management layout is required;
damaged metadata is rejected without falling back to untrusted saved addresses.
