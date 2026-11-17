# Project state and resumption

Updated: 17 November 2026.

## Pending provisional container-output increment

The [stream assembler](BackupStreaming.md) joins explicit metadata and payload
sources into a sequential container. A complete preflight verifies framing and
payload CRCs before any sink call. The second pass emits provisional bytes,
checks CRCs again and compares ordered body/tail fingerprints. Any failure
clears the result's sector-count claim; the caller must discard all output,
including bytes delivered before a final-sector failure. Original/approved
MBR sources remain explicit roles, without inferred provenance or approval.

Only `backup-stream-model.img` links the new code. Its 199 scenarios / 995
assertions show `J=03E3` and `RB BACKUP STREAM PASS`. Independent Python wire
oracles check full output bytes, source/sink coordinates and order, every
ordinary-fixture read and output failure boundary, resealed-record changes,
64 KiB crossings, the 1 MiB limit, clearing and guards. The model has 17,040
bytes of static headroom and uses the existing guarded 8 KiB stack.

Local host validation passed 207 tests and the reference layout report.
Both rescue builds reproduced exactly; all 152 prior artifacts per language
remain byte-identical, including normal/demo images and previous native models.
Normal memory budgets are unchanged. Full boot-campaign and hosted results
are recorded in the PR. The separate HDD campaign is left to normal hosted
CI because its code is unchanged. No skip marker or CI trigger change is used.

Live-source binding, MBR provenance/approval, saved semantic checks, destination
storage and independent readback remain open. This is a standalone protocol
model; normal rescue still has no backup-file output command.

## Live F6 CRC32 baseline (PR #37)

PR #37 is merged at `712b69bfb2f8d3f7b15abf459b2a21bb398b2fe7`.

F6 now calls the validated payload observer through fresh BIOS discovery and
displays one whole-range CRC32 per row on both pages. Enter/F6 rereads the
source; paging preserves the completed observation without new I/O. Probe,
capture and changed-device failures clear the complete result, including all
CRCs. No saved-file access, backup creation, MBR approval or write is added.
The [F6 guide](BackupCapturePlan.md) contains the exact eight expected CRCs and
explains the equal residues of records with embedded trailing CRC fields.

Local validation passed 204 host tests, the reference layout report, repeated
EN/DE rescue and ISO builds, and all 14 rescue campaigns: 328 boots / 2,560
UI states. F6 uses exactly 2,266 HDD reads on the intact fixture. New tests
cover a fresh CRC after a stable reserved-byte change and a transient change
only during the second payload pass. VGA fields/colors, source hashes,
read traces, code/BSS/stack guards and zero guest writes remain checked.
The existing BIOS test ROM modes 0–18 are byte-identical; mode 19 adds the
transient read-buffer mutation. The standalone planner and payload markers
remain `G=02C6` and `I=03F6` respectively.

Normal rescue binaries are 34,644 bytes EN / 34,912 bytes DE. BSS remains
20,820 bytes; static headroom is 1,880 / 1,612 bytes, with the unchanged
1,536-byte minimum. The 1,072-byte display result is on the existing guarded
8 KiB stack. Further growth needs to preserve these limits. HDD code is
unchanged; its separate boot campaign was not rerun locally.

