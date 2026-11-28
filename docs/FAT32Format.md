# FAT32-Testformatierung auf P2

Das Paket enthält eine deutsche und eine englische Startdiskette sowie zwei
VirtualBox-Testplatten mit eigenen Medien-UUIDs. Die Freigabe gilt für P2 auf
der mitgelieferten Zielplatte.

1. Bei ausgeschalteter BIOS-VM `FAT32-Ziel.vdi` als primären IDE-Master
   (Port 0, Gerät 0) und `FAT32-Sicherung.vdi` als sekundären IDE-Master
   (Port 1, Gerät 0) anschließen. Die VDIs mit ihren gelieferten UUIDs verwenden.
2. Von `Deutsch/fat32-format.img` starten. P2 zeigt zunächst **0 von 8**.
   **F**, dann **2** erzeugt ein leeres FAT32. Es folgt `RB FAT32 FORMAT PASS`.
3. Nach dem Ausschalten erneut von derselben Diskette starten. Bei **8 von 8**
   erscheint `RB FAT32 VERIFIED`. **R**, dann **2** stellt die Originalsektoren
   wieder her. Nach `RB FAT32 RESTORE PASS` zeigt der nächste Start **0 von 8**.
   **Esc** beendet die Prüfung ohne Schreibzugriff.

Die Diskette vergleicht 6.190 Metadatensektoren mit der Sicherung. Auf der
gelieferten P2 unterscheidet sich das leere FAT32 in acht Sektoren vom Original.
Die beiden FATs vermerken den Stammverzeichnis-Cluster als belegt. Von 392.819
Datenclustern zu je 4 KiB sind damit 392.818 frei. Die Formatierung richtet
ein Dateisystem ein. Eine Betriebssysteminstallation ist ein eigener Schritt.

## VirtualBox test in English

Attach `FAT32-Ziel.vdi` to primary IDE master (port 0, device 0) and
`FAT32-Sicherung.vdi` to secondary IDE master (port 1, device 0) while
the BIOS VM is off. Boot `English/fat32-format.img`. On P2, **F** followed
by **2** creates the filesystem and reports `RB FAT32 FORMAT PASS`.
Power off and boot the same floppy again. The cold check shows 8 of 8 and
`RB FAT32 VERIFIED`. Press **R**, then **2**, to return the approved
metadata to its original state. After `RB FAT32 RESTORE PASS`, another
floppy boot shows 0 of 8.

## Publication and recovery

| Order | Target LBA | Contents |
| ---: | ---: | --- |
| 1 | 3,148,741 | Primary FSInfo with the free count and next free cluster |
| 2 | 3,148,742 | Third sector of the primary boot record |
| 3 | 3,148,747 | Backup FSInfo |
| 4 | 3,148,748 | Third sector of the backup boot record |
| 5 | 3,148,772 | First FAT |
| 6 | 3,151,847 | Second FAT |
| 7 | 3,148,746 | Backup boot sector |
| 8 | 3,148,740 | Primary boot sector |

The fixed metadata range includes the full root cluster at 3,154,922 through
3,154,929. Other data clusters and all other partitions are outside the
enrolled write range. Both complete three-sector boot records are identical
on the newly formatted volume. The diskette flushes and reads back each
changed sector. After a power loss a recognized prefix can be restored in
reverse order from the verified original backup. Unexpected bytes block the
operation. Later writes by filesystem tools can change the metadata and
prevent rollback.

The formatter runs under exclusive access to the enrolled IDE pair. Its
16-bit offset covers up to 65,535 metadata sectors for FAT32. In the real-mode
memory available, up to 1,024 sectors that actually differ can be recorded
for checked writes. Larger changes are rejected during the initial scan.
Both original VBR sectors must be empty. A surviving backup VBR at offset 6
protects an existing volume even when its primary VBR has been erased. The FAT16 package
and its P1 procedure are documented separately in the repository.
