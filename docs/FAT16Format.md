# FAT16-Testformatierung auf P1

Das Paket enthält zwei dynamisch wachsende VirtualBox-Testplatten und eine
Startdiskette je Sprache. Die Disketten sind für das mitgelieferte Plattenpaar
und dessen erste primäre Partition freigegeben.

1. Bei ausgeschalteter BIOS-VM die entpackte `FAT16-Ziel.vdi` am primären
   IDE-Master (Port 0, Gerät 0) und `FAT16-Sicherung.vdi` am sekundären
   IDE-Master (Port 1, Gerät 0) anschließen. Für beide Platten die
   mitgelieferten VDIs mit ihren ursprünglichen Medien-UUIDs verwenden.
2. Von `Deutsch/fat16-format.img` in A: starten. Für P1 erscheinen
   **0 von 4** geänderten Sektoren. **F**, dann **1** legt ein leeres
   FAT16-Dateisystem auf dem Ziel an. Erwartete Meldung: `RB FAT16 FORMAT PASS`.
3. Die VM ausschalten und erneut von derselben Diskette starten. Die Anzeige
   meldet **4 von 4** und `RB FAT16 VERIFIED`. **Esc** beendet die Prüfung.
4. Für die Rückprobe **R**, dann **1** wählen. Nach `RB FAT16 RESTORE PASS`
   zeigt der nächste Diskettenstart wieder **0 von 4**. Die Sicherungsplatte
   dient bei allen Schritten ausschließlich als Lesequelle.

**Was auf P1 passiert.** LBA 63 bis 481 enthalten die 419 Metadatensektoren.
Zwei FAT-Anfangssektoren werden initialisiert, ein belegter Testsektor wird
geleert und der Bootsektor wird zuletzt geschrieben. Das FAT16 hat 49.191
Datencluster zu je 32 KiB und ein leeres Stammverzeichnis. Der Datenbereich
beginnt bei LBA 482. Die Formatierung installiert kein Betriebssystem.

## VirtualBox test in English

Attach `FAT16-Ziel.vdi` to primary IDE master (port 0, device 0) and
`FAT16-Sicherung.vdi` to secondary IDE master (port 1, device 0) while
the BIOS VM is off. Use the original VDI media UUIDs. Boot
`English/fat16-format.img`. On the original pair the diskette shows P1
and 0 of 4 changed sectors. Press **F**, then **1**. After
`RB FAT16 FORMAT PASS`, power off and boot the same diskette again.
The cold check reports `RB FAT16 VERIFIED` and 4 of 4 changed sectors.
Press **R**, then **1** to restore the original metadata. The diskette
reports `RB FAT16 RESTORE PASS`. Another cold boot shows 0 of 4.

## Write and recovery contract

The floppy binds one FAT16 primary, the two ATA identities and capacities,
the BIOS geometry, the complete MBR and EBRs, and the contents of the
original metadata range. The backup's original VBR must be zero. The CRCs
detect accidental changes. The caller assumes exclusive access to both
drives. Pressing Esc or entering a different slot at the confirmation cancels.

| Publication order | Target LBA | Change |
| ---: | ---: | --- |
| 1 | 64 | Initialize the first FAT |
| 2 | 72 | Clear the fixture marker in the first FAT |
| 3 | 257 | Initialize the second FAT |
| 4 | 63 | Publish the FAT16 boot sector |

Each changed sector is flushed and read back. A cold scan compares all 419
metadata sectors. An uninterrupted prefix of completed writes can be restored
in reverse order after an interruption, including one during rollback. A
torn sector, a changed backup or unrecognized filesystem metadata blocks
the operation. This restores the enrolled metadata of this test volume.
The partition table, file data area and other volumes stay outside the write
range. Later filesystem activity may change those metadata and prevent rollback.
The [FAT32 P2 kit](FAT32Format.md) uses separate media. The
[FreeDOS guest test](DOSGuestTest.md) verifies file I/O on both filesystems.
