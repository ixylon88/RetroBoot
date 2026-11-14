# Rescue F5: compare a saved file with current HDD metadata

From **RetroBoot Rescue**, **F5** checks `RBBACKUP.RBB` on floppy A: and
compares its identity, capacity, BIOS geometry and canonical layout claims
with freshly acquired metadata from the first HDD (`80h`). Every invocation
starts again. **Enter** repeats this comparison, **F4** selects the separate
saved-file check, and **Esc** clears the result and returns to diagnosis.

The operation reads only. It does not restore, install, change visibility or
start an OS. A match describes the supported metadata; it does not distinguish
physical disks with cloned identifiers or authorize a later write.

## Manual VirtualBox check

Use one successful **BIOS ABI probe** run containing the F5 increment. Download
its **retroboot-rescue-diagnostics** artifact and extract it into a fresh
build-specific directory. The pair is:

| Role | Path inside the artifact | Size |
| --- | --- | ---: |
| English floppy A: | `rescue/retroboot-rescue-demo.img` | 1,474,560 bytes |
| German alternative for floppy A: | `rescue-de/retroboot-rescue-demo.img` | 1,474,560 bytes |
| Matching synthetic first HDD | `rescue/retroboot-rescue-target-hdd.img` | 134,217,728 bytes |

The HDD under `rescue-de/` has identical bytes. Only one language is needed
for the manual check. The usual `retroboot-hdd.img` and `retroboot-handoff.img`
are different fixtures and are not the matching HDD for this saved example.

1. Power off the test VM. Keep legacy BIOS enabled and **Floppy** first in
   the boot order. Attach the selected demo floppy directly as A:.
