# F8: read-only transaction-journal diagnosis

Recovery now reads the two preallocated `RBTXN.A/B` files after a complete
management-volume allocation check. It validates independent media identity,
selects a consistent journal pair and compares its full MBR snapshots with the
current MBR. This is an observation, not repair, write permission or OS-start
authorization. The binary record and pairing rules remain in
[TransactionJournal.md](TransactionJournal.md).

## Manual check

The `retroboot-hdd-bios` CI artifact contains English media under `hdd/` and
German media under `hdd-de/`. Either `retroboot-hdd.img` or
`retroboot-handoff.img` can exercise this check in an empty BIOS VM. A new raw
image requires a new VirtualBox conversion; an existing VDI retains its old
contents. This increment changes both images and expands the management root
from six to eight files.

1. Boot a current image, press **F8**, then **Enter**.
2. On the ordinary EDD route, expect the green baseline message:
   **Empty journal: current MBR matches the baseline.** / **Leeres Journal:
   Aktueller MBR entspricht dem Ausgangsstand.**
3. Expected hexadecimal fields are:

   | Field | Expected |
   | --- | --- |
   | Files / detail | `0000 / 0000` |
   | Journal / copy A / copy B | `0000 / 0000 / 0000` |
   | Sequence | `00000001` |
   | Phase / selected copy | `0000 / A` |
   | MBR CRC32 old / new | Equal values |
   | Changed slots | `00` |

4. **Enter** repeats the complete read and should show the same result.
   **F4/F9** are inert on the journal page. **F8** returns to the Recovery
   landing page; **Esc** returns to the main menu. Selecting Recovery with
   the menu arrows and Enter opens the landing page first.
5. **F10** now lists eight files, including `RBTXN.A` and `RBTXN.B`, each
   `00000600` bytes. The allocation status remains `0000 / 0000`.

The released samples contain an EDD baseline bound to their exact capacity.
A forced CHS boot intentionally reports journal `0008 / 0005 / 0005` because
its route and reachable geometry differ. It must not silently reinterpret or
rewrite that baseline. Dedicated automated fixtures bind matching records to
CHS as well as EDD. On the defined QEMU/SeaBIOS test device, explicit 260/16/63
geometry yields 259 reachable cylinders, or 261,072 sectors. This is a fixture
parameter, not a runtime assumption about other BIOS implementations.

## Read boundary and identity

Each Enter starts from zeroed diagnostic state and fresh reads:

1. The [eight-file audit](AdminAllocation.md) checks the MBR/EBR layout,
   management VBR, root, every file chain, both complete FATs and allocation
   ownership. It supplies the validated scan and six exact journal-sector LBAs.
   A chain may be fragmented. No cached map from a previous F10 is used.
2. Exactly one sector from each `RBCFG.A/B` and `RBSTATE.A/B` is read through
   that allocation. Both copies of each family must decode successfully.
   Configuration version 2 and the same nonzero media identity in all four
   records are required. A valid fallback alone cannot establish this identity.
   Installation readiness is a separate F6 concern and is not required merely
   to inspect a journal.
3. Exactly three sectors per journal copy are read, following the audited map.
   A partial read invalidates that entire copy; the other copy is still checked
   for diagnostic purposes. No fourth padding sector or target VBR is read.
4. The current MBR is read again and compared byte-for-byte with the MBR
   captured by the allocation scan. A change or read failure clears selection.
5. The existing journal model checks record CRCs, layout, identity, BIOS route,
   capacity/geometry, protected bytes, pair continuity and current-MBR relation.

The code has a sector-reader callback and no writer. Private synchronous
scratch is non-reentrant and cleared before and after every invocation.
Neither payload buffers nor an allocation map remain available as a later
write lease. The observation is not atomic against an external actor changing
other metadata between reads; it conveys no durability or authenticity proof.

## Displayed results

A valid pair distinguishes an empty baseline, prepared/old, prepared/new,
committed/new and diverged MBR. Prepared results and divergence are yellow.
A green completion means matching record evidence and current bytes, not proof
of a durable historical write. No result initiates rollback, roll-forward,
repair, countdown or a target boot.

The first code line describes loading; the second uses the existing journal
status vocabulary. The detail namespace depends on the load status:

| Load code, hex | Meaning and detail |
| --- | --- |
| `0000` | Reads completed; inspect the separate journal status/observation |
| `0001` | Allocation blocked; detail is the F10 status |
| `0002` | Configuration invalid/degraded; detail is an `RB_CONFIG_*` status |
| `0003` | Installation-state invalid/degraded; same detail vocabulary |
| `0004` | Identity mismatch; detail `1` configuration version/media pair, `2` configuration/state media binding |
| `0005` | Sector read failed; detail is file ID `3`–`8`, or `0` for the final MBR read |
| `0006` | MBR changed during observation |

The displayed LBA identifies a failing sector when one exists; zero also
serves as the unspecified location for a cross-record identity/pair conflict.
A journal payload read failure leaves the unreadable copy marked `missing`
while the load line supplies its I/O reason and LBA. Failure pages have no
selected sequence, phase, snapshot CRCs or change mask from a previous success.

## Evidence and remaining work

`make journal-test` runs the English campaign; `RB_LANGUAGE=de` selects German.
Already-built images can be tested with `python3 tools/test_journal.py`, using
optional `--language`, `--qemu`, `--bios` and exact `--case` filters. Reports,
VGA/RAM/low-memory dumps, screenshots, BIOS logs and disk-read/write traces are
published under `journal/` and `journal-de/` alongside the release media.

Each language has 45 campaigns and 495 keyboard/VGA states. Twenty scenarios
have independently bound EDD and CHS records: all observations, corrupt copies,
pair conflicts, identity/geometry/protected-byte failures, missing/short/shared
files, configuration/state defects and real persistent/transient sector errors.
Both released images also run through EDD and CHS; one handoff image runs
without the instrumentation ROM. Every campaign performs three fresh reads,
checks cleared BSS/scratch, stack guard and unchanged handoff memory, compares
exact sector sequences, preserves the source image and requires zero writes.

The native reader model has 42 assertions (`D=002A`, `RB JOURNAL IO PASS`),
including fragmented three-sector maps, every payload-sector read failure,
identity defects, a changed/failing final MBR read and success-to-failure cleanup.
The allocation model has 80 assertions (`A=0050`), including the 122-cluster
maximum and fragmented journal-sector maps. The pure journal model has
144 assertions (`T=0090`), including partial snapshot and discard patterns.
Four host tests check fixture boundaries,
route parameters, read evidence and failure-page hygiene.

F8 diagnoses the journal. The independent rescue floppy and the normal
HDD menu have separate entry points for confirmed changes.
[HDD switch and external recovery](TransactionJournal.md#confirmed-hdd-switch)
