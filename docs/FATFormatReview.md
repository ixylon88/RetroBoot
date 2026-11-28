# FAT format target review

## VirtualBox-Test auf Deutsch

Das Paket enthält zwei getrennte Testplatten mit gleichem Sektorinhalt und
unterschiedlichen Seriennummern. Die Startdiskette kennt beide Nummern.
Alle Schritte lesen ausschließlich.

1. Bei ausgeschalteter BIOS-VM die Dateien aus dem entpackten ZIP anschließen.
   `Format-Ziel.vdi` gehört an den primären IDE-Master (Port 0, Gerät 0),
   `Format-Sicherung.vdi` an den sekundären IDE-Master (Port 1, Gerät 0).
   `Deutsch/fat-review.img` in Laufwerk A einlegen und von Diskette starten.
2. **1**, dann **Enter** zeigt die gewohnte FAT16-Vorschau. **R** vergleicht
   den geplanten Metadatenbereich mit der Sicherung. Erwartet werden
   **419 verglichene Sektoren, davon einer mit Inhalt**. Dieser liegt neun
   Sektoren hinter dem leeren ersten Sektor der Partition.
3. Erneut **1** drücken. Nach dem zweiten Vergleich erscheint
   **RB FAT REVIEW PASS**. Bei Auswahl einer anderen Platznummer bricht die
   Prüfung ab. **Esc** bricht am Bestätigungsdialog ebenfalls ab.
4. **2**, **Enter**, **R** zeigt für FAT32 **6.190 verglichene Sektoren**.
   Die Bestätigung gilt jeweils nur für den gerade angezeigten Platz.
5. Für die Gegenprobe die VM ausschalten, nur die Sicherungsplatte abkoppeln
   und erneut von Diskette starten. **1**, **Enter**, **R** meldet die fehlende
   Sicherungsplatte. **Esc** in der Partitionsauswahl beendet den Test.

## VirtualBox test in English

Attach `Format-Ziel.vdi` as primary IDE master (port 0, device 0) and
`Format-Sicherung.vdi` as secondary IDE master (port 1, device 0) to the
powered-off BIOS VM. Boot `English/fat-review.img` in drive A. Select a slot
with **1** to **3**, press **Enter** for the default cluster size, then **R**.
The screen shows both serials and the inclusive metadata range. Repeating the
displayed slot number performs a second comparison and ends with
`RB FAT REVIEW PASS`. Esc cancels. A wrong slot number or Enter discards the
review. After removing the backup from the powered-off VM, the next review
reports the missing disk.

| Slot | Layout | First metadata LBA | Last metadata LBA | Compared sectors | Sectors with data |
| --- | --- | ---: | ---: | ---: | ---: |
| P1 | FAT16, 64 sectors/cluster | 63 | 481 | 419 | 1 |
| P2 | FAT32, 8 sectors/cluster | 3,148,740 | 3,154,929 | 6,190 | 0 |
| P3 | FAT32, 8 sectors/cluster | 6,297,480 | 6,305,677 | 8,198 | 1 |

## Scope of the comparison

The floppy holds the model, serial and capacity of each IDE master. For
each pass the guest rechecks the enrollment and both identities before and
after the physical reads. The live BIOS layout, MBR and selected first
sector must agree with the displayed plan. Both IDE masters must supply
the same complete MBR and EBR sectors as the BIOS drive.

The guest compares every byte from the volume start through the end of the
fixed FAT16 root directory or FAT32 root cluster 2. This includes the
reserved area, both FATs and, on FAT32, the primary and backup boot and
FSInfo sectors. A mismatch reports its absolute LBA. Re-entering the slot
repeats the disk and sector checks. The two passes must also produce matching
address-bound fingerprints of the EBRs and the nonzero metadata sectors.
The comparison covers the displayed interval. File data elsewhere on the
volume lies outside it. The package test independently compares both full
VDIs against the original 8 GB raw image.

The review uses one BIOS VM with exclusive access to the IDE pair and
512-byte sectors addressable by LBA28. Identity checks and fingerprints
detect changes during the review. They provide no cryptographic
authentication or atomic snapshot. Every confirmation expires immediately.
The guest has read-only disk routines. Publishing filesystem metadata,
recovering an interrupted format and the T11 guest read/write test remain
open in issue #50.