2. Convert the new target HDD image into a **new VDI**, rather than reusing a
   VDI from an earlier HDD test. For the default Windows installation, open
   PowerShell in the extracted artifact's `rescue` directory and run:

   ```powershell
   & "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe" convertfromraw `
     "retroboot-rescue-target-hdd.img" "retroboot-rescue-target-hdd.vdi" --format=VDI
   ```

   The output filename must be unused. With a different VirtualBox installation
   directory, use that installation's `VBoxManage.exe` path. The raw input is
   preserved. Oracle documents this [conversion command](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/vboxmanage.html#vboxmanage-convertfromraw).
3. In **Settings → Storage**, detach the previous test HDD without deleting
   its file. Attach the new VDI as the first IDE HDD (primary master). No other
   HDD is needed. The new fixture is deliberately nonbootable: startup must
   come from the floppy.
4. Start the VM, confirm the title **RetroBoot Rescue**, and press **F5**.
   The green result should state that saved identity/layout match current HDD
   metadata. The expected EDD values are below.
5. Press **Enter** to repeat; the same result should return. **F4** should
   still show the familiar saved-file success. **F5** performs a new HDD
   comparison. **Esc** returns to the initial diagnosis page.
6. Optionally power off, detach the HDD and repeat F5. The expected result is
   `0x0003 / 0x0001 / 0x0000` (no HDD), with no retained successful identity fields.

| F5 field | Expected value for the published pair |
| --- | --- |
| Check / detail / nested | `0x0000 / 0x0000 / 0x0000` |
| Nested record detail | `0x0000` |
| Disk ID | `0x52425431` |
| Media ID | `A6 21 6F 34 5C D2 46 77 90 AB C0 13 7D 84 52 E9` |
| Canonical layout CRC32 | `0x6FF4FB5E` |
| Management start / sectors | `0x0000007E / 0x0001F5C9` |
| Reachable sectors | `0x0000000000040000` |
| Route / heads / sectors | `EDD / 0x0000 / 0x0000` |
| Config / state generation | `0x00000001 / 0x00000001` |
| Floppy / disk error LBA | Both `0x00000000` |

The published saved claims describe EDD and exactly 128 MiB. A BIOS that
provides CHS only or exposes a different capacity is rejected explicitly;
the automated CHS case uses a separate matching fixture. F5 on the normal
floppy, without `RBBACKUP.RBB`, reports `0x0001 / 0x0005 / 0x0000` before any HDD
probe or read. This is a different page and code sequence from F4's
`0x0005 / 0x0000 / 0x0000` missing-file result.

The English F5 success page was manually confirmed under VirtualBox on
14 November 2026. The screenshot showed the green metadata-match message,
the values in the table above in the earlier unprefixed notation, an
unsplit media identity, and zero record/error fields. The report did
not separately identify the workflow run, image paths, VirtualBox/BIOS
version, or Enter/F4/Esc results. It confirms this displayed result only;
physical-hardware, repeat-key and no-HDD coverage are not implied. The image
was discarded after recording this text evidence.

Further text reports need the workflow run, exact two image paths, language,
F5 codes and Enter/F4/Esc observations.
The [beginner guide](GettingStarted.md) explains the other screens and keys.

German VirtualBox screenshots on 14 November 2026 subsequently confirmed the
initial rescue page and this successful F5 result with the new numeric/byte
notation. All fields matched the table, including a single prefix on the
64-bit capacity, spaced media-ID bytes, zero errors and correct German text
including `schließen`. No workflow revision, exact image paths, BIOS/version,
repeat-key results or HDD-menu formatting were separately established. This
floppy evidence is retained as text; the supplied images were discarded.
The [CD packaging](RescueCD.md) adds a separate boot path whose manual check
remains pending.

## Composition and lifetime

The synchronous adapter in [rescue_backup.c](../core/rescue_backup.c) performs:

1. A fresh bounded FAT12 file lookup and map, with no reuse of earlier F4/F5
   success. It runs all container, saved-record and FAT boot-area validators,
   then rereads the floppy allocation metadata.
2. Fresh BIOS discovery for drive `80h`, followed by the existing
   [target-comparison core](BackupTarget.md). Its two complete acquisitions
   discover live addresses independently from the current MBR/FAT16 directory.
   Backup descriptor addresses never steer physical HDD reads.
3. A second BIOS discovery. Drive, route, capacity and geometry must still
   equal the initial observation.
4. A second complete saved-file validation and floppy metadata recheck. Read
   count and two ordered half-sector CRC chains must equal the first pass.
   The chains include file-relative sector addresses and detect tested changes
   even when a modified record/header has a newly valid trailing CRC.
5. Closure of the temporary file map. Every failure clears observed device,
   identity, layout and generation fields, retaining only error diagnostics.

`rb_backup_open_boot` returns the validated private header claims only on
success. They remain valid until the next saved-record/boot check and are used
only within this call. The code is non-reentrant. Each Enter/F5 reopens the
file and rediscovers the HDD; prior observations never become persistent
selection or authorization.

Sources must remain stable during the operation. Repeated reads and CRCs are
neither an atomic snapshot nor authentication. Changes after the final read
remain possible. Floppy errors identify a physical diskette LBA. A saved-file
failure's disk LBA refers to a claim in the file; a target failure's disk LBA
refers to an actual HDD read. Zero can also mean LBA 0 or no specific location.

## F5 codes

| Check, hex | Layer | Detail / nested |
| --- | --- | --- |
| `0x0000` | Success | Both zero; supported metadata correspondence only |
| `0x0001` | Floppy file access | [File status](RescueBackupFile.md); nested zero |
| `0x0002` | Saved content | [Boot-area status/detail](BackupBootAreas.md), with separate record detail |
| `0x0003` | Fresh BIOS discovery | [Probe status](ExternalRescue.md); nested zero |
| `0x0004` | Live target comparison | [Target status/detail](BackupTarget.md) |
| `0x0005` | Changed observation | `0x0001`: device changed on reprobe; `0x0002`: final saved-content fingerprint differs |

For example, `0x0004 / 0x0007 / 0x0000` means a capacity mismatch and
`0x0004 / 0x0006 / 0x0004` means an observed identity differs from saved claims.
An unsupported or damaged live MBR/FAT/identity is rejected; the backup's
addresses are never a fallback access path.

## Fixture and automated evidence

The new HDD is a synthetic metadata fixture, not a collected/restorable backup
or an installed RetroBoot system. Its MBR code, system boot areas, program
contents and journal payloads are absent. The eight management-file chains
exist for the allocation audit; only the four configuration/state payloads
are populated. Live record addresses differ from saved descriptor addresses
on purpose, demonstrating independent discovery.

`make rescue-test RB_LANGUAGE=en` and `RB_LANGUAGE=de` each add **24 boots and
216 keyboard/VGA states** for F5. Together with the earlier campaigns, the
floppy total is **188 boots / 1,244 states**; the host suite has **181 tests**.
CD boot adds 38 boots / 342 states using the same adapter and checkers.
The unchanged native target model retains 178 assertions per language.

The F5 campaigns cover EDD and CHS success, missing HDD/file, invalid saved
content, capacity/route/identity/layout differences, damaged live metadata,
allocation/record errors, bounded BIOS retries, failed/changed reprobes,
changed saved content and a correctly resealed header change. Two campaigns
first succeed, then alter a disposable host fixture between invocations:
missing floppy file and damaged HDD MBR. Old successful fields must disappear.
These intentional host mutations are recorded separately; guest writes remain
forbidden and source images unchanged.

An independent oracle requires **1,058 HDD reads** per successful F5:
two 529-read acquisitions. The normal demo also requires **267 floppy reads**,
including both full saved-content passes and metadata rereads. BIOS calls,
read order, all UI fields, program bytes, BSS/stack guard, absence of handoff,
media hashes and zero BIOS/block writes are checked. Evidence is published in
`rescue-match-test/` and `rescue-match-test-de/`; `match-results.json` is written
only after all requested campaigns pass.

Both language builds reproduce. Payloads are 29,686 / 29,908 bytes (EN/DE),
with BSS ending at 50,440 / 50,662 below the 57,344 stack guard. Old test ROM
modes 0..13 remain byte-identical; modes 14..17 inject only test faults.
The display convention also applies to the HDD menu. Disk formats, BIOS
adapters and validators are unchanged by that presentation adjustment.

Real backup collection, original-MBR provenance, broader boot-format support,
complete recovery authorization and interruption-tested restoration remain
open. F5 completes the bounded read-only integration, not external recovery.
