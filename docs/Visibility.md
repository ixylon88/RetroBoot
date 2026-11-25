# Read-only primary-partition preview

F7 compares the current MBR type and active flag of each primary slot with
the selected profile's intended values. It implements the display-only
foundation of specification v0.2 sections 8 and 11. The preview never writes a sector,
stages a target VBR, starts an OS, or enables the countdown. Enter and F4 are
inert on this page; the handoff image's main-menu F4 remains the compiled T07
test only. The handoff build also offers **F9** from this view for the
separate [checked-profile test](ProfileTest.md); only that explicit action
can perform the controlled T07 transition.

## Manual check

A fresh image or newly converted VDI is required. Replacing a downloaded raw
image does not update a previously converted VDI.

| Image | Expected F7 result |
| --- | --- |
| `hdd/retroboot-hdd.img` | No preview: no configured entry; preview/check/detail `0002 / 0006 / 0000`; no partition plan |
| `hdd/retroboot-handoff.img` | Profile `Test VBR`; green matching-visibility result; codes `0000 / 0000 / 0000`; changed mask `00` |
| Corresponding images under `hdd-de/` | The same results with German labels |

On the handoff image, both current and intended columns show P1 type/active
`06 / 80`, empty P2/P3 `00 / 00`, and extended P4 `05 / 00`. Visible and active
masks both remain `01 / 01`. The management volume is logical and therefore
is not one of these four primary rows; F2 shows its hidden type `16`.

Left/Right selects a stored profile and repeats the current-target and layout
check. F7 reloads both record families and resets selection to the first
profile. Esc returns to the menu; F8 opens recovery information. F7 also
works from recovery. These checks are observations at the time of the keypress,
not continuing monitoring or persistent authorization.

German screenshots from PR #13 were manually confirmed under VirtualBox on
12 November 2026, showing both expected results above. English F7 and its
[F9 test handoff](ProfileTest.md) were confirmed there on 13 November 2026:
matching preview, unchanged masks and `RB HANDOFF PASS`. No BIOS version
or original-OS compatibility was established.

## Rules and limits

A preview requires the [F6 record/current-VBR checks](InstallationState.md):
healthy independent configuration and state pairs, matching media and
installation identities, a ready selected installation, the installed/approved
declaration, no pending/recovery installation, and a freshly validated layout
and target VBR. NTFS targets remain blocked because the volume validator does
not validate NTFS. NT groups in the tests use a FAT primary entry point.

The preview captures the exact MBR used by that successful final scan; it
performs no second MBR read. It additionally verifies the current hidden
logical management volume and the startup `RBM1` pointer. This is necessary
because the structural fingerprint intentionally normalizes hidden types and
excludes boot-code bytes.

| Profile | Intended visible data primaries | Intended active primary |
| --- | --- | --- |
| `dos9x_isolated` | Only the selected primary | Selected primary |
| `nt_chain` | The profile's explicit visible mask, including the selected primary | Selected primary only |

The explicit type pairs are `06/16`, `0E/1E`, `0B/1B`, `0C/1C` and `07/17`
(visible/hidden, hexadecimal). Unknown types fail the scan. Mask bits `01`,
`02`, `04`, `08` refer to P1 through P4; an extended or empty slot cannot be
included as a visible data primary. The changed mask marks slots whose type
or active byte would differ.

Only the type and active bytes of recognized data primaries may differ in
the proposed MBR. Boot code, disk signature, CHS bytes, start/length fields,
slot order, empty entries, extended entry and `55AA` stay byte-identical.
EBRs and shared logical volumes are not changed. Failure clears both in-memory
MBR copies and all masks; the page displays the reason without a stale plan.

| Preview code | Meaning |
| --- | --- |
| `0000` | Current type/active bytes already match the intended primary view |
| `0001` | Changes would be required; the image is unchanged |
| `0002` | Record/current-target check failed; the next two values are F6 check/detail |
| `0003` | Final management-volume hidden state or pointer changed |

F7 only diagnoses the current primary view. The confirmed HDD switch reopens
the selected installation and checks ownership, journal state and each write.
[HDD switch](TransactionJournal.md#confirmed-hdd-switch)

The fixed test identities and ready declarations belong solely to owned
synthetic fixtures.

## Verification

`make visibility-test RB_LANGUAGE=en` builds and runs this campaign; `de`
selects German. Direct invocation is `python3 tools/test_visibility.py`, with
`--language`, `--qemu` and `--bios` options. Evidence is stored under
`build/visibility/` and `build/visibility-de/` and included in the HDD artifact.
Only the four normal/handoff images are published.

The native C16 suite has 52 assertions, including all five type pairs,
byte preservation, DOS isolation, NT groups, different selected slots,
current hidden/active combinations, management binding changes, failure
clearing and use of exactly one final MBR observation.

Per language, 37 emulator campaigns exercise 370 states: 16 multi-profile
fixtures and both published images through EDD and CHS, plus one run without
instrumentation. They cover stale identities, pending states, degraded
copies, VBR changes, real I/O failures/retries, NTFS rejection and switching
between successful and failed profiles. Each observed state checks VGA text,
colors and borders, loaded code/BSS/stack guard and unchanged handoff memory.
Traces verify exact reads and zero writes; source image hashes remain unchanged.
CP437 profile names include `ÄÖÜäöüß` in both language builds.
