# Provisional container output

The native stream assembler joins the existing five metadata sectors and
explicit payload sources into a sequential version-1 container. This is a
bounded output protocol, not a live backup command. It is linked into
**`backup-stream-model.img`** and the separate
[live-source model](BackupLiveSources.md); normal rescue F4/F5/F6 and HDD code
are unchanged.

## Manual VirtualBox check

The **BIOS ABI and Rescue** workflow publishes the image under `rescue/` and
`rescue-de/` in **`retroboot-rescue-diagnostics`**. Both copies are identical.
The separate `retroboot-hdd-bios` artifact does not contain this test floppy.

1. With the BIOS test VM powered off, `backup-stream-model.img` is attached as
   its boot floppy. No HDD or CD is needed; boot order starts with Floppy.
2. The expected terminal result is:

   ```text
   J=03E3
   RB BACKUP STREAM PASS
   ```

3. The model halts. Shutdown or restart exits; no key sequence is required.
   An exclamation-mark diagnostic or `RB RESCUE STARTUP ERROR` means failure.

`03E3` is the hexadecimal count of 995 assertions in 199 scenarios. The model
uses synthetic memory sources and consumes output in memory without writing
a disk or creating a file. It does not need either live target HDD fixture.

## Manual evidence

On 17 November 2026, the supplied VirtualBox procedure was reported as
confirmed, including the expected `J=03E3` and `RB BACKUP STREAM PASS` result.
The supplied test bundle was labelled for PR #38's head
`eff84c13235ffc0f43216620720478e661a66610`. A later input audit found that
its local stream image preceded the final compile-time result-size assertion;
it is not byte-identical to that head's hosted build. Both run the same 199
scenarios / 995 assertions. The [build-input investigation](CI.md#rescue-build-inputs)
records the exact distinction. The exact image selected, language folder and
VM/BIOS versions were not independently recorded. The confirmation applies to
the supplied standalone test; it adds no live-source, destination-storage or
restore evidence, nor a manual test of the final hosted image.

## Interface and output lifetime

[`rb_backup_stream`](../include/backup_stream.h) takes an explicit `rb_backup`,
exact file-sector count, source callback, provisional sink callback and their
separate contexts. All existing framing rules are checked before source I/O.
The metadata encoder supplies canonical reserved zeros and header/table CRCs.

The source receives **kind, kind-local index and sector offset**. Both MBR
roles therefore require explicit source resolution; the current disk sector
zero is never automatically used as an original or approved MBR. Supplied
roles, identity and payload CRCs are claims. This layer does not establish
provenance, approval, saved-record semantics or a live-device match.

| Pass | Work | Sink calls |
| --- | --- | --- |
| 1 | Encode metadata; read all payloads; check every complete-extent CRC32 | None |
| 2 | Repeat encoding and payload checks; compare ordered body/tail fingerprints | File sectors `0` through `file_sectors - 1`, once each |

Both fingerprints cover every metadata and payload sector, with its
file-relative address and order. Keeping the first 508 bytes separate from
the final four bytes detects the tested resealed-record changes that preserve
the ordinary whole-record CRC. Collisions remain possible; there is no
authentication or atomic snapshot guarantee.

Callbacks return zero only after consuming or copying all 512 bytes. Sector
pointers are temporary. Metadata and result must not overlap and must not be
modified by callbacks; source and sink must be independent. Metadata must stay
stable throughout the call. One automatic 512-byte scratch buffer and bounded
counters are used; there is no whole-container allocation, static scratch or
retained pointer. Payloads over 64 KiB and the 1 MiB limit use 32-bit offsets.

**All output is provisional until the function returns successfully.** A
read, CRC, fingerprint or sink failure may occur after some or every sector
has already been delivered. The caller must then discard the entire output.
There is no rollback or commit callback. A failing sink may have consumed its
sector before returning an error. Retrying requires a fresh call and a fresh
provisional destination.

Success reports `result.sectors == file_sectors`; any failure clears that
claim, including after an earlier successful call. Success establishes only
the emitted stream within this contract. Durable storage, independent
destination readback and publication remain the destination adapter's work.

| Status | Meaning | Diagnostic location |
| --- | --- | --- |
| `0x0000` | Stream checks passed | No error; sector count available |
| `0x0001` | Missing required argument | No callback called |
| `0x0002` | Invalid metadata framing | Encoder status in `detail`; metadata sector |
| `0x0003` | Source read failed | Kind, index and failed file sector |
| `0x0004` | Complete-extent CRC differs from supplied claim | Kind, index and extent's first file sector |
| `0x0005` | Ordered observations differ between passes | No single-sector attribution |
| `0x0006` | Sink rejected a sector | Failed file sector; kind/index for payloads |

Null result returns `0x0001` without touching any output or calling either
callback. Otherwise the return value equals `result.status`.

## Evidence and remaining integration

Independent Python wire images provide complete byte oracles for EDD/CHS,
asymmetric 64-bit capacity fields, distinct original/approved MBR bytes,
42 descriptors, payloads over 64 KiB and the exact 1 MiB file limit. The native
sink compares every delivered byte, source coordinates and callback order.
Tests cover every ordinary-fixture payload read in both passes, every sink
position including metadata, every extent's CRC failure in either pass,
invalid framing/arguments, final-sector failures at the size limit, input and
result guards, and reuse after success. Two resealed last-sector changes must
fail even after all output was delivered. Three host tests independently
check the wire oracles, failure boundaries and CRC-residue counterexample.

The runner verifies the final marker on VGA and in the debug log, unchanged
program bytes, BSS/stack boundaries, unchanged media and zero guest writes.
Both language builds retain the existing 8 KiB stack and static reserve.
Actual local and hosted results are recorded separately in the PR.

The [live-source adapter](BackupLiveSources.md) now connects the
[payload observer](BackupPayloads.md) and this assembler in a separate native
model. It matches independently acquired live extents, keeps both MBR roles
explicit and revalidates the live source after emission. Fresh BIOS integration,
normal-image memory work, original-MBR provenance, MBR approval, saved semantics,
destination persistence/readback and targeted restore remain separate work.
The [independent completion check](BackupVerification.md) now reopens actual
provisional output and verifies both MBR roles against enrolled history.
The bootable completion fixture stages its files in RAM. Normal rescue still
creates no backup file.
