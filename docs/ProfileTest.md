# F9: checked-profile test handoff

The dedicated handoff image connects the configuration, installation-state
and visibility checks to the owned T07 test sector. F9 is available only
from F7 in this test build. It performs a fresh check before executing the
known sector; an earlier green F7 result supplies no authorization.

## Manual check

The manual check uses the English build from the **retroboot-hdd-bios**
artifact. A fresh image or newly converted VirtualBox VDI is required.
Replacing a raw image does not update an existing VDI.

1. Boot `hdd/retroboot-handoff.img` in the existing empty BIOS test VM.
2. Press **F7**. Profile `Test VBR` should show matching visibility,
   `0000 / 0000 / 0000` and changed mask `00`.
3. A yellow **F9** hint appears below the preview controls. Press **F9**.
4. The independent test sector should display:

   ```text
   RB HANDOFF PASS
   Test VBR reached. Reboot to return.
   ```

Rebooting returns to RetroBoot. The normal `hdd/retroboot-hdd.img` has no
F9 hint or action; F7 still reports `0002 / 0006 / 0000`. The corresponding
`hdd-de/` images use German menu labels, with the same English test marker.
Main-menu F4 retains the earlier isolated [T07 test](Handoff.md).

German F7 screenshots from PR #13 were manually confirmed under VirtualBox
on 12 November 2026: both expected results, P1 `06 / 80`, P4 `05 / 00`,
matching `01 / 01` masks and changed mask `00`. English F7 followed by F9
from merged PR #14 was confirmed under VirtualBox on 13 November 2026.
The supplied screenshots show the matching English preview with its F9 hint
and `RB HANDOFF PASS` at the owned test VBR. Reboot behavior, a BIOS version,
physical hardware and original-OS compatibility were not established by this
report. The subsequent [F10 allocation](AdminAllocation.md) check was
confirmed with `0000 / 0000`, without additional coverage details.

## Fresh preparation

Every F9 attempt follows this sequence:

1. Remember the displayed profile's Entry ID, name, target, installation
   identity and policy, together with disk, layout and media identity.
2. Reread both configuration copies and both independent state copies.
3. Find the same unchanged profile by Entry ID. Reordering is allowed;
   a changed or missing selected entry requires another F7 review.
   Record generations are selected independently; a generation change alone
   does not replace the selected profile.
4. Repeat the record/current-target checks and visibility calculation using
   the newly loaded records. Degraded copies, pending/recovery state,
   stale identity, missing approval, changed VBR or invalid layout block it.
5. Require visibility to match already. A proposed partition change blocks
   the test; no change is applied.
6. Require the compiled test disk ID, primary slot and exact 16-byte MBR
   entry, including CHS bytes. Compare all 512 captured VBR bytes with the
   compiled T07 sector, even when the state record's CRC matches.
7. Pass that exact captured sector and entry to the existing assembly
   handoff. There is no additional MBR or VBR read after this comparison.

On the released handoff image, F9 reads 22 configuration/state metadata
sectors, then MBR LBA 0, EBR LBA 63 and target LBA 131,072. BIOS retries
remain bounded. Native tests cover selection changes and reordering; emulator
traces verify that F9 repeats the reads instead of reusing F7's observations.

## Rejection display

| Test code | Meaning |
| --- | --- |
| `0001` | The displayed selection changed, disappeared or cannot be rebound |
| `0002` | Fresh record, target, layout or management-volume check failed |
| `0003` | Current visibility requires partition changes |
| `0004` | Disk, primary slot or raw entry differs from the compiled fixture |
| `0005` | Captured sector differs from the compiled T07 VBR |

The next two values contain the F6 check/detail for `0002`; the management
binding failure has its own explanatory text. The page includes the relevant
LBA when available and clears the old preview. F7 reloads the records for a
new review, Esc returns to the menu and F8 opens recovery information.
F9, F4 and Enter are inert on this rejection page.

Failed preparation clears the handoff buffer. No failure or unrequested
keypress stages a sector at `0000:7C00` or updates the target's receipt.
The successful transition has the unchanged [T07 register contract](Handoff.md#transition-contract).

## Verification and limits

`make profile-test RB_LANGUAGE=en` builds and tests this path; `de` selects
German. Direct invocation is `python3 tools/test_profile.py`, with optional
`--language`, `--qemu` and `--bios` arguments. Evidence goes to
`build/profile/` and `build/profile-de/` and accompanies the four released
images in the HDD artifact. Fault fixtures are not published as images.

The native C16 model has 60 assertions (`J=003C`). Four host tests cover
fixture preservation, an independently resealed substituted VBR, selection
of a second profile and rejection-page cleanup. Per language, 37 emulator
campaigns exercise 336 keyboard/VGA states through EDD and CHS, including
one run without the test option ROM. They verify exact reads, target bytes
and receipt, low-memory preservation on rejection, loaded code, BSS, stack
guard, unchanged image hashes and zero disk writes.

This increment executes only the owned test VBR. It adds no original-OS
authorization, countdown, installer, journal or disk-write path. The records
and current reads are observations, not an atomic snapshot against external
media changes. Real OS compatibility, complete ownership checks and
recovery-backed writes remain separate work. Specification v0.2 is unchanged.
