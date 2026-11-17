# Streaming live payload checksums

The native payload observer extends the existing capture planner with a
complete, sector-by-sector read of every planned live extent. It returns each
extent's ordinary CRC32 only after two complete validated passes agree.
Payload bytes are not retained or exported. The current MBR retains kind 0;
original-MBR provenance and current-MBR approval remain separate work.

The standalone **`backup-payload-model.img`** exercises this API using synthetic
in-memory sectors. The [live F6 view](BackupCapturePlan.md) now uses the same
observer through fresh BIOS discovery and displays each extent's CRC32.
F4/F5 retain their existing actions and read sequences. No new menu key,
disk write, file creation or restoration is introduced.

## Manual check

The test floppy is included under `rescue/` and `rescue-de/` in
`retroboot-rescue-diagnostics` from **BIOS ABI and Rescue**. Both copies are
byte-identical. A local test bundle can provide the same image when hosted
checks are skipped; its README identifies the source revision and image hash.

1. With the BIOS test VM powered off, `backup-payload-model.img` is attached as
   its boot floppy. No HDD or CD is needed. The boot order starts with Floppy.
2. After startup, the expected result is:

   ```text
   I=03F6
   RB BACKUP PAYLOAD PASS
   ```

3. The program halts. No keyboard sequence is needed; shutdown or restart exits
   the test. `!` diagnostics or `RB RESCUE STARTUP ERROR` indicate failure.

`03F6` is the hexadecimal count of 1,014 assertions in 202 scenarios. This is a
different image and marker from `backup-plan-model.img` (`G=02C6`). The latter
continues to check the original planner without the additional payload reads.

On 17 November 2026, the expected `I=03F6` and `RB BACKUP PAYLOAD PASS`
procedure supplied with PR #36 was confirmed. The local bundle identified
source `ea997bff0a53e42afc75857763495a50bd2ed98c`; the exact downloaded revision,
attached drives and VM/BIOS versions were not separately reported. This is
manual evidence for the standalone model, not for the subsequent live F6 UI.

## Contract

[`rb_backup_payload_capture`](../include/backup_payload.h) accepts a fresh
device description and a physical-sector reader. It builds its own plan; it
does not trust or reuse an earlier F6 result. Each pass performs:

1. The planner's complete metadata acquisitions, range/size checks, profile
   references and FAT reserved-area checks.
2. A contiguous read of each live extent in plan order, one sector at a time.
   A running CRC32 covers every byte across the entire extent, including
   reserved-area padding and the trailing CRC fields in config/state records.
3. A closing MBR read, compared exactly with all other MBR observations in that
   pass.

All reads, including the new payload reads, enter the existing ordered
body/tail fingerprints. Both passes must have identical fingerprints and read
counts. Whole-extent CRC equality is insufficient: a record with a changed
body and a recalculated trailing CRC can have the same whole-record CRC.
The separate first-508-byte/final-four-byte chains preserve the tested
distinction. CRCs detect changes probabilistically; they do not authenticate
bytes or provide an atomic snapshot or a later write lease.

Success returns `rb_backup_payloads.plan` and `crc[i]` for `plan.entries[i]`.
Unused entries and checksum slots are zero. Failure clears all plan claims
and all checksum slots, including results from a preceding successful call;
only the existing plan diagnostic fields survive.

Existing planner diagnostic codes retain their meanings. New status
`0x000A` identifies a read failure during the added payload phase: detail is
the extent kind, index is its kind-local index, nested is zero, and error LBA
is the failed physical sector. A changed MBR still returns `0x0006`.

The 1,072-byte result contains the unchanged 908-byte plan and 41 CRC values.
Collection uses one additional 512-byte automatic buffer, after the boot
checker has returned. No complete extent, heap allocation, writer callback
or cross-call cache is needed. Extents over 64 KiB are streamed with 32-bit
sector counters. The existing 1 MiB container estimate is checked before any
payload collection. The required writable result must not overlap inputs;
the planner's stable-source and non-reentrant preconditions still apply.

## Evidence and remaining work

The native model covers FAT16/FAT32, EDD/CHS, 64-bit device capacities,
reserved areas over 64 KiB and the exact 1 MiB estimate. It reuses independent
planner fixtures, with Python/zlib whole-extent CRC oracles. All 39 payload
sectors have separate I/O failures in both passes. Transient EBR, reserved-byte
and resealed record changes are injected only during collection and then
reverted; they must still be rejected. Second-pass semantic failures, failure
clearing, input immutability and result guards are checked.

The successful fixture has exactly 2,266 reads: two passes of 1,094 existing
validation reads plus 39 payload reads. The exact-limit fixture has 10,278
reads; the one-sector-too-large case still stops after 1,060 sizing/metadata
reads. The test runner checks the independent full address trace in the debug
log, the final result on VGA, code/BSS/stack boundaries, unchanged media and
zero disk writes. Four host tests separately check the byte/read oracles and
the whole-record CRC cancellation example.

This API returns observations and checksums, not a serialized backup. Actual
byte emission requires a bounded export protocol with fresh validation and
independent destination verification. Original-MBR sourcing, current-MBR
approval, complete container assembly and targeted restore remain open.
