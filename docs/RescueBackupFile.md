# Read-only backup-file validation

The independent rescue floppy now reads `RBBACKUP.RBB` from its own FAT12 root
directory when **F4** is pressed. It checks the file allocation, then runs the
existing [container](ExternalBackup.md), [saved-record](BackupRecords.md) and
[FAT boot-area](BackupBootAreas.md) checks. A successful result describes the
saved file only. It does not identify an attached HDD or authorize recovery.
The operation does not replace the running configuration or installation state.

## Manual check

The **retroboot-rescue-diagnostics** artifact in the **BIOS ABI and Rescue** workflow
contains two images per language:

| Artifact path | Contents | Expected F4 result |
| --- | --- | --- |
| `rescue/retroboot-rescue-demo.img` | English program and synthetic test metadata | `0x0000 / 0x0000 / 0x0000` |
| `rescue-de/retroboot-rescue-demo.img` | German program and the same synthetic metadata | `0x0000 / 0x0000 / 0x0000` |
| `rescue/retroboot-rescue.img` | English program, no backup file | `0x0005 / 0x0000 / 0x0000` |
| `rescue-de/retroboot-rescue.img` | German program, no backup file | `0x0005 / 0x0000 / 0x0000` |

All images are 1,474,560-byte floppy images. The demo is **not a backup of any
attached disk**. Its original-MBR field is empty, and its boot regions contain
test headers rather than an OS boot program. It is unsuitable for restoration.

1. The selected demo image is attached as floppy A: with the VM powered off;
   floppy boot precedes HDD boot. VirtualBox uses a floppy-controller attachment,
   without raw-to-VDI conversion. The existing HDD may remain attached.
2. After the initial diagnosis page appears, **F4** checks the saved file.
   Expected file/check/detail: `0x0000 / 0x0000 / 0x0000`; nested detail `0x0000`.
   The result is green, with volumes/FAT16/FAT32 `0x0002 / 0x0001 / 0x0001`,
   reserved sectors `0x0021` (hexadecimal, 33 decimal), and READY VBR matches `0x0001`.
3. **Enter** repeats the file check. **Esc** returns to the cleared HDD diagnosis
   page. Enter there performs the existing HDD diagnosis; F4 returns to the file
   check. An absent HDD does not prevent the file check from succeeding.
4. The normal image, which has no `RBBACKUP.RBB`, reports file status `0x0005`
   and no successful volume counters. This is the expected missing-file result.

The German demo's F4 result was manually confirmed under VirtualBox on
14 November 2026: all codes and error locations zero, volumes `0002 / 0001 / 0001`,
reserved sectors `0021` and READY matches `0001`. Enter-repeat and Esc-return
were not separately reported. No English F4, physical-hardware or BIOS-version
coverage follows from that observation. Earlier VirtualBox diagnosis observations
remain in [ExternalRescue.md](ExternalRescue.md). The [getting-started guide](GettingStarted.md)
provides download and image/key orientation.

## File access contract

The reader supports the owned 1,440 KiB FAT12 superfloppy layout: 512-byte
sectors, one sector per cluster, one reserved sector, two nine-sector FATs,
224 root entries, 18 sectors per track and two heads. Other BPBs are rejected.
The BIOS adapter accepts only boot drive `00h` and LBAs `0..2879`. Each attempt
reads one sector into a low-memory bounce buffer, with at most three attempts
and resets on read failure. It never changes the HDD discovery/context fields.
The caller's output buffer is copied only after a successful BIOS read.

Both complete FAT copies must agree, including unused bytes. The reader walks
every active regular root file, verifies exact chain length/end markers, and
rejects cycles, cross-links, free/bad/reserved/out-of-range cluster references,
nonzero high cluster words and unsupported directory entries. Subdirectories
are unsupported. Deleted entries and LFN records are skipped; the first zero
entry ends directory interpretation. All root sectors are still included in
the metadata checksum. Orphan allocations outside root-file chains are not
traversed or claimed to be a complete filesystem audit.

Only the exact short name `RBBACKUP.RBB` is selected. Duplicate matching names
are rejected. File length must be sector-aligned and between 2,560 bytes and
1 MiB. A validated FAT and a small index permit random reads from fragmented
files of up to 2,048 sectors. A failed open or
read clears the map and successful counts. An out-of-range file read performs
no disk I/O. A fresh F4/Enter check reconstructs the map each time.

