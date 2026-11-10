# T07: transition to an independent test VBR

This increment proves the real-mode handoff using an owned 512-byte test
boot sector. It does not authorize an installed OS. The normal diagnostic
images retain their read-only menu and ignore F4. The dedicated
`retroboot-handoff.img` adds an explicit F4 action on the main menu.

## Manual test

The **retroboot-hdd-bios** artifact contains two image kinds per language:

| Image | Purpose |
| --- | --- |
| `hdd/retroboot-hdd.img`, `hdd-de/retroboot-hdd.img` | Existing 64 MiB diagnostic menu, including F2/F3 |
| `hdd/retroboot-handoff.img`, `hdd-de/retroboot-handoff.img` | New 128 MiB T07 image, with a primary test target and the existing hidden management volume |

The [HDD guide](HDD_Boot.md) describes BIOS-mode QEMU/VirtualBox startup.
A new VirtualBox VDI must be converted from the new handoff image; a VDI from
an earlier image still runs the earlier program.

1. Boot `retroboot-handoff.img` as the first IDE disk in an empty BIOS VM.
2. The main menu has a yellow F4 test hint. Automatic boot remains disabled.
3. F3 can inspect P1, type `06`, VBR LBA `00020000`; it is a plausible FAT16
   header, with no claim that a complete filesystem exists.
4. Esc returns to the main menu. F4 performs the fresh checks and transfers
   execution. A black screen should show:

   ```text
   RB HANDOFF PASS
   Test VBR reached. Reboot to return.
   ```

The VBR has taken over at that point: it does not return to C or the menu.
A reboot starts RetroBoot again. This success message is stable English ASCII
in both language variants, like the existing ABI/boot test markers. A rejected
preflight stays in the menu with its reason; F4 retries, Esc returns and F2
opens the tables. `RB HANDOFF FAIL` is an independent target-side failure,
expected only in the deliberately broken transition fixtures.

The rejection page includes hexadecimal status/detail codes. Status `0001`
means a mismatched target entry, `0002` a table-scan error, `0003` a volume
header/read error and `0004` a mismatch with the compiled VBR. The detail
for `0002`/`0003` is the existing scanner/volume status; the corresponding
reason is also displayed as text.

Manual success for PR #9's F3 view was reported after its merge, without new
VM, machine or BIOS details. That evidence does not cover this new T07 image.

## Authorization and exact reads

The test build binds a disk ID, primary slot, all 16 MBR-entry bytes and all
512 VBR bytes at compile time. The first target is active FAT16 P1 at LBA
131,072, spanning 5,073 sectors. It follows the unchanged management container.
The test region contains only the BPB and executable probe, with no FAT,
directory, OS files or installer. It is not a usable FAT filesystem.

`core/handoff.c` performs these steps on every F4 attempt:

1. Reject an invalid slot or inactive expected entry before reading.
2. Read and validate the complete MBR/EBR layout using the existing scanner,
   including the bound disk ID and BIOS reach.
3. Require a visible active FAT primary and an exact match of its raw MBR
   entry, including CHS bytes. Empty, logical, hidden and unsupported targets
   are not authorized by this test path.
4. Inspect the FAT BPB with the existing parser and capture the **same sector
   read** that it validates. There is no unchecked second VBR read.
5. Compare the captured sector against the complete compiled test VBR. On
   success, hand that exact buffer to assembly. On any failure, clear both
   staged sector and entry and return an error to the menu.

The earlier F3 result is never reused as authorization. Successful F4 on the
normal handoff fixture reads MBR LBA 0, EBR LBA 63 and target LBA 131,072.
The BIOS reader retains EDD or CHS, with at most three attempts per sector.
Failed table validation prevents the VBR read. A matching BPB with modified
code is also rejected. There is no disk write, hook installation or drive swap.

The exact fixture binding is a deliberately limited test authorization,
not persistent installation identity or an OS profile. It does not establish
DOS/Win9x partition isolation, an NT loader configuration, whole-filesystem
integrity or atomicity against externally changing media. Those remain
separate work before any original-OS start.

