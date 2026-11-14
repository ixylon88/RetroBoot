# Saved FAT boot areas

`rb_backup_check_boot` checks saved FAT16/FAT32 reserved areas after the
[container](ExternalBackup.md) and [record](BackupRecords.md) checks. It operates
on file-relative sector reads. It does not read an attached HDD or authorize
a restore. The normal rescue floppy and its menu remain unchanged.

## Supported scope

Every data partition in the approved view, including the hidden management
volume, must pass the existing [volume-header parser](VolumeHeaders.md).
Partition type `07h`/`17h` is unsupported by this layer. A valid record-only
result for such a container remains possible; boot-area success is refused.

The complete reserved region, from the volume start through
`BPB_RsvdSecCnt - 1`, must be present. Adjacent BOOT descriptors may divide it,
and descriptor indices need not follow disk order. Holes and BOOT bytes outside
that region are rejected. Container bounds and non-overlap are prerequisites.
The checker streams each extent and verifies its payload CRC again, including
opaque reserved padding. A 130-sector extent exercises the 64 KiB boundary
without allocating a complete extent in the C/16 segment.

FAT32 support is deliberately limited to the three-sector boot-record
arrangement with FSInfo at relative sector 1. Sector 2 must have its boot
signature. A nonzero backup offset must reserve three non-overlapping sectors
within the reserved area; offset 6 is typical, and offset 10 is tested too.
Zero means no backup copy. Other FSInfo placements are reported as unsupported
arrangements, without implying that every such filesystem is invalid.

Primary and backup VBRs must match byte for byte, as must their continuation
sectors. Both FSInfo copies require the three signatures, zero reserved bytes
and bounded free-count/next-cluster hints; `FFFFFFFFh` means unknown. Their
hints may differ. Microsoft specifies that only the primary FSInfo is kept
current. A stale or differing boot-code copy causes rejection; no preferred
copy or repair is inferred. These rules follow the structures in Microsoft's
[FAT specification 1.03, pages 12 and 21–22](https://www.isdaman.com/alsos/protocols/fats/fatgen103.pdf).

Each READY installation in the selected state record must match the saved
first-sector CRC, including installations not referenced by a selected profile.
Older valid state copies may describe an earlier VBR. Non-READY installations
do not claim a VBR match. This comparison concerns the saved first sector only.

## Native interface and diagnostics

```c
rb_backup_check_boot(result, read, opaque, file_sectors);
```

The reader supplies exactly 512 bytes per successful file-sector read. The
source must remain stable throughout the call. Private scratch and the internal
record context make this interface non-reentrant. The record API remains
available independently with its original scope; an internal successful-open
handoff shares its already checked container, partition scan and selected state.

The 24-byte result contains `status`, `detail`, `record_detail`, descriptor
`kind`/`index`, disk-relative `error_lba`, then five success counters:
`volumes`, `fat16`, `fat32`, `reserved_sectors`, `ready_matches`. Every failure
clears all five counters. Successful diagnostics are all zero. Counts are
published only after all volumes pass, so a later logical-volume failure cannot
leave an earlier primary volume appearing approved.

| Status | Meaning | Detail |
| --- | --- | --- |
| `0000` | Saved FAT boot areas consistent | Zero |
| `0001` | Earlier record/container layer failed | Record status; nested detail in `record_detail` |
| `0002` | Boot payload read failed | Zero; exact disk LBA and descriptor |
| `0003` | Reread extent CRC changed | Zero; extent start LBA and descriptor |
| `0004` | Volume-header check failed or unsupported | Existing `RB_VOLUME_*` code |
| `0005` | Reserved-area coverage failed | `1` hole, `2` extent outside reserved area |
| `0006` | Unsupported FAT32 boot-region arrangement | Zero |
| `0007` | FSInfo rejected | `1` signatures, `2` reserved bytes, `3` free count, `4` next-cluster hint |
| `0008` | Boot copy/continuation rejected | `1` backup VBR mismatch, `2` backup continuation mismatch, `3` primary continuation signature |
| `0009` | READY VBR CRC mismatch | Zero-based selected installation index |

A coverage hole reports descriptor index `FFFFh` and the first missing LBA.
Semantic errors can be reported before the encompassing extent CRC is complete;
no successful result can bypass that CRC. Reread checks detect changed content
but do not establish atomic acquisition or cryptographic authenticity.

## Evidence and remaining work

Six added host tests verify literal structures, valid outer/inner checksums in
semantic counterexamples, sparse native-vector transfer, stale FSInfo hints,
fault placement and the non-executable nature of the examples. There are
161 host tests in total. The new native model has 65 scenarios / 325 assertions
per language (`D=0145`, `RB BACKUP BOOT PASS`), including reversed split extents,
FAT16 reserved regions, absent/relocated FAT32 backups, late logical-volume
failure, selected/older READY CRCs and reads/changes beyond 64 KiB.

Native model payloads are 32,072 bytes EN / 32,140 bytes DE; BSS ends at
42,226 / 42,294, below the 57,344 stack guard. Normal rescue payloads remain
8,410 / 8,478 bytes. Compared with the published PR #20 artifacts, 40 of 43
existing artifact digests per language are unchanged; only the three
saved-record model artifacts differ for the internal handoff.

Both languages are built twice. The complete rescue campaign now has 82 boots
and 434 UI states. Previous container, saved-record and diagnostic models remain
covered. Only the saved-record model changes slightly for the internal context
handoff; normal rescue/HDD/ABI implementations are unchanged. The new checker
is linked only into `backup-boot-model`.

`synthetic-boot-areas.rbb` contains internally consistent test metadata, not a
collected disk snapshot. Original-MBR provenance, boot-code/overlay identity,
other filesystem boot formats, FAT/data/file allocation, snapshot collection,
independent live-media/geometry binding, FAT12 import and confirmed targeted
restore remain open. An intact reserved region is not a filesystem or user-data
backup. No additional manual VM test is required for this model increment.
