# Preliminary metadata capture plan

**F6 in RetroBoot Rescue** builds a read plan from the first HDD, estimates the
backup size and checks every sector in the supported FAT reserved boot areas.
FAT32 FSInfo, primary/backup boot copies and selected READY first-VBR checksums
are checked before a green result. Normal and demo rescue floppies/CDs share
this action; no `RBBACKUP.RBB` is required. No backup file or disk write occurs.

## Manual VirtualBox check

The downloads belong to **[BIOS ABI and Rescue](https://github.com/ixylon88/RetroBoot/actions/workflows/abi-probe.yml)**
(formerly **BIOS ABI probe**). The successful run for the intended revision
contains both rescue artifacts. **HDD BIOS boot** instead publishes
`retroboot-hdd-bios`, which contains the separate HDD-menu test program.

| Artifact | German path | Purpose |
| --- | --- | --- |
| `retroboot-rescue-diagnostics` | `rescue-de/retroboot-rescue-demo.img` | Boot floppy with synthetic saved backup |
| `retroboot-rescue-diagnostics` | `rescue-de/retroboot-rescue-target-hdd.img` | Good synthetic target HDD |
| `retroboot-rescue-diagnostics` | `rescue-de/retroboot-rescue-bad-fsinfo-hdd.img` | Same target with deliberately broken FSInfo |
| `retroboot-rescue-cd` | `rescue-iso-de/retroboot-rescue-demo.iso` | Equivalent boot CD |

English paths use `rescue/` and `rescue-iso/`. Both languages contain identical
HDD fixtures. The normal rescue image also supports F6; the demo additionally
supports the existing successful F4/F5 checks.

1. With the VM powered off, a **new VDI converted from the current good target
   IMG** is attached as the first IDE HDD. Earlier F5-only targets lack the
   FAT32 reserved area; the ordinary HDD/handoff images are different fixtures.
   Conversion and attachment are described in the [F5 setup](RescueTargetCheck.md#manual-virtualbox-check).
2. The current rescue floppy or ISO boots with legacy BIOS. For a CD check,
   the old floppy is ejected and Optical precedes Hard Disk in the boot order.
   The title must be **RetroBoot Rescue**.
3. **F6** must show a green message confirming the plan and FAT boot areas,
   with the values below. **Right** shows the remaining three ranges;
   **Left** returns. Further arrows at either end stay on the current page.
4. **Enter/F6** performs a fresh check and returns to page one. **Esc** clears
   the result and returns to diagnosis. Paging itself performs no reads.
5. After shutdown, the good VDI is replaced by a separately converted
   **`retroboot-rescue-bad-fsinfo-hdd.img`**. F6 must now show a yellow rejection:
   `0x0000 / 0x0009 / 0x0007 / 0x0001`, error LBA `0x00020001`, index `0x0000`.
   Ranges, size and page count must be blank. This is an intentional failure.
6. Optionally, with the HDD detached before startup, F6 must report
   `0x0001 / 0x0000 / 0x0000 / 0x0000`, also without range/size fields.

| F6 field | Expected good-target value |
| --- | --- |
| BIOS / plan / detail / nested | `0x0000 / 0x0000 / 0x0000 / 0x0000` |
| Error LBA / index | `0x00000000 / 0x0000` |
| Ranges / volumes / estimated bytes | `0x0008 / 0x0002 / 0x00005A00` |
| Live / estimated container sectors | `0x00000027 / 0x0000002D` |
| Pages | `0x0001 / 0x0002`, then `0x0002 / 0x0002` |

The eight ranges cover the current MBR, EBR, two FAT reserved areas, `RBCFG.A`,
`RBCFG.B`, `RBSTATE.A` and `RBSTATE.B`. The estimate is **23,040 bytes**
(22.5 KiB), including space for a separately sourced original MBR. The extra
boot-area checks do not change these ranges or size. Rescue F6 is distinct
from installation-state F6 in the HDD program, whose title is **RetroBoot**.

## Manual evidence

On 15 November 2026, the expanded full boot-area checks were also reported
successful under VirtualBox. The German good-target screenshot shows the green
confirmation, four zero codes, zero error LBA/index, eight ranges, two volumes,
39 live / 45 estimated sectors, 23,040 bytes and page one of two. Its five
visible ranges match the fixture. The bad-FSInfo screenshot shows the yellow
rejection, codes `0x0000 / 0x0009 / 0x0007 / 0x0001`, LBA `0x00020001`, zero
index, and blank ranges/counts/size/pages. The distinct result colors were
reported as helpful. Exact workflow/image revision, boot medium, VM/BIOS
versions, page two, repeats/Esc and no-HDD behavior were not separately
established for this report. The supplied images were discarded after retaining
this text evidence.

On 15 November 2026, the preceding F6 range-preview increment was reported
successful under VirtualBox. Two German screenshots show both pages, four zero
diagnostic codes, zero error LBA/index, eight ranges, two volumes, 39 live /
45 estimated sectors and 23,040 bytes. All eight displayed LBAs and lengths
match the synthetic fixture. Exact workflow/image revision, boot medium,
VM/BIOS versions, Enter/F6 repeats, Esc and no-HDD behavior were not separately
established. The supplied images were discarded after retaining this text.
That earlier report confirms the preceding preview only.

The earlier standalone model's `G=0157` and `RB BACKUP PLAN PASS` were reported
from VirtualBox on 14 November 2026. The long visible address trace accompanied
a passing result. Exact revision, attached drives and VM/BIOS versions were not
separately reported; the supplied image was discarded after retaining evidence.

## Optional standalone model check

`backup-plan-model.img` in either rescue language directory boots as a floppy
without an HDD. The expanded in-memory model now displays:

```text
G=023E
RB BACKUP PLAN PASS
```

`023E` counts **574 assertions** in hexadecimal. No attached HDD is scanned and
no file is created. No keyboard input is required; a restart exits the halted
program. Its exact address trace remains in the emulator debug log, not VGA.

## BIOS adapter and result lifetime

[`rb_rescue_capture_plan`](../core/rescue_plan.c) rediscovers the first HDD on
every F6/Enter invocation and supplies a read-only BIOS sector callback. After
success it probes again and compares the complete device description. A failed
second probe clears the plan; a changed device clears it with plan status
`0x0006`, detail `0x0001`. No F5 result or saved-file address is reused.

The 908-byte display result remains on the existing guarded 8 KiB stack. Leaving
the page clears it. Paging shows a completed observation without new I/O, not
continuous monitoring. The first displayed code is the BIOS probe status:
`0x0000` success, `0x0001` no HDD, `0x0002` invalid parameters, `0x0003` unusable
CHS geometry. A zero planner code is not success if the BIOS code is nonzero.

## Core contract

[`rb_backup_plan_capture`](../include/backup_plan.h) requires a fresh device
description, a physical-sector reader and a writable result that does not
overlap inputs. Stable sources and non-reentrant use remain preconditions.
No BIOS discovery occurs inside the core. Each of two planning passes:

1. Performs the existing two complete MBR/EBR/allocation/config/state
   acquisitions through `rb_backup_observe_target`. Success exposes the scan,
   four audited record addresses and READY first-VBR claims from the selected
   validated installation-state copy. Older copies are not selected claims.
2. Lists the current MBR and EBRs; probes every nonempty data partition,
   including management, to obtain its complete reserved-sector count.
   FAT32 requires FSInfo at offset 1, at least three reserved sectors and
   either no backup or a three-sector backup starting at offset 3 or later,
   wholly inside the reserved area.
3. Adds all four config/state sectors and bounds the **entire** plan against
   device, owning partitions, overlap, descriptor count and container size.
   Oversized plans fail before any full-area read.
4. Reprobes each VBR and checks its reserved count against the bounded plan.
   Every remaining reserved sector is then streamed with bounded buffers.
   FAT16 opaque reserved bytes are included in the observation. FAT32 checks
   both FSInfo structures, the primary continuation signature, exact first
   VBR/backup equality and exact continuation/backup equality. FSInfo hints may
   differ between copies but must independently satisfy the supported bounds.
   The shared [FSInfo helper](../core/fat_boot.c) preserves F4's saved-file rules.
5. Compares each selected READY first-VBR CRC with the observed first sector,
   then rereads the complete MBR. Pending installations carry no READY claim.

One descriptor and one sector remain reserved for a separately sourced original
MBR within the existing 42-descriptor / 1 MiB container limits. Estimated size
is five container sectors plus all listed live sectors plus that original-MBR
sector. No file offsets, payload CRC list, generation or serialized container
are produced. Current-MBR kind **0** deliberately differs from both on-disk
MBR roles, and cannot be encoded as an original or approved MBR.

Both passes must have identical read counts and ordered half-sector CRC32
fingerprints. Every observed byte and physical LBA enters those chains,
including all reserved-sector padding. Every MBR read within a pass must also
match exactly. These checks detect observed changes; CRCs do not authenticate
data and repeated reads do not produce an atomic snapshot or a later write
lease. Later use requires fresh validation.

## Results

Success returns observed identities, layout/generations, device description,
counts, physical ranges and sector totals. Failure clears them all, retaining
only status/detail/nested/index/error LBA.

| Status | Meaning | Detail / nested / index |
| --- | --- | --- |
| `0x0000` | Plan and supported boot areas consistent | Zero |
| `0x0001` | Missing device or reader | Zero; no reads |
| `0x0002` | Target observation failed | Target status / target detail / zero |
| `0x0003` | Unsupported or invalid volume header | Volume status / zero / scan index |
| `0x0004` | Unsupported FAT32 layout | Zero / zero / scan index |
| `0x0005` | Container size or descriptor limit | Kind / zero / kind-local index |
| `0x0006` | Observed metadata changed | Inner target diagnostics if applicable |
| `0x0007` | Boot-area or final MBR read failed | Volume I/O code for boot area / zero / scan index |
| `0x0008` | Invalid or overlapping range | Kind / zero for bounds or one for overlap / kind-local index |
| `0x0009` | Boot-area content rejected | Saved boot-check category / subcode / scan index |

For status `0x0009`, detail `0x0007` is FSInfo: nested 1 signatures, 2 reserved
bytes, 3 free count, 4 next hint. Detail `0x0008` is copy consistency: nested 1
backup VBR, 2 backup continuation, 3 primary continuation signature. Detail
`0x0009` is a READY CRC mismatch; nested identifies the selected installation
entry. The error LBA is the physical failing sector. Zero can identify the
MBR or a whole-pass mismatch without one failing address.

## Automated evidence and remaining work

The native model has **113 scenarios / 574 assertions** per language. It covers
FAT16/FAT32, EDD/CHS, geometry/capacity limits, reserved areas over 64 KiB, the
exact 1 MiB boundary, malformed FSInfo/copies, selected and older READY claims,
pending installations, 42 selected read failures and structurally valid changes
between passes. Guards and complete failure clearing are checked. The successful
fixture's independent **2,188-read** oracle contains two 1,094-read passes:
two 529-read metadata acquisitions, two sizing VBRs, 32 system reserved sectors,
one management VBR and one closing MBR. The exact-limit case streams 6,194 reads;
a one-sector-too-large plan stops after 1,060 sizing/metadata reads.

The live F6 campaign has **26 floppy boots / 264 UI states per language**.
It exercises paging, repeats, F4/F5 transitions, missing/damaged HDDs, EDD/CHS,
BIOS changes, reserved-area I/O failures and the new boot-content failures.
A host FSInfo mutation after success must discard prior ranges on the next
check. CD checks add five instrumented and four bare boots / 98 states per
language, including the actual published good and bad-FSInfo HDDs. Both
languages use complete VGA, code/BSS/stack guards, exact reads, unchanged media
and zero-write checks. F6 itself never reads the saved backup file.

The complete rescue scope is **298 boots / 2,310 UI states**, including the
unchanged F4/F5 campaigns and native saved-file validators. Local and published
run results are recorded in the PR; reports remain under `build/rescue-*test*`.
Host tests retain independent fixture, read-boundary and stale-field checks.

Full FAT boot-area validation does not resolve profile/state cross-links,
original-MBR provenance, current-MBR approval, backup-file serialization,
a writable export destination or targeted restore. No program, journal payload
or user-data backup is claimed. An intact owned management layout remains
required; damaged metadata is rejected without using untrusted saved addresses.
