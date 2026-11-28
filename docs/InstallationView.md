# Setup-Partitionssicht für Windows 95 OSR2 auf P2

Die Diskette wendet die sechs Byteänderungen aus der Installationsplanung
auf der mitgelieferten Testfestplatte an. Ein Kaltstart mit derselben Diskette
zeigt, ob die Setup-Sicht aktiv ist. Von dort lässt sich die ursprüngliche
Sicht aus der Sicherung wiederherstellen. Der Versuch benötigt keine Windows-CD.

## In VirtualBox

1. Die BIOS-Test-VM ausschalten. Die beiden VDIs aus diesem Paket am
   IDE-Controller anschließen. Vor dem Start die Belegung mit der Tabelle
   vergleichen. Die deutsche Diskette `Deutsch/install-view.img` in A:
   einlegen und von Diskette starten.

   | Datei | VirtualBox-Anschluss | Erwartete Seriennummer |
   | --- | --- | --- |
   | `Setup-Ziel.vdi` | Primärer Master, Port 0, Gerät 0 | `VB52421001-11111111` |
   | `Setup-Sicherung.vdi` | Sekundärer Master, Port 1, Gerät 0 | `VB52421002-22222222` |

2. Im Originalzustand zeigt die Diskette **0** bereits geänderte Sektoren
   und die **6** geplanten Byteänderungen in **3** Tabellensektoren. **A**,
   dann **2** bestätigt das Anwenden auf P2. Erwartet werden
   `RB INSTALL VIEW APPLY PASS` und `RB INSTALL VIEW END`.
3. Die VM ganz ausschalten. Mit beiden VDIs und derselben Diskette wieder
   starten. **3** bereits geänderte Sektoren und `RB INSTALL VIEW ACTIVE`
   bestätigen die dauerhafte Umschaltung. Die Bytewerte in der Anzeige
   beschreiben jetzt den Rückweg. **R**, dann **2** stellt die ursprüngliche
   Sicht wieder her. Die Abschlussmeldung lautet `RB INSTALL VIEW RESTORE PASS`.
4. Nach einem weiteren Kaltstart müssen wieder **0** Sektoren als geändert
   erscheinen. **Esc** beendet den Versuch. Ein Abbruch an der Bestätigung
   lässt den angezeigten Zustand bestehen.

| Reihenfolge beim Anwenden | Wirkung auf der Testplatte |
| --- | --- |
| EBR von L1, LBA `0x009FD38C` | Gemeinsames FAT16-Volume verbergen |
| EBR von L3, LBA `0x00B1B895` | Gemeinsames FAT32-Volume verbergen |
| MBR, LBA `0x00000000` | P1 verbergen und deaktivieren, P2 sichtbar und aktiv machen |

Jede Änderung wird auf die Zielplatte geschrieben, aus dem Plattencache
gesichert und vollständig zurückgelesen. Nach einer Unterbrechung bietet
die Diskette die Rücknahme der erkannten Schritte in umgekehrter Reihenfolge
an. Bei einer fremden Änderung erscheint `RB INSTALL VIEW BLOCKED`.
Die Diskette greift während des gesamten Versuchs nur lesend auf die Sicherungsplatte zu.

## English

Attach `Setup-Ziel.vdi` as the primary IDE master and `Setup-Sicherung.vdi`
as the secondary IDE master of a powered-off BIOS VM. Boot
`English/install-view.img` as A:. The floppy is bound to the two enrolled
ATA identities. The initial screen identifies Windows 95 OSR2 on P2 and lists
the exact old and proposed bytes.

| Boot | Keys | Expected result |
| --- | --- | --- |
| Original, 0 sectors changed | **A**, **2** | `RB INSTALL VIEW APPLY PASS` |
| Cold boot, 3 sectors changed | **R**, **2** | `RB INSTALL VIEW ACTIVE`, then `RB INSTALL VIEW RESTORE PASS` |
| Cold boot after restore, 0 sectors changed | **Esc** | `RB INSTALL VIEW END` |

The guest reads all four table sectors from both IDE masters, compares the
primary reads with the BIOS view and the backup reads with the approved
original sectors on the floppy. The planner supplies the desired type and
active-flag bytes. The external copy supplies the original sectors for
restore. The primary write routine accepts only three fixed table indices.
The guest checks the state before every write and reads the sector back after
flushing. Cold recovery accepts a prefix of completed writes. An unexpected
table byte, an out-of-order change or a missing disk blocks the operation.

Applying the view requires the six checked P2 boot sectors to be empty.
Restoring visibility only touches the three partition tables, so data
created on P2 in the meantime is preserved. The management EBR, EBR links,
volume boot sectors and file data stay outside every change. This kit covers
the visibility transaction on the supplied test pair. Starting the original
setup media and tracking its reboots are later steps in
[the installation workflow](https://github.com/ixylon88/RetroBoot/issues/51).

On Linux, `make toolchain` followed by `make install-view-test` builds both
languages and boots the packaged media in QEMU. The tests check the exact
write and flush order, cold recovery after each interrupted step, and the
complete disk contents after rollback.
