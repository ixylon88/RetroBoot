# Independent verification of completed backup streams

The [completion check](../include/backup_verify.h) stages a complete version-1
metadata backup from the live-source assembler. It reopens the actual destination,
checks its contents with the existing saved-data readers and compares every
staged byte with a fresh serialization. The fixture uses RAM for the destination.
The [dedicated IDE recovery disk](BackupDisk.md) uses the same completion check
for durable output under #45. Targeted restore is tracked in #46.

## Acceptance sequence

1. The source adapter identifies the same enrolled disk it will read. Its
   identity and capacity must match the MBR enrollment. The [independent
   witness and carrier](MbrRestart.md) must agree on the original and a
   current approved revision. These two retained sectors supply the separate
   MBR roles. The live disk supplies the EBRs, FAT boot areas, configuration
   and installation state.
2. The [live-source assembler](BackupLiveSources.md) writes the provisional
   destination and finishes its closing source checks. Failure at this point
   discards the entire candidate, even if the sink already received every byte.
3. The destination adapter reopens the stored candidate for reading and
   reports its actual byte length. The independent [container](ExternalBackup.md),
   [record](BackupRecords.md) and [FAT boot-area](BackupBootAreas.md) readers
   check that complete candidate, including extents, both saved MBR roles,
   the approved partition view and its configuration/state and boot sectors.
4. The source is identified again. A second read-only open checks the actual
   length and a fresh assembly compares every destination sector byte for byte.
   This comparison also checks both MBRs against the exact witnessed bytes.
   The ordered fingerprints from writing and reading must agree. The carrier,
   witness and physical source identity are rechecked before the result can
   expose the verified sector count and approved revision.

Every failure leaves both result fields zero. The destination adapter supplies
exclusive access, fresh provisional storage per attempt and a stable read-only
view when reopened. It must discard a failed candidate. The caller supplies
the independently enrolled physical source, witness and carrier endpoints.
The check never publishes a file or grants permission to write to the source.
Ordered CRC fingerprints detect changes within this contract and are not
cryptographic authentication.

## Bootable test

The rescue diagnostics contain `backup-verify-model.img` in `rescue-de/` and
`rescue/`. Booting either image in a BIOS test VM runs the complete check.
The model provides its own independent synthetic disk, witness and carrier
and stages the real output in conventional RAM. No HDD attachment, diskette
exchange or keypress is needed. The German result is:

```text
Sicherungstest im Arbeitsspeicher
Geprüfte Sektoren 45
Beschädigter letzter Sektor abgelehnt
Ausgetauschter freigegebener MBR abgelehnt
RB BACKUP VERIFY PASS
```

The 27 [guest cases](../tests/backup/verify.c) exercise truncation, trailing
bytes and sectors, overlapping disk ranges, a malformed saved state and
a damaged FAT32 FSInfo sector with intact outer checksums. The campaign substitutes
different original, approved and configuration sectors that retain the original
whole-sector CRC32. Other cases fail the final write or read, change the
source or witness during verification, or replace data on the second open.
A failed attempt is followed by successful reuse of the same result object.

The guest stages 45-sector and 143-sector files. The second crosses the 64 KiB
boundary. After the run, the host extracts both actual files from guest RAM
and compares every byte with independently encoded Python files. The GitHub
diagnostics retain both `.rbb` files, the localized console text, and the
per-language memory maps. The English payload occupies 41,220 bytes and the German
payload 41,250 bytes. The builds retain 2,514 and 2,484 bytes of static headroom
respectively before the fixed, guarded 8 KiB stack. The separate fixture
buffers use 23,040 and 73,216 bytes of conventional memory.
