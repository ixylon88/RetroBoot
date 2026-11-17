# Native backup metadata encoding

The C/16 encoder produces the five metadata sectors of the existing version-1
[external container](ExternalBackup.md): its header and four descriptor-table
sectors. It is a preparation for collecting a backup, not a complete collector.
Only the standalone test model links the encoder. Rescue F4/F5/F6 and the HDD
program have no new key or write action.

## Manual VirtualBox check

The successful **[BIOS ABI and Rescue](https://github.com/ixylon88/RetroBoot/actions/workflows/abi-probe.yml)**
run for this revision publishes **`retroboot-rescue-diagnostics`**. The test
floppy is **`rescue/backup-encode-model.img`**, also present under `rescue-de/`.
It is not part of the separate `retroboot-hdd-bios` artifact.

1. In a powered-off BIOS test VM, attach `backup-encode-model.img` as a floppy.
   No HDD or CD is needed; boot order starts with Floppy.
2. Boot and expect exactly these result lines below any BIOS startup text:

   ```text
   H=04F2
   RB BACKUP ENCODE PASS
   ```

3. The program stops after the result. No key sequence is required; a restart
   or VM shutdown exits the test. Exclamation-mark diagnostics or
   `RB RESCUE STARTUP ERROR` indicate failure.

`04F2` is the hexadecimal count of **1,266 assertions in 64 scenarios**.
Both language builds use the same stable ASCII marker. The model uses only
in-memory synthetic bytes; it never scans an attached HDD or creates a file.
On 15 November 2026, the expected `H=04F2` and `RB BACKUP ENCODE PASS`
result was reported as matching. The exact downloaded revision, language
folder, attached drives and VM/BIOS versions were not separately reported.

## Interface and boundaries

[`rb_backup_encode_metadata`](../include/backup_encode.h) takes an explicit
`rb_backup`, an exact file-sector count, a metadata-sector number and a
512-byte output buffer. Sector 0 produces the header; sectors 1–4 produce the
table. Requests may be repeated or made in any order. Every call checks the
entire identity/framing claim and descriptor layout before emitting bytes.

The caller supplies both MBR roles, all LBAs, file offsets, payload CRCs,
identity and geometry. The encoder does not infer missing fields, choose a
generation, collect source bytes or promote the preliminary F6 current-MBR
kind 0 to either original or approved MBR. That kind is rejected. Required
roles, canonical order, ownership, nonoverlap, count and 1 MiB bounds follow
the existing container rules.

All integers are explicitly encoded little-endian. Reserved bytes and unused
descriptor slots are zero, regardless of unused native-array contents. The
encoder computes table and header CRCs. Supplied **payload CRCs remain claims**:
the model deliberately demonstrates accepted framing with an incorrect payload
CRC, followed by rejection by the complete container reader.

Failures return existing `RB_BACKUP_*` codes and clear all 512 output bytes.
Null input, null output or a sector outside 0–4 returns `RB_BACKUP_FORMAT`;
a null output cannot be cleared. Output must not overlap input. Input remains
unchanged, and no pointer, cache or static scratch survives a call. Header
construction reuses the output sector for each table page before encoding the
header; it needs no second sector buffer. There is no I/O callback or writer.

The private [format helpers](../core/backup_format.c) share the existing
identity, descriptor and CRC rules with the reader. Extraction preserves the
reader's validation order and read boundaries; malformed wire-only fields,
table/header CRCs and all payload reads remain the reader's responsibility.

## Evidence and remaining work

Independent Python wire images provide exact byte oracles, including
asymmetric 32-/64-bit fields, EDD/CHS, 7/15/16/17/31/32/33/42 descriptors,
reserved zeros, boot payloads over 64 KiB and the exact 1 MiB file limit.
Every scenario requests sectors in order 4,0,3,1,2,0 from poisoned output.
The native model checks complete output bytes, input immutability, buffer
guards, rejection cleanup and full-reader round trips. Invalid parameters
are also exercised immediately after successful output.

Three host tests verify oracle rejection categories, literal wire offsets,
boundary coverage and the distinction between metadata and payload integrity.
The unchanged reader/model and F4/F5/F6 campaigns run alongside the new model
in both languages. The model's result is checked on VGA as well as in the log;
code/BSS bounds, stack guard, unchanged media and zero writes remain checked.
Actual local, CI and published-artifact results are recorded in the PR.

The separate [payload observer](BackupPayloads.md) now obtains per-extent CRCs
from two freshly validated live passes. It does not connect the encoder to an
export destination or promote the current-MBR kind to a stored MBR role.

The separate [stream assembler](BackupStreaming.md) now joins encoded metadata
and explicit payload sources with two-pass checks and provisional output.
It does not connect the live observer or resolve the MBR roles.

Complete live source capture and byte emission, original-MBR provenance,
current-MBR approval, stable export, independently verified destination and
targeted restore remain separate work. Valid metadata sectors alone do not
establish any of these properties.
