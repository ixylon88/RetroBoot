# RetroBoot Installationsplanung

Die Diskette zeigt, welche Partitionen das gewählte Setup auf der mitgelieferten
Testfestplatte sehen soll. Alle Vorschläge bleiben im Arbeitsspeicher. Für
diesen Test genügen eine Diskette und die VDI aus demselben Paket.

1. Bei ausgeschalteter BIOS-Test-VM `Installationsziel.vdi` als primären
   IDE-Master (Port 0, Gerät 0) anschließen. `Deutsch/install-plan.img`
   in Laufwerk A: einlegen und von Diskette starten.
2. **2** für Windows 95 OSR2, dann **2** für P2 wählen. Die Vorschau zeigt
   sechs geänderte Bytes in drei Tabellensektoren. P2 würde die sichtbare,
   aktive Systempartition. P1 und die gemeinsamen Laufwerke L1 und L3
   würden verborgen. Das Verwaltungsvolume L2 ist bereits verborgen.
3. **R** liest die Festplatte erneut. Stimmen beide Beobachtungen überein,
   erscheint `RB INSTALL PLAN VERIFIED`. Danach ist wieder die
   Betriebssystemauswahl aktiv.
4. **1**, dann **2** prüft MS-DOS 6.22 auf P2. Die Diskette erklärt,
   dass dieses Profil FAT16 benötigt. **3**, dann **3** prüft Windows 98 SE
   auf P3. Dort schützt der vorhandene Test-Bootsektor das Ziel. Beide
   Fälle enden mit `RB INSTALL PLAN BLOCKED` und führen zur Auswahl zurück.
5. **1**, dann **1** zeigt den gültigen FAT16-Fall für MS-DOS. Nur L1 und
   L3 müssten verborgen werden. **Esc** verlässt die Vorschau. **Esc** in
   der Betriebssystemauswahl beendet das Programm mit `RB INSTALL PLAN END`.

### Beispiel für Windows 95 OSR2 auf P2

| Eintrag | Tabellen-LBA | Offset im Sektor | Ist → geplant |
| --- | --- | --- | --- |
| P1, Aktivflag | `0x00000000` | `0x01BE` | `0x80 → 0x00` |
| P1, FAT16-Typ | `0x00000000` | `0x01C2` | `0x06 → 0x16` |
| P2, Aktivflag | `0x00000000` | `0x01CE` | `0x00 → 0x80` |
| P2, FAT32-Typ | `0x00000000` | `0x01D2` | `0x1B → 0x0B` |
| L1, FAT16-Typ | `0x009FD38C` | `0x01C2` | `0x06 → 0x16` |
| L3, FAT32-Typ | `0x00B1B895` | `0x01C2` | `0x0B → 0x1B` |

Die Typbytes steuern, welche FAT-Volumes das Setup vorfinden soll. P4 ist
der erweiterte Container. Seine Verkettung bleibt für die Suche nach den
logischen Laufwerken erforderlich. Der Plan gilt für die mitgelieferte
8-GB-Referenzplatte. Ein leerer geprüfter Bootbereich sagt nichts über
weiter hinten gespeicherte Dateien aus. Auf P1 liegen absichtlich Testdaten
neun Sektoren hinter dem Start.

## English

Attach `Installationsziel.vdi` as primary IDE master in a powered-off BIOS
test VM and boot `English/install-plan.img` in A:. Select the operating
system first and the primary partition second. The floppy reads the disk
and keeps its proposed changes in memory.

| Keys | Expected result on the supplied disk |
| --- | --- |
| **2**, **2**, **R** | Windows 95 OSR2 on P2. Six bytes across three partition-table sectors. A fresh disk check reports `RB INSTALL PLAN VERIFIED`. |
| **1**, **2** | MS-DOS 6.22 on FAT32 is refused with `RB INSTALL PLAN BLOCKED`. |
| **3**, **3** | Windows 98 SE on P3 is refused. Its existing test boot sector is reported with its LBA. |
| **1**, **1** | MS-DOS 6.22 on P1. Two logical volume type bytes would change, one in each affected EBR. |
| **Esc** | Return to OS selection. At OS selection, exit with `RB INSTALL PLAN END`. |

The planner checks the disk ID, BIOS geometry and partition layout, reads
the complete MBR and the three EBRs, and inspects the selected FAT16 boot
sector or FAT32 sectors at relative offsets 0, 1, 2, 6, 7 and 8. Any nonzero
byte in these boot sectors protects the target. A repeated review checks
the boot area again and compares both observations of the full table sectors
and geometry. File data elsewhere on the partition is outside this review.

On Linux, `make toolchain` followed by `make install-plan-test` builds both
languages and tests the packaged media in QEMU. The campaign checks the VGA
output, the exact disk reads and zero writes. Applying the plan and starting
original setup media are subsequent parts of the
[installation workflow](https://github.com/ixylon88/RetroBoot/issues/51).
