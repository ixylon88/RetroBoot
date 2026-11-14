# Saved partition and record consistency

An intact container can still combine records from different media or omit an
EBR referenced by its saved partition table. `rb_backup_check_records` adds a
native C/16 consistency check after the [container validator](ExternalBackup.md).
It reuses the existing partition scanner and configuration/state decoders and
pair selectors. No second implementation of those formats is introduced.

PR #20 introduced this check in a separate model payload. The subsequent
[F4 file path](RescueBackupFile.md) also uses it in the normal rescue program.
The Python inspector still reports container integrity only; it does not
perform the native record check.

## Accepted evidence

The checker validates the complete container first, then interprets the
**approved-MBR view** through a file-backed sector callback. Disk LBA 0 maps
only to the approved-MBR descriptor. EBR requests map only to EBR descriptors;
there is no fallback to a live disk or another kind of stored extent.

| Check | Requirement |
| --- | --- |
| Approved MBR / EBR chain | Existing bounded scanner succeeds against the container's disk ID and capacity |
| Management volume | `RBM1` marker and pointer agree with the header; a hidden logical FAT16 partition has exactly the claimed start and length |
| Canonical layout | Recomputed `RBL1` CRC agrees with the header; visibility/active flags retain the existing normalization rules |
| EBR coverage | Descriptors correspond exactly to the referenced chain, including order; missing and unreferenced EBRs are rejected |
| Boot-area owners | Every owner matches an actual nonempty data partition; the extended container is not a data volume |
| Volume starts | A boot-area descriptor begins at each data volume's start sector |
| Configuration / state | Both A/B copies decode successfully and bind to the saved disk, layout and management volume |
| Pair selection | Highest valid generation is selected independently in each family; equal generations require identical bytes |
| Media identity | All four records carry the container's media ID; configuration version 2 is required |
| Installation references | Every nonzero selected profile installation ID resolves to a selected state entry with matching slot, type, kind, start and length |
| Approved profile | Its matching installation record is in the existing `READY` phase |

Both copies must pass, including an older copy that is not selected. A/B
generations do not need to equal each other or the container generation.
The check does not establish a durable update history. Several profiles may
refer to one matching installation. An unapproved profile with no installation
ID does not assert an installation; empty profile/state lists are permitted.

During semantic reads, each complete MBR, EBR or configuration/state sector is
checked again against its descriptor's payload CRC. A read failure or changed
sector aborts immediately. This catches changes in MBR bytes outside `RBL1`
as well as changes in fields with their own internal checksum.

## Remaining boundary

Success means consistency of the listed saved records. It does not prove that
the container is a complete, recoverable snapshot or belongs to a live target.
In particular:

- The original-MBR role remains opaque preserved data. Its original identity,
  provenance, historical partition layout and suitability for a later targeted
  restore are not inferred from the approved view.
- Boot-area ownership and coverage of each start sector are checked, but boot
  bytes are not interpreted by this API. The subsequent
  [FAT boot-area layer](BackupBootAreas.md) adds BPB, reserved-area/copy and
  selected READY VBR CRC checks. Other filesystem formats remain open.
- The `RBM1` marker is not authentication or a complete boot-code/overlay check.
  Record descriptor LBAs are not verified file allocation or ownership evidence.
- CRCs are not cryptographic authentication. Collection, stable snapshot
  acquisition, independent live-media/geometry binding,
  explicit restore selection/confirmation and interruption handling remain open.

The model deliberately accepts a record-consistent fixture with zero-filled
original-MBR and boot-area payloads. This positive case documents the boundary:
the result must not be presented as a usable recovery backup or write grant.
The frozen specification v0.2 and its full recovery acceptance criteria remain
unchanged. Transaction writes remain disabled.

## API and diagnostics

`rb_backup_check_records(result, read, opaque, file_sectors)` uses the existing
file-relative 512-byte callback. The caller supplies the exact length and keeps
the source stable for the entire call. The function has private scratch state
and is non-reentrant. The reread checks are not an atomic-snapshot guarantee or
a lease to use the same file later without revalidation.

On success, the result contains partition/EBR/boot-extent counts and selected
configuration/state source indices and generations. Every failure clears those
counts and generations and resets both source indices to `FFFFh`. Only
diagnostics remain: status, detail, descriptor kind/index where applicable and
the saved disk LBA associated with the error. These LBAs are descriptive;
callbacks continue to receive file-relative sector addresses.

| Status, hex | Meaning / detail |
| --- | --- |
| `0000` | Saved partition and record checks passed within this boundary |
| `0001` | Initial container validation failed; detail is a container status |
| `0002` | A semantic reread failed |
| `0003` | A reread sector no longer matches its container payload CRC |
| `0004` | Saved partition scan failed; detail is an existing scan status |
| `0005` | Coverage failure: detail 1 missing EBR, 2 EBR set/order, 3 invalid boot owner, 4 missing volume start |
| `0006` | Management binding: detail 0 marker/pointer, 1 missing matching hidden logical FAT16 extent |
| `0007` | Configuration copies failed; detail uses existing configuration status codes |
| `0008` | Installation-state copies failed; detail uses existing configuration status codes |
| `0009` | Identity: detail 1 legacy configuration, 2 record media ID, 3 header layout CRC |
| `000A` | Unresolved or incompatible installation reference; detail is the zero-based profile index |

For an initial container failure, kind/index/error LBA are zero because no
semantic record has been selected. Missing EBR or volume-start coverage uses
index `FFFFh` when no corresponding descriptor exists. Pair conflicts identify
the A role for that family. Installation-reference errors report the profile's
target start LBA. No derived partial success is returned.

## Verification and builds

The existing commands include the new model:

```sh
make check
make rescue-test RB_LANGUAGE=en
make rescue-test RB_LANGUAGE=de
```

This increment established 155 host tests, including six tests that check literal partition
and record fields, golden layout CRCs, valid outer/inner checksums on semantic
counterexamples, generation expectations and exact host-to-native vector
transfer. The native model executes 74 scenarios / 296 assertions per language
(`C=0128`, `RB BACKUP RECORDS PASS`). Coverage includes:

- One/two-EBR layouts, reordered or unreferenced EBRs, missing volume starts,
  invalid owners, MBR/EBR corruption and inconsistent header claims.
- Independently newer A/B copies, equal-generation conflicts, invalid copies,
  legacy records and foreign media IDs in either selected or older copies.
- Resolved/unresolved installation IDs, approved-but-not-ready states, empty
  records and several profiles referring to one installation.
- Injected I/O failures during the initial container pass and at each semantic
  reread, plus changes at each reread. Bounds, guards, exact positive read
  sequences, failure-stop counts, diagnostics and cleared results are checked.

This increment established 40 boots and 217 UI states per language.
The boot-area increment reached 82 boots / 434 states; the subsequent F4
file path brings the current total to 138 boots / 812 states. The earlier 216 container assertions and 28
rescue assertions remain. BIOS write-attempt tracing, unchanged-image checks
and absence of HDD/block writes remain part of the campaign.

`synthetic-records.rbb` is published with the rescue CI evidence. It contains
encoded test records, not a snapshot collected from a real disk. Native parser
dependencies are now also used by the [F4 file check](RescueBackupFile.md).
Neither the checker nor its model invokes the existing HDD record loader.
HDD and ABI implementations retain their previous behavior.