The packed FAT12 entries and end markers follow Microsoft's
[FAT specification 1.03, pages 16–18](https://www.isdaman.com/alsos/protocols/fats/fatgen103.pdf).
The fixed geometry, flat-root restriction and file-size limit are RetroBoot
constraints, not general restrictions on FAT12.

After successful saved-content validation, all 33 metadata sectors are read
again and compared through CRC32. Changed metadata invalidates the result and
clears displayed success counters. The medium must remain stable during a check;
the reread detects changes but does not make the acquisition atomic or authentic.
The adapter context is valid only during this operation. Scratch is non-reentrant.

## FAT12 index and memory

Each open file retains its own copy of the nine-sector FAT (4,608 bytes).
For this geometry, cluster 2,848 is the last valid cluster. Its packed entry
ends at byte offset 4,273. Once all nine sectors of the second FAT match the
first, including padding, bytes 4,352 through 4,607 can hold 128 cluster
numbers. The checksum covers the original bytes before indexing. Compile-time
checks enforce both the total map size and the boundary of the usable links.

The root scan checks every file chain and records the first cluster of each
group of 16 sectors of `RBBACKUP.RBB`. A random read starts at that cluster,
follows at most 15 links in memory and issues one physical sector request.
Opening or invalidating another file uses that file's own FAT. Reopening a
file checks both FATs again and rebuilds its index.

| Normal rescue measurement | Before (EN / DE) | With the FAT12 index (EN / DE) |
| --- | ---: | ---: |
| Program file, bytes | 34,644 / 34,912 | 34,708 / 34,976 |
| BSS, bytes | 20,820 / 20,820 | 16,724 / 16,724 |
| Space below stack guard, bytes | 1,880 / 1,612 | 5,912 / 5,644 |

Removing the 4,096-byte address array costs 64 bytes of code per language
and frees 4,032 bytes overall. The 8 KiB stack starts at `0xE000`. The build
requires at least 1,536 bytes between BSS and the stack guard.

A sizing experiment repeated the normal link with `backup-live.obj`,
`backup-stream.obj` and `backup-encode.obj` immediately before `end.obj`.
The control link reproduced the normal payload byte for byte after sealing.
The trial left 2,114 / 1,846 bytes below the guard, or 578 / 310 bytes above
the minimum (EN / DE). The future BIOS caller, its data and its runtime stack
use still need to be measured in the integrated build.

## Diagnostic codes

The page shows file status, saved-content status and saved-content detail.
The next line retains the nested record/container detail. Saved-content codes
are specified in [BackupBootAreas.md](BackupBootAreas.md). If the file layer
fails, saved-content fields and counters are cleared rather than presented as
an independent successful result.

| File status | Meaning |
| --- | --- |
| `0000` | File access succeeded; saved-content status still needs checking |
| `0001` | Floppy read failed; physical error LBA is shown |
| `0002` | Unsupported or invalid BPB/boot signature |
| `0003` | FAT copies disagree or reserved FAT entries are invalid |
| `0004` | Unsupported or inconsistent root-directory entry |
| `0005` | No matching backup file |
| `0006` | Duplicate matching filenames |
| `0007` | Invalid file size or unsupported backup size/alignment |
| `0008` | Invalid or incorrect-length cluster chain |
| `0009` | Reused cluster: cycle or cross-link |
| `000A` | Metadata changed during the successful-content check |
| `000B` | File read outside an active checked map; no physical read |

The floppy error LBA refers to the source diskette. The saved-disk error LBA
is a claim inside the file, not an access to the attached HDD. A root-chain
error reports the physical root sector containing the rejected entry.

## Validation and remaining work

The file increment brought the host suite to 167 tests. Six tests verify fragmented packing, the 1 MiB
allocation bound, root/LFN fixtures, preserved executable payloads, exact
physical-read expectations and rejection of stale success fields.

The native file model adds eight scenarios / 32 assertions per language
(`E=0020`, `RB RESCUE FILE PASS`). It checks the maximum map and its last sector,
range rejection without I/O, context reuse after a missing file, changed
metadata, final-sector recheck I/O failure, unchanged output on payload read
failure, EOC variants, cleared maps and guard bytes.

An additional native case reads all 2,048 offsets of a fragmented 1 MiB file
in alternating order from the start and end. It checks the requested physical
address and a single reader call for every offset (`M=0800`), including the
last physical sector. It also checks independent file contexts, nonzero FAT
padding, a mismatch in the last mirror byte, metadata recheck and reopening
with a partial final group.

The file increment brought the EN/DE rescue campaign to 138 boots / 812 UI states.
This includes 27 seven-state file campaigns per language, covering fragmented files,
the odd FAT12 entry at byte 511, the last disk sector, a file over 64 KiB,
the last root slot, malformed FATs/chains/directories/files, content errors,
bounded BIOS retries, no-HDD operation and return to HDD diagnosis. Assertions
check exact floppy/HDD reads, unchanged program/guard bytes, VGA, source hashes,
HDD context preservation and absence of BIOS/block writes. Both languages build
twice identically; all earlier native checker models remain exercised.

At the file-only increment, normal rescue payloads were 22,158 bytes EN / 22,296 bytes DE, with BSS ending at
37,762 / 37,900, below the 57,344 stack guard. Runtime initialization is now a
separate compilation unit so checker models do not need the menu and complete
file-validation stack. Model binaries therefore change too. HDD and ABI
implementation sources remain unchanged.

Original-MBR provenance, boot-code/overlay classification, other saved filesystem
formats, management-file ownership, real snapshot collection, independent
live-media/geometry binding and explicitly confirmed targeted restoration are
still open. The [target-comparison core](BackupTarget.md) retains its native
model tests and is now integrated through a separate [F5 path](RescueTargetCheck.md).
F5 validates the complete file before and after fresh live HDD comparison;
F4 remains file-only. The current total is 175 host tests and 188 rescue boots /
1,244 UI states. Current sizes and the matching synthetic image pair are in the
F5 guide. Neither path completes the external recovery requirement or enables
disk writes.