## Transition contract

`bios/handoff.asm` is linked only into the explicit handoff-test variants.
With interrupts disabled, it copies the validated sector and entry before
leaving the C stack. A 16-bit IRET establishes the target address and restores
the caller's IF; DF is cleared explicitly. The menu calls with IF set.

| Item | Target state |
| --- | --- |
| CPU / entry | Real mode, `CS:IP = 0000:7C00` |
| VBR | All 512 bytes unchanged at physical `07C00h–07DFFh` |
| BIOS drive | `DX = 0080h`, hence `DL = 80h` |
| Partition pointer | `DS:SI = 0000:0800`, exact stable 16-byte MBR-entry copy |
| Segments | DS, ES, FS, GS and SS are zero |
| Stack | `SS:SP = 0000:7C00`, growing below the VBR |
| Flags | DF clear; caller IF restored, IF=1 for the menu test |
| Other general registers | AX, BX, CX, DI and BP zero |
| Disk interrupt | Existing INT-13h vector unchanged |

`include/handoff.inc` records the addresses. The entry copy occupies
`0800h–080Fh`, after the relocated MBR and before the existing sector buffer.
The target writes a 32-byte test receipt at `0820h–083Fh`; that receipt is
not an input to authorization. IVT/BDA, the old MBR, Stage 2 and its C stack
are outside the copied VBR and entry ranges. The stage-specific stack guard
continues to be checked in the emulator.

`tests/handoff/vbr.asm` captures entry flags, segment registers, SP, SI and DX
before normalizing anything. It checks real mode, its execution address,
required segments, stack, drive, IF/DF, signature and all 16 entry bytes.
Only then can it emit PASS. It performs no sector I/O. Its final BIOS text
output can change the live registers, so the captured receipt is the entry
state; the registers after the final halt are not substituted for it.

## Evidence and limits

```sh
make check
make hdd-test
make hdd-ui-test RB_LANGUAGE=de
make handoff-test RB_LANGUAGE=en
```

A direct run on already built images is also available:
`python3 tools/test_handoff.py --language en`, with optional `--qemu` and
`--bios` paths. Outputs are isolated under `build/handoff/` and
`build/handoff-de/`.

- 102 host tests include fixture preservation, literal primary-entry values,
  malformed inputs and independent rejection of corrupted receipt fields.
- 90 boot cases include 40 identical EDD/CHS read-sequence pairs. The new
  native C16 preparation model runs 29 assertions (`H=1D`) through each path,
  including stale-result rejection, bounded reads and cleared failure buffers.
- Each language runs 43 handoff campaigns and 185 screen states. Both BIOS
  routes exercise success, preflight errors, actual one-off/permanent read
  failures and nine intentionally faulty transitions: DS, ES, SS, SP, SI,
  DL, DF, IF and the copied partition entry. Normal-menu F4 is inert. A further
  positive run uses no test option ROM.
- Host inspection compares all 512 loaded VBR bytes, the entry and adjacent
  memory, the saved entry state and the INT-13h vector. VGA output, Stage 2
  bytes, BSS and stack guard are checked. Exact post-menu reads, EDD/CHS pairs,
  unchanged image hashes and absence of disk writes are required.

Together with the unchanged menu/scanner/volume suites, there are 782 states
per language and 1,564 across both languages. Both languages build twice with
byte-identical results. `handoff-results.json` is written only when all its
campaigns pass. Reports, text pages, screenshots, low-memory/Stage-2/VGA dumps
and disk traces accompany the two normal and two handoff images in CI.
Deliberately faulty images and the 8 GB reference image are excluded.

The implementation contract comes from specification v0.2, section 7; T07
is listed in section 16. That frozen document is unchanged. Passing these
probes establishes T07 for the recorded QEMU/SeaBIOS setup. Historical BIOS
hardware, OS profiles, installation identity and original OS loaders still
need their own evidence.