All three hosted workflows (four jobs) passed. Downloaded artifacts matched
112 local binaries/media and all 14 case/read/VGA reports. On 17 November
2026, the manual F6 procedure was confirmed; German VirtualBox screenshots
show both intact CRC pages and the expected bad-FSInfo rejection with cleared
fields. The [manual evidence](BackupCapturePlan.md#manual-evidence) records the
exact values and the limits of the screenshots and reported procedure.

## Payload-observation baseline (PR #36)

PR #36 is merged at `8fa54d4d3d1abfe697c15d95dcccaaf46f60682a`.

The [payload observer](BackupPayloads.md) builds a fresh validated plan in each
of two passes, streams every live extent and returns its ordinary CRC32.
Every added read also enters the ordered body/tail fingerprints. Failure
clears all plan claims and CRCs. Current-MBR kind 0 remains unapproved;
payload retention, serialization, original-MBR provenance and restore remain
open. F4/F5/F6 actions and their read sequences are unchanged.

Local validation on the PR #35 baseline passed 203 host tests, the reference
layout report, repeated EN/DE rescue and ISO builds, and all 14 rescue
campaigns: 320 boots / 2,480 UI states. Each new native model runs 202 scenarios
and 1,014 assertions (`I=03F6`, `RB BACKUP PAYLOAD PASS`), including per-sector
payload I/O failures in both passes and transient resealed record changes.
The existing planner still reports `G=02C6`. The test environment is the QEMU
10.0.13/SeaBIOS, 486/16 MiB environment recorded below. On 17 November 2026,
the supplied `I=03F6 / RB BACKUP PAYLOAD PASS` procedure was confirmed.
Exact downloaded revision, attached drives and VM/BIOS versions were not
separately reported; the [payload guide](BackupPayloads.md) records the scope.

Normal rescue payload sizes are 34,582 bytes EN / 34,846 bytes DE; BSS remains
20,820 bytes. Static headroom is 1,942 / 1,678 bytes, above the unchanged
1,536-byte minimum. The payload model has 3,280 bytes of static headroom.
Further UI/core growth must retain these budgets. HDD code is unchanged and
the separate HDD boot campaign was not rerun for this increment.

Hosted CI was intentionally skipped for PR #36 to conserve the
available Actions allowance. A local test bundle contains the verified
`backup-payload-model.img`, source revision and SHA-256. The normal workflow
also includes this image in both language folders when run explicitly.
Subsequent code PRs use the normal full PR workflows without a skip marker;
the PR/manual trigger policy from PR #35 remains in place. Local verification
and hosted check results are recorded separately.

## Saved baseline

PR #35 (PR/manual CI triggers) is merged at
`e75bc0329186c874b7be471c2f840e75a19ab3f7`. The duplicate post-merge runs are
disabled; PR and manual runs retain their complete jobs. That trigger-only
revision intentionally skipped hosted CI, with local YAML/diff validation.

PR #34 (body/tail fingerprints) is merged at
`c687bd432a1fd0a2f3335259777d307594ed3cd3`. On 16 November 2026, the manual
follow-up explicitly confirmed `G=02C6` and `RB BACKUP PLAN PASS`. Exact
downloaded revision, language folder, attached drives and VM/BIOS versions
were not separately reported. The [plan guide](BackupCapturePlan.md#manual-evidence)
records this evidence.

PR #33 (native metadata-sector encoding) is merged into `historical` at
`68cb5ac28e57a7a35f02245f65374315ef5af3ea`. All four checks passed. Published
rescue files, four ISOs, 14 case/read/VGA reports and native model logs matched
local results (314 boots / 2,444 states). The encoder result was confirmed on
15 November 2026: `H=04F2` and `RB BACKUP ENCODE PASS`. Exact artifact revision,
language folder, attached drives and VM/BIOS versions were not separately
reported. This confirms the standalone encoder, not complete source capture.

PR #32 (live installation-reference consistency) is merged into `historical`
at `29b3f4b723161e48d326b4c9352107147ead2da8`. All four checks passed. Published
rescue files, four ISOs and all 14 case/read/VGA reports matched local results
(312 boots / 2,444 states). German VirtualBox reports on 15 November 2026
confirmed intact F5 and both F6 pages, plus the new bad-reference rejection:
F5 `0x0004 / 0x000B / 0x0000`, F6 `0x0000 / 0x0002 / 0x000B / 0x0000`,
error LBA `0x00020000` and cleared success fields. The [manual evidence](BackupCapturePlan.md#manual-evidence)
retains exact observations and coverage limits. Exact artifact revision, boot
medium, VM/BIOS versions, F4 and complete Enter/Esc sequence were not separately
established. The five supplied screenshots were discarded after recording the
text evidence.

PR #31 (saved-check buffer reuse) is merged into `historical` at
`a5930936561398850dac44da656ad4c8914ec190`. All four checks passed; published
rescue files, four ISOs and 14 case/read/VGA reports matched local results
(298 boots / 2,310 states). English VirtualBox reports on 15 November 2026
confirmed F4/F5/F6 success with the intact target and the expected F6
bad-FSInfo rejection with the deliberately damaged target. The intact F6
shows four zero codes, eight ranges and 23,040 bytes. The damaged result has
`0x0000 / 0x0009 / 0x0007 / 0x0001`, LBA `0x00020001`, no retained ranges.
The [manual evidence](BackupCapturePlan.md#manual-evidence) records exact
observations and coverage limits; no exact revision, boot medium, VM/BIOS
versions, page two or complete key sequence is inferred. Supplied screenshots
were discarded after retaining text evidence. Future procedures distinguish
`retroboot-rescue-target-hdd.img` (intact) from each deliberately damaged fixture
by its complete filename.

PR #30 (complete live FAT boot-area validation) is merged into `historical` at
`09ebfccf4825eccfc134c7014e14e1659d882d7c`. All four PR checks passed. Published
rescue files, four ISOs and all 14 case/read/VGA reports matched local results
(298 boots / 2,310 states). On 15 November 2026, German VirtualBox results
confirmed both the green good-target F6 page and the yellow bad-FSInfo rejection.
The good page has four zero codes, eight ranges and 23,040 estimated bytes;
the bad page has `0x0000 / 0x0009 / 0x0007 / 0x0001`, LBA `0x00020001`, and
blank ranges/size. The [F6 evidence](BackupCapturePlan.md#manual-evidence)
records the reported scope. Exact revision, boot medium, VM/BIOS versions,
page two, repeats/Esc and no-HDD behavior were not separately established for
this report. The supplied images were discarded after retaining text evidence.

PR #29 (live rescue F6 preview) is merged into `historical` at
`4b4ee977a7ea8d6fc663df754a64ff7fbdad60e3`. All four PR checks passed;
published rescue files, four ISOs and all 14 case/read/VGA reports matched
local results (280 boots / 2,130 states). On 15 November 2026, two German
VirtualBox screenshots confirmed both F6 pages, four zero codes, eight ranges,
two volumes and 23,040 estimated bytes. All displayed LBAs/lengths match the
fixture. Exact revision, boot medium, VM/BIOS versions, repeats/Esc and no-HDD
behavior were not separately established. The [F6 guide](BackupCapturePlan.md#manual-evidence)
retains the text evidence; the supplied images were discarded. This confirms
the preceding preview, not the new full boot-area checks.

PR #28 (preliminary capture-plan core) is merged into `historical` at
`d5e01296fad319ac43210ee3a5eb77a895497f3a`. All four PR checks passed;
its rescue binaries/fixtures, four ISOs and case/read/VGA results matched the
local build. The model's `G=0157` and `RB BACKUP PLAN PASS` were subsequently
reported from VirtualBox on 14 November 2026. The long visible address trace
caused confusion. Exact artifact revision, attached drives and VM/BIOS version
were not separately reported. The [plan guide](BackupCapturePlan.md) retains
that text evidence; the supplied screenshot was discarded.

PR #27 (short BIOS CD-mode explanations) is merged into `historical` at
`e353caf22a54c0534f0ba3cd866c3fd1496b13a8`. PR #26 (rescue ISO) was merged at
`6968062d68cead1678fcf75d24f43165901445e0`; all four PR #26 checks passed.
Its published ISOs matched local builds, and all four CD reports matched the
local case/read/VGA results. English F4/F5 success was subsequently reported
from a VirtualBox CD boot. The [CD evidence](RescueCD.md#manual-evidence)
records the values and limits: exact revision, old-floppy removal, VM/BIOS
version, repeats, no-HDD and German CD use were not separately established.
The supplied screenshots were discarded after retaining text evidence.

PR #25 (numeric values and byte sequences) is merged into `historical` at
`c95289b9c4fabc1154b78df6c2d1117f0c1d6865`. All four PR checks passed.
The German initial rescue page and successful F5 result were subsequently
confirmed under VirtualBox on 14 November 2026, including the `0x` notation,
spaced media-ID bytes and German text. The exact values match the
[F5 table](RescueTargetCheck.md#manual-virtualbox-check). Workflow/image paths,
BIOS version, repeat keys and HDD-menu formatting were not separately reported.
The supplied screenshots were discarded after retaining this text evidence.

PR #23 (target-comparison core and beginner guide) is merged into `historical`
at `3e3063903c95b2327efaab583e53f75a2686d258`. All four PR checks passed,
including HDD regression. That baseline has 170 host tests and 140 rescue
boots / 812 UI states. Its native target model has 178 assertions per language
and a 542-read oracle; it introduced no normal-UI action.

PR #22 remains the saved-file baseline. The German demo's F4 result was
manually confirmed under VirtualBox on 14 November 2026: codes and error
locations zero, volumes `0002 / 0001 / 0001`, reserved sectors `0021`, READY
matches `0001`. Enter-repeat and Esc-return were not separately reported.
No English F4, physical-hardware or BIOS-version coverage is implied.

PR #21 remains the saved FAT boot-area baseline (65 scenarios / 325 assertions),
PR #20 the saved-record baseline (74 / 296), and PR #19 the container baseline
(72 / 216), per language. No disk writes were introduced.

PR #18 remains the independent read-only rescue baseline; its four checks passed.
The German rescue floppy was manually confirmed under VirtualBox with the
64 MiB compact fixture, 128 MiB handoff fixture, no HDD and an unrelated 2 GiB
HDD. The initial page was also shown. Exact observations and coverage limits
are recorded as text in [ExternalRescue.md](ExternalRescue.md).

PR #17 remains the read-only HDD journal baseline.
F8 followed by Enter reads the identity-bound A/B journal records and compares
the current MBR; F10 audits eight management files. The manual procedure
provided after PR #17 was reported checked and confirmed. No additional
image/language, machine/BIOS, individual field values or separate key-path
observations were supplied for that earlier report.

The F10 status `0000 / 0000` was separately confirmed on 13 November 2026.
English F7 followed by F9 from PR #14 was confirmed under VirtualBox that day:
matching preview, `0000 / 0000 / 0000`, unchanged masks, the F9 hint and
`RB HANDOFF PASS`. No BIOS version, physical-hardware coverage or original-OS
start was established. Earlier reports cover the ABI floppy, HDD/C startup,
menu, partition scanner, English/German builds, F3, isolated T07, F5/F6 and
German F7. Their coverage remains limited to the reported results.

## Body/tail fingerprint baseline (PR #34)

Branch `codex/rescue-crc-tail-checks` fixes an observed gap in F5/F6 change
checks before further backup collection work. A record rewrite confined to
its second half, followed by recalculation of the trailing CRC, preserved both
former half-sector fingerprints. A valid eighth-profile rename reproduced
this in the native live observer; a BIOS-injected opaque saved-payload rewrite
reproduced it in F5. Both regressions accepted the changed bytes before the fix.

The shared `rb_fingerprint_sector` chains the first 508 and last four bytes
separately, retaining addresses and read order. Live acquisitions, outer F6
passes and F5 saved-file revalidation use the same helper. Status meanings,
read sequences and file formats remain unchanged. This closes the reproduced
CRC-residue gap; collisions remain possible, and no authentication or atomic
snapshot is claimed. Complete capture and original-MBR provenance remain open.

The native planner now has 139 scenarios / 710 assertions. A stable renamed
record is accepted; inner/outer changes are rejected with cleared claims.
F5 adds one nine-state fault case per language on floppy and instrumented CD,
including F4 success and repeated F5 rejection. Local verification passed:
199 host tests plus reference layout, repeated EN/DE rescue/CD builds, and
318 boots / 2,480 UI states. All 314 previous cases retained their structured
read/VGA observations. CI and published-artifact evidence are recorded in the PR.

Normal rescue payloads shrink by 108 bytes to 34,240 / 34,504 bytes EN/DE.
BSS remains 20,820 bytes; static headroom is 2,284 / 2,020 bytes against the
unchanged 1,536-byte minimum. Stack guards and 8 KiB stack remain unchanged.
The standalone planner has 13,034 bytes of static headroom.

Manual check: boot `rescue/backup-plan-model.img` (or `rescue-de/`) from the
new `retroboot-rescue-diagnostics` artifact, with no HDD required. Expected:
`G=02C6` and `RB BACKUP PLAN PASS`. The program halts; restart or VM shutdown
exits. Subsequent manual confirmation is recorded above. Normal rescue has no new
key or message. The three published target HDDs and synthetic backups remain
unchanged; the BIOS-only fault fixture is separate.

## Native metadata encoding baseline (PR #33)

Branch `codex/backup-metadata-encoder` adds a C/16 encoder for the existing
version-1 header and four descriptor-table sectors. Explicit identity, roles,
addresses, file offsets and payload CRCs are checked for valid framing; reserved
bytes and unused slots are zeroed. No payload is collected or checked by this
API. The preliminary current-MBR kind 0 is rejected, not promoted to an original
or approved MBR. Every call validates the complete framing, supports arbitrary
metadata-sector request order and clears output on failure. No static scratch,
retained pointers, I/O callbacks or writer are added.

The encoder is linked only into `backup-encode-model.img`. Shared private
identity/descriptor/CRC helpers preserve the existing container reader's
validation and read order. Normal rescue payloads increase by 72 bytes to
34,348 / 34,612 bytes EN/DE; BSS remains 20,820 bytes and headroom is
2,176 / 1,912 bytes above the unchanged 1,536-byte minimum. The encoder model
has 6,544 bytes of static headroom. The fixed stack guard and 8 KiB stack remain.

The [standalone procedure](BackupEncoding.md#manual-virtualbox-check) uses
`rescue/backup-encode-model.img` (or `rescue-de/`) from
`retroboot-rescue-diagnostics`; no HDD is required. Expected output is
`H=04F2` and `RB BACKUP ENCODE PASS`: 64 scenarios / 1,266 assertions.
The standalone result was confirmed on 15 November 2026; coverage limits are
recorded above. Normal rescue F4/F5/F6 have no new key or message; all three published target HDDs and synthetic backups are unchanged.

Verification scope is 197 host tests plus the reference layout, both repeated
rescue/CD builds, and 314 boots / 2,444 UI states. Exact byte oracles cover
32-/64-bit wire values, table boundaries, EDD/CHS, files over 64 KiB and 1 MiB,
invalid framing, output clearing, const inputs and guarded full-reader round
trips. Deliberately incorrect payload CRC claims demonstrate the encoder's
boundary. Prior native assertion counts and F5/F6 read oracles remain unchanged.
Actual local, CI and published-artifact evidence is recorded in the PR.

Complete source capture, payload CRC collection, original-MBR provenance,
current-MBR approval, stable export and targeted restore remain open. The HDD
implementation, frozen specification, disk formats and read-only scope remain.

## Live installation-reference baseline (PR #32)

Branch `codex/rescue-installation-links` extends both rescue F5 and F6 with
selected configuration/state link validation. Individually valid record CRCs
are insufficient when a profile references an absent or incompatible
installation. The existing saved-record rule now lives in one shared helper:
nonzero IDs must match slot/type/kind/start/length; approved profiles require
READY. Drafts without IDs, unapproved pending references, empty lists and
multiple profiles for one installation remain valid. A/B generations are
selected independently; older copies still validate, but are not selected
link claims. F4 behavior remains unchanged.

The appended target status `0x000B` reports the first failing profile index
and target start. F5 maps it to `0x0004 / 0x000B / index`; F6 maps it to
`0x0000 / 0x0002 / 0x000B / index`. Failures clear source addresses, READY
claims and display results. No additional disk reads occur; intact success
oracles remain 1,058 for F5 and 2,188 for F6.

The new published `retroboot-rescue-bad-reference-hdd.img` changes only both
configuration installation IDs and their checksums. With the current demo
floppy/CD, F4 stays green; F5/F6 turn yellow at target LBA `0x00020000`.
The intact `retroboot-rescue-target-hdd.img` and the distinct
`retroboot-rescue-bad-fsinfo-hdd.img` are unchanged. The [manual procedure](BackupCapturePlan.md#installation-reference-check)
uses exact filenames and codes. German manual confirmation is recorded in
the saved baseline above.

The shared helper adds 68 bytes to normal rescue payloads: 34,276 / 34,540
bytes EN/DE. BSS remains 20,820 bytes; headroom is 2,248 / 1,984 bytes, above
the unchanged 1,536-byte build minimum and below the fixed `0xE000` guard.
Disk formats, frozen specification, HDD implementation and read-only scope
remain unchanged. Original-MBR provenance, current-MBR approval, serialization,
export and restoration remain open.

Verification scope is 194 host tests plus the reference layout; the native
capture-plan model has 136 scenarios / 692 assertions (`G=02B4`). It covers
selected/older A/B links, both ID halves, incompatible kinds, approved pending
states, drafts, empty lists, eight profiles, last-index errors, later-pass
changes and source clearing after prior success. Saved-record, saved-boot and
target models retain 296, 396 and 178 assertions. Full rescue regression is
312 boots / 2,444 UI states across both languages and floppy/CD paths; F6
includes a success-to-unlinked host mutation. Exact reads, VGA, memory guards,
unchanged source media and zero guest writes remain required. Actual local,
CI and published-artifact results are recorded in the PR.

## Saved-check sector-buffer baseline (PR #31)

Merged PR #31 addresses the narrow static-memory margin
before further rescue features. Saved-record checking and subsequent saved FAT
boot-area checking share three 512-byte buffers in an explicit union. The
record phase completes before the boot phase starts. Container descriptors,
partition scan, selected config/state and reader context remain separate and
valid for F5. Every new record check clears the complete context; each boot
buffer is filled before use. The existing non-reentrant contract remains.

| Normal rescue measure | PR #30 EN / DE | PR #31 EN / DE |
| --- | --- | --- |
| Payload bytes | 34,146 / 34,410 | 34,208 / 34,472 |
| BSS bytes | 22,356 / 22,356 | 20,820 / 20,820 |
| BSS end | 56,502 / 56,766 | 55,028 / 55,292 |
| Gap below stack guard | 842 / 578 | 2,316 / 2,052 |

The 1,536-byte BSS reduction costs 62 payload bytes, leaving 1,474 bytes more
static-memory headroom. The fixed 8 KiB stack and its guard at `0xE000` remain
unchanged. Builds now require at least 1,536 bytes below that guard and record
`headroom_bytes` for every native rescue variant. This is a build reserve,
not a stack-usage measurement or a changed image-format requirement.

Host coverage is 192 tests plus the reference layout. The saved-boot model has
66 scenarios / 396 assertions (`D=018C`): all successful returned container
claims and unused descriptor slots are checked after scratch reuse; failures
must return no claims. A new successful reopen immediately follows a late
failure and uses distinct nonzero VBR/continuation copies. The existing rescue
campaign covers 298 boots / 2,310 states, including F4/F5/F6 transitions,
repeats, exact reads, VGA, memory guards and zero-write checks. Validation and
published artifact evidence are recorded in the PR.

Manual regression uses the current demo rescue floppy or ISO and the matching
intact `retroboot-rescue-target-hdd.img`: F4, F5, F6, then F4 and Enter again should remain green; Esc
returns to diagnosis. There is no new key or visible feature in this increment.
The [saved-check lifetime](BackupBootAreas.md#shared-sector-buffer-lifetime)
explains the bounded reuse. The frozen specification, HDD implementation,
disk formats and read-only scope are unchanged.

## Complete live FAT boot-area baseline (PR #30)

Merged PR #30 strengthens the existing rescue F6 path.
After the entire range plan fits, every supported FAT reserved sector is read.
FAT32 FSInfo structures, primary/backup boot copies and selected READY
first-VBR CRC claims must agree with the supported rules. Two complete passes
also compare ordered fingerprints, including padding bytes. The current
increment corrects the original half-sector split to a 508/4 body/tail split.
Failure clears every range/count/size field. Plan status `0x0009` adds precise
content diagnostics; existing status values and disk formats remain stable.
The shared FSInfo helper retains saved-file F4 behavior and test coverage.

The good target still yields eight ranges, two pages and 23,040 estimated bytes.
The published `retroboot-rescue-bad-fsinfo-hdd.img` supplies a simple negative
VirtualBox check: F6 codes `0x0000 / 0x0009 / 0x0007 / 0x0001`, error LBA
`0x00020001`, with ranges and size blank. Both targets are synthetic and
nonbootable. The [F6 procedure](BackupCapturePlan.md#manual-virtualbox-check)
identifies the exact good/bad files and the boot medium. German confirmation
of both results is recorded in the saved baseline above.

The workflow display name is now **BIOS ABI and Rescue** (formerly **BIOS ABI
probe**). The workflow file and `bios-probe` job/check remain unchanged.
Rescue floppy/HDD and CD artifacts belong to this workflow; **HDD BIOS boot**
publishes the separate `retroboot-hdd-bios` artifact. Active download guides
and the embedded CD README identify the F6 action.

The expanded native model has 113 scenarios / 574 assertions (`G=023E`) and
an independently checked 2,188-read success trace. It includes complete boot
areas, malformed FSInfo/copies, selected/older READY claims, pending states,
42 read failures, valid changed bytes and exact container-limit behavior.
Its model-only startup deadline is 60 seconds; ordinary startup/UI deadlines
remain 15 seconds. Existing saved-boot and target models retain 325 and 178
assertions respectively. Host coverage remains 190 tests plus reference layout.

The live F6 campaign has 26 floppy boots / 264 states per language, plus five
instrumented and four bare CD boots / 98 states per language. A host FSInfo
mutation after success verifies stale-result clearing. Full rescue scope is
298 boots / 2,310 states, with exact read sequences, full VGA, memory guards,
unchanged source media and zero guest writes checked. Published CI and artifact
verification are recorded in the PR.

At PR #30, both rescue languages reproduced. Payloads were 34,146 / 34,410
bytes EN/DE; BSS ended at 56,502 / 56,766, below the 57,344 stack guard.
The German margin of only **578 bytes** prompted the PR #31 buffer-reuse
increment. Full-area scratch uses two bounded sector buffers on the
existing guarded 8 KiB stack, alongside the unchanged 908-byte display result.
The frozen specification, HDD implementation and disk formats are unchanged.
Original-MBR provenance, current-MBR approval, serialization, export and
restoration remain open; this is still a read-only preliminary plan.

## Numeric/byte display and F5 baseline

Merged PR #24 integrates the existing comparison core
with the normal rescue program. F5 opens and fully validates `RBBACKUP.RBB`,
rediscovers the first HDD, performs two independent live-metadata acquisitions,
reprobes the device and revalidates the complete saved file before success.
Ordered fingerprints reject tested correctly resealed changes. The current
increment closes the late-record blind spot in the original half-sector split.
Every failure clears successful device/identity/layout/generation fields.
Enter repeats; F4 selects the file-only check; Esc clears to diagnosis.
There are no writes, restore actions or OS starts.

Merged PR #25 displays hexadecimal numeric values with one `0x`
prefix and opaque media IDs as sixteen space-separated byte pairs in stored
order. Both normal HDD menus and rescue pages use this convention in English
and German. Numeric 64-bit fields have one prefix for the complete value;
decimal counters and ASCII debug markers retain their existing form. Status
columns have been widened without changing codes, disk formats or checks.
The [display conventions](Languages.md#numbers-and-byte-sequences) describe the
number/byte distinction. German rescue confirmation is recorded above.

PR #24 is merged into `historical` at
`5fa5c2ac155ca1e3ba908ad2373b3f8e02e16034`. All four checks passed for its
F5 commit `ad6bbb60f96fc1b4d58809a127d54f5913680e79`. PR #25 builds on that tree.

The artifact adds `retroboot-rescue-target-hdd.img`, a nonbootable 128 MiB
synthetic HDD paired with the existing demo backup. It is not the normal or
handoff HDD image. The [F5 guide](RescueTargetCheck.md) gives the exact two-file
setup, new-VDI conversion, expected values and boundaries.

The English F5 success page was manually confirmed under VirtualBox on
14 November 2026: green match, check/detail/nested and record detail zero,
disk ID `52425431`, media ID `A6216F345CD2467790ABC0137D8452E9`, layout CRC
`6FF4FB5E`, management `0000007E / 0001F5C9`, capacity `0000000000040000`,
EDD with zero heads/sectors, generations `00000001 / 00000001` and both
error LBAs zero. The screenshot did not separately establish the workflow
revision, exact image paths, BIOS/version or Enter/F4/Esc results. Evidence
is retained as text; the supplied image was discarded as requested.

Verification at the display baseline: 175 host tests; both rescue builds reproduced; 188 rescue boots /
1,244 UI states. The new 24 nine-state campaigns per language include real EDD
and CHS reads, damaged/missing file or HDD metadata, failed/changed reprobes,
changed and correctly resealed saved content, and stale-result clearing after
an initially successful operation. An independent oracle checks 1,058 HDD and
267 floppy reads for each successful EDD comparison. Native target assertions
and all earlier models remain exercised. Test ROM modes 0..13 are byte-identical
to PR #23. Normal payloads are 29,686 / 29,908 bytes (EN/DE), with BSS ending at
50,440 / 50,662, below the 57,344 stack guard. The HDD menu changes only
presentation; BIOS adapters, validators, disk formats and ABI implementation
sources remain unchanged. CI results remain attached to the proposed PR.

The [core contract](BackupTarget.md) records comparison codes and limitations.
The [getting-started guide](GettingStarted.md) now distinguishes rescue F4,
rescue F5 and HDD F10, including the new matching HDD fixture. Cloned identity,
non-atomic observation and original-MBR provenance remain explicit limitations.

## Backup-file baseline on the rescue floppy

Merged PR #22 adds a read-only F4 path for `RBBACKUP.RBB`
on the boot floppy. A bounded FAT12 reader checks both FATs and all regular
root-file chains before constructing a fragmented file map. The file is then
streamed through the existing container, saved-record and FAT boot-area checks.
Metadata is reread after success. The HDD context is not used or modified.
Enter repeats the selected file check; Esc returns to HDD diagnosis.

The [file-validation guide](RescueBackupFile.md) contains the manual procedure
and status codes. Separate EN/DE `retroboot-rescue-demo.img` images carry
synthetic data and expect `0000 / 0000 / 0000` on F4. The normal images contain
no backup file and expect `0005 / 0000 / 0000`. The German demo has the manual
confirmation recorded above. F4 success is about saved content, never a live
target or restore.

Verification: 167 host tests; 138 rescue boots / 812 UI states; both languages
built twice. A new native model adds eight scenarios / 32 assertions, including
a 1 MiB file map, range rejection, changed metadata, read failure and clearing
of stale maps. Twenty-seven real file/keyboard campaigns per language check
fragmentation, bad media metadata, content errors, retries and HDD-context
isolation. Normal rescue payloads are 22,158 / 22,296 bytes (EN/DE); HDD and
ABI implementations are unchanged. Runtime initialization was separated from
the menu so native checker models remain within the segment budget.

## External container baseline

Branch `codex/external-backup-format` defines a bounded sector-based container,
a Python encoder/inspector and a streaming native C/16 validator. Its header
stores claimed media/disk identity, layout, capacity and geometry; descriptors
carry original/approved MBRs, EBRs, multi-sector or discontiguous boot areas and
configuration/state copies. Bounds, ordering, overlap, required roles and CRCs
are checked. Failed validation clears all selected metadata.

The [container contract](ExternalBackup.md) specifies the wire format, status
codes, host command and exact trust boundary. Structural validity does not
prove snapshot completeness, record semantics, provenance, live-media identity
or permission to restore. Only synthetic format examples are generated. Real
collection and restore remain open. The later F5 path compares supported
current metadata, without proving unique physical identity or provenance. The subsequent F4 path loads and validates the file; it does not restore it.

Verification adds nine host tests (149 total) and 72 native scenarios with
216 assertions (`B=00D8`, `RB BACKUP MODEL PASS`) per build language. The model
includes a 1 MiB streamed file, boot areas over 64 KiB, 42 descriptors, separated
boot regions, resealed malformed fields, payload damage and final-sector I/O
failure. At PR #19, normal rescue binaries/images were unchanged and backup code was
linked only into an additional model variant. F4 now uses the checkers too.

## Independent rescue baseline

Merged PR #18 adds a separate 1,440 KiB FAT12
floppy in English and German. It has its own CRC-pinned loader, C startup,
BIOS discovery and MBR/EBR diagnostic page. No HDD code or filesystem is needed
to start. Enter reads drive `80h`; Enter repeats; Esc clears. The observed disk
ID is explicitly not an independently verified identity. That initial baseline had no backup
file reader. F4 now supplies one; disk writes, restore and HDD handoff remain
unavailable. The later rescue ISO packages the same floppy.

The [external rescue guide](ExternalRescue.md) contains the manual procedure,
format, codes, trust boundary and evidence. CI publishes the two floppies as
**retroboot-rescue-diagnostics** in the existing ABI workflow. The earlier ABI
floppy and four normal/handoff HDD images remain byte-identical. The
[journal diagnosis](JournalDiagnosis.md) and [journal format](TransactionJournal.md)
remain the HDD baseline.

Verification scope:

- 190 host tests plus the reference layout report, including file access, all three backup layers, target comparison, capture planning and ISO packaging.
- Rescue: both languages built twice, 38 boots and 217 UI states each
  (76 boots, 434 states total), including absent/damaged HDDs, EDD/CHS,
  BIOS faults, read retries and rejected floppy/C-startup variants.
  Each native rescue model executes 28 assertions (`R=001C`).
  The additional checker models and file campaigns bring the current total to
  190 floppy boots and 1,244 UI states across both languages before F6.
  F6 now adds 52 floppy boots / 528 states. All CD campaigns total 56 boots /
  538 states, bringing the combined scope to 298 / 2,310.
- Every rescue UI state checks VGA, program bytes, BSS/stack guard,
  exact HDD reads and absence of writes. Source media and disposable HDD
  copies remain unchanged except for explicitly recorded host mutations in two
  F5 cases and one F6 case per language; no guest writes occur. Independent host vectors decode FAT12 packing
  and file allocation. Current payload sizes: 34,146 bytes EN / 34,410 bytes DE.
- Existing HDD scope remains 104 boot cases, 47 identical EDD/CHS sector
  sequence pairs and 7,362 UI states across both languages. Native models
  retain 126 journal, 42 journal-reader, 80 allocation, 26 menu, 51 partition,
  114 volume/arithmetic, 29 handoff, 84 configuration, 86 state, 52 visibility
  and 60 profile assertions. The ABI floppy retains three boot cases.
- Normal HDD Stage 2 remains 38,000 bytes EN / 38,610 bytes DE; handoff
  remains 42,342 / 43,012 bytes. The 48 KiB file and 8 KiB stack budgets remain.

Local native tests use QEMU 10.0.13/SeaBIOS with `pc-i440fx-8.2`, CPU `486`
and 16 MiB RAM; CI records its own versions and ROM hashes. PR checks/artifacts
provide validation for the proposed commit; merge remains part of project
review. The German external floppy has the manual evidence recorded above.

English is the default; German shares the logic and CP437 encoder including
`ÄÖÜäöüß`. Repository prose is impersonal and excludes private details.
The frozen specification v0.2 and archives are unchanged.

## Open work

1. Complete independent external recovery before the first write tests:
   extend supported saved boot formats and validate original-MBR provenance; collect
   a complete backup using the bounded container, saved-record and FAT boot-area
   checkers, with independent media/geometry binding and
   all required MBR/EBR/VBR metadata, including FAT32 backup headers and
   configuration/state. The F4 file-validation path is available, but does not
   establish provenance, live target binding or recovery completeness. The
   read-only F5 path integrates fresh rescue BIOS discovery and file validation
   with the target-comparison core. Unique physical identity and recovery
   authorization remain outside that result. Add verified, explicitly confirmed targeted restore
   and interruption tests. Diagnosis alone does not satisfy this requirement.
   The live rescue F6 path now validates complete supported FAT boot areas;
   metadata serialization and provisional container output have standalone native
   models; connecting fresh live sources to explicit MBR roles, destination
   storage/readback and provenance remain open. The separate
   [payload observer](BackupPayloads.md) now collects whole-extent CRCs within
   two freshly validated passes, retaining no payload bytes. The rescue ISO has automated CD-boot coverage and
   reported English VirtualBox F4/F5 success; broader manual and physical BIOS
   compatibility remain open.
2. Add fresh ownership/identity checks and verified prepare/MBR/completion
   writes with interruption tests after every step. The present observation
   is neither an atomic snapshot, a durable-history proof nor a write lease.
3. Add fresh installation identities and controlled installer state transitions.
   Original-OS starts still need separate authorization and compatibility evidence;
   HDD F9 remains bound to the exact owned T07 test sector.

## Resuming after a pause

Start with current GitHub branches/PRs, repository code and the open items above.
Interrupted tests restart; transient emulator state is not a saved checkpoint.
Completed increments are committed and proposed as PRs for project review.
