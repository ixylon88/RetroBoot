# Fresh live sources for provisional output

The bounded source adapter connects the live payload observer to the stream
assembler. The normal rescue program uses it for the read-only F7 dry run.
The standalone `backup-live-model.img` also exercises callback and format
edge cases. Both implement part of [#42](https://github.com/ixylon88/RetroBoot/issues/42).

## F7 in normal rescue

F7 opens and validates `RBBACKUP.RBB` on the rescue boot medium. The file
supplies the claims and two explicit MBR roles. A fresh BIOS discovery of
drive `0x80` establishes the route and capacity for physical reads.
The live observer independently locates every other extent. The sink compares
all 512 bytes of each generated sector with the corresponding file sector.

After the final comparison the live core repeats its full HDD capture. The
rescue caller then probes the BIOS again and compares drive number, EDD/CHS
route, heads, sectors per track and both capacity words. It revalidates the
entire saved file and compares the ordered file fingerprints and read count.
Only then does the verified-sector counter become visible. Every failure
returns zero verified sectors. Enter repeats from the beginning. Esc clears
the display. The operation issues only reads. MBR provenance and approval
are tracked in #43, external persistence and readback in #45.

### Manual floppy check

The **BIOS ABI and Rescue** workflow publishes the following synthetic media in
`retroboot-rescue-diagnostics`, under `rescue/` and `rescue-de/`. The normal
rescue executable is identical on all floppies of a given language.

1. In a BIOS test VM, attach `retroboot-rescue-target-hdd.img` as the first
   HDD using the [VirtualBox conversion instructions](BackupCapturePlan.md#manual-virtualbox-check).
   Attach `retroboot-rescue-stream.img` as floppy A: and boot from it.
2. Press **F7**. The result is green with **45 verified sectors**.
3. Exchange A: for `retroboot-rescue-stream-resealed.img` and press **Enter**.
   The saved configuration generations differ. Both copies have valid record
   CRCs and the whole-sector CRCs still agree with the originals. The byte
   comparison rejects sector 41. The screen shows **0** verified sectors.
4. Restore the first floppy and press **Enter**. All **45** sectors pass again.

On 18 November 2026 the maintainer confirmed this German VirtualBox test
with 45, 0 and 45 verified sectors in that order.

| Result | Status / detail / subcode | Verified sectors |
| --- | --- | ---: |
| Intact EDD fixture | `0x0000 / 0x0000 / 0x0000` | 45 |
| Resealed configuration mismatch | `0x0006 / 0x0006 / 0x0006` | 0 |
| Standard floppy with no reference | `0x0001 / 0x0005 / 0x0000` | 0 |
| Valid reference, no HDD | `0x0003 / 0x0001 / 0x0000` | 0 |
| Changed device on closing probe | `0x0005 / 0x0001 / 0x0000` | 0 |
| Failed closing BIOS parameters | `0x0007 / 0x0002 / 0x0000` | 0 |

### Memory and BIOS evidence

| Normal build | Program bytes | BSS bytes | Static space below stack guard |
| --- | ---: | ---: | ---: |
| EN | 38,472 | 16,760 | 2,112 |
| DE | 38,798 | 16,760 | 1,786 |

The 1,536-byte minimum static reserve applies to both images. The 1,072-byte
capture map lives on the guarded 8 KiB stack for the duration of a call.
The QEMU runner measures the untouched portion above the guard from the
loader's prefilled bytes. The local 486/SeaBIOS campaign measured a minimum
of 3,806 untouched bytes in each language. The [first hosted F7 run](https://github.com/ixylon88/RetroBoot/actions/runs/44203863188)
measured 3,766 bytes in EN and 3,806 in DE. These are observations from those
runs. Each later run records its own stack watermark with the firmware and
emulator hashes in `stream-results.json`.

The runner checks BIOS and floppy events in order, every physical HDD LBA,
VGA results, memory guards, medium hashes and attempted writes. EDD and CHS
each perform 4,608 HDD reads for the intact fixture. The late BIOS tests reach
all 45 sector comparisons and both complete HDD captures before injecting a
changed capacity or failed parameter query. Both revoke the entire result.
A separate final-file fault invalidates the reference after the closing probe.

## Contract and source roles

[`rb_backup_live_stream`](../include/backup_live.h) takes explicit container
metadata, exact file-sector count, a freshly discovered device description,
a physical-sector reader, an explicit MBR-source callback and a provisional
sink. No prior F6 result or reusable source map is accepted or returned.

| Stage | Checks | Output |
| --- | --- | --- |
| Framing | Existing identity/count/range/order/size rules | None; no callback |
| Initial capture | Two complete semantic and payload acquisitions | None |
| Binding | Capacity, BIOS route/geometry, disk/media IDs, layout and exact non-MBR extents/CRCs | None |
| Stream | Existing preflight and emission passes with CRCs and ordered fingerprints | Provisional sectors |
| Closing capture | Repeat full capture/binding; compare all ordered acquisition bytes, addresses and read counts | Final success or discard |

Every physical stream address comes from the freshly built live plan. The
supplied descriptors must match kind, kind-local index, LBA, sector count,
owner range and CRC exactly. A framing-valid invented address is rejected
before any stream-source or sink callback. Offsets are bounded again when
resolving the stream's role/index/offset requests. Extents above 64 KiB and
the existing 1 MiB container limit retain 32-bit sector arithmetic.

The plan's current MBR has kind 0 and is excluded from this mapping. Both
`ORIGINAL` and `APPROVED` are resolved through the explicit MBR callback, with
their own kind, index 0 and offset 0. The current live sector 0 is never a
fallback for either role. The adapter does not establish either supplied
MBR's provenance, approval or saved-content semantics. The explicit MBR
payloads may differ from the current observation; later provenance and
saved-content checks must establish whether a complete container is usable.
The separate [MBR provenance model](MbrProvenance.md) specifies how first
installation and later explicit approvals supply evidence for these roles.

The caller must provide fresh BIOS discovery, stable sources, immutable inputs
and independent source/sink contexts. The call is synchronous and non-reentrant.
It uses one 1,072-byte automatic capture result plus bounded callback and
fingerprint state. The static callback context is cleared before return. The existing stream uses one
512-byte automatic buffer. No complete payload is retained in guest memory.

**Every output sector remains provisional until the outer function succeeds.**
Even after the final sink call, closing I/O, semantic or changed-observation
failures revoke the sector-count claim. Any failure requires discarding all
output. There is no rollback, commit callback, file creation or disk writer.
Success is neither destination durability nor permission to publish or restore.

Whole-record CRCs can remain equal after a record body changes and its trailing
CRC is recalculated. The closing capture therefore compares two ordered
body/tail chains over all successful physical validation reads, as well as the
read count. The inner stream keeps its separate two-pass fingerprints.
These checks do not authenticate data or create an atomic snapshot. Coordinated
transient changes between observations and CRC collisions remain possible;
stable sources are a precondition, not a lock acquired by this API.

## Diagnostics

The return value equals `result.status`. Every failure clears
`result.stream.sectors`; success reports the exact file-sector count.
The result is 32 bytes. A null result returns `PARAMS` without touching output
or calling any callback. Results can be reused after success or failure.

| Status | Meaning | Detail |
| --- | --- | --- |
| `0x0000` | Complete wrapper succeeded | Provisional stream count available |
| `0x0001` | Missing required argument | No I/O |
| `0x0002` | Invalid container framing | Existing backup-format code |
| `0x0003` | Initial or closing capture failed | Separate capture status/detail/nested/index and physical error LBA |
| `0x0004` | Fresh identity mismatch | 1 capacity, 2 route/geometry, 3 disk/media ID, 4 layout/admin range |
| `0x0005` | Fresh extent mismatch | Descriptor index; 0 for count mismatch; observed extent LBA |
| `0x0006` | Stream failed | Stream status and full role/index/file-sector diagnostics |
| `0x0007` | Initial and closing observations differ | No single-sector attribution |

Capture fields are meaningful for `CAPTURE`, inner stream error fields for
`STREAM`. The outer status always governs acceptance, including when the inner
stream completed before a closing failure. The original-MBR source and sink
may also report failure after consuming or copying bytes.

## Native and independent evidence

The synthetic model has **123 scenarios / 615 assertions**. Independent Python
wire oracles supply every emitted byte; sparse disk fixtures avoid a complete
guest disk/container allocation. The original and approved MBR payloads are
deliberately distinct from each other and from live sector 0. They are opaque
test bytes, not evidence of valid MBR provenance or a restorable backup.

Coverage includes EDD/CHS, 64-bit capacity, FAT16/FAT32, payloads above 64 KiB,
the exact 1 MiB limit, stale identities/extents, malformed roles/file offsets,
every non-MBR live read failure in each stream pass, both explicit MBR-source
failures in each pass, sink failures, changed/resealed stream bytes and closing
capture failures after all 45 ordinary-fixture sectors were delivered.
A valid generation change in both closing configuration copies preserves
their whole-record CRCs but must still revoke success. Results and input
guards, input immutability and reuse after success are checked.

The intact fixture has **4,608 physical reads**: 2,266 in each capture and 38
live payload reads in each stream pass. Four additional explicit MBR callback
calls supply the two separate roles; those calls do not read the live HDD.
The runner checks the complete physical-address trace, debug and VGA markers,
program bytes, BSS/stack guards, unchanged media and zero guest writes.

The initial model build uses 40,556 file bytes, 13,504 BSS bytes and 3,284 bytes
of static headroom, with the existing guarded 8 KiB stack. At PR #59 normal
rescue had 1,880 / 1,612 bytes of headroom (EN/DE). The subsequent FAT12 index
raises this to 5,912 / 5,644 bytes. The sizing link with the stream core leaves
578 / 310 bytes above the required reserve before adding the BIOS caller.

Actual local/repeated/hosted results are recorded in the implementation PR.
F7 integrates the same core with real BIOS reads. Durable external output,
independent destination readback and targeted restore remain open.

## Manual model check

The **BIOS ABI and Rescue** workflow publishes the model under `rescue/` and
`rescue-de/` in `retroboot-rescue-diagnostics`; both images are identical.
With the test VM powered off, the image is attached as its boot floppy.
No HDD or CD is needed. Expected terminal output is:

```text
K=0267
RB BACKUP LIVE PASS
```

The model halts after the result. An exclamation-mark diagnostic or
`RB RESCUE STARTUP ERROR` means failure. On 17 November 2026 the maintainer
reported a successful manual VirtualBox test of the supplied PR #59 model.
