# DOS-Dateitest für FAT16 und FAT32

Die Testfestplatte enthält die FAT16-Partition P1 als C: und die FAT32-Partition P2
als D:. Die Startdiskette enthält FreeDOS Kernel 2046. Eine eigene DOS-Installation
wird für diesen Test nicht benötigt.

1. In einer ausgeschalteten BIOS-Test-VM nur `DOS-Dateitest.vdi` als primären
   IDE-Master (Port 0, Gerät 0) anschließen. `Deutsch/dos-test.img` in A: einlegen
   und von Diskette starten.
2. **1**, dann **W** legt auf P1 die Datei `C:\RBT11.DAT` an. Nach
   `RB DOS WRITE PASS` die VM ausschalten und von derselben Diskette erneut starten.
3. **1**, dann **V** prüft alle 98.321 Bytes und das Dateiende. Nach
   `RB DOS READ PASS` löscht **D** die geprüfte Datei und meldet
   `RB DOS DELETE PASS`. **Esc** behält die Datei.
4. Für P2 nach einem Neustart denselben Ablauf mit **2** durchführen.
   Die Testdatei liegt dort als `D:\RBT11.DAT`.

Jedes Volume enthält die eigene schreibgeschützte Kennungsdatei `RBT11.ID`.
Ein zweites **W** lässt eine vorhandene Datei bestehen. Bei abweichendem Inhalt
bleibt die Datei zur Diagnose erhalten. Eine frisch entpackte Test-VDI stellt
den Ausgangszustand wieder her.

### Mit eigener DOS-Startdiskette

Von der eigenen DOS-Systemdiskette bis zur Eingabeaufforderung starten. Dann
die Testdiskette einlegen und `A:\RBT11.COM` aufrufen. Der Aufruf ohne Parameter
kehrt zur Eingabeaufforderung zurück. Unter MS-DOS 6.22 steht P1 zur Verfügung.
Für P2 wird ein DOS mit FAT32-Unterstützung benötigt, etwa von Windows 95 OSR2
oder Windows 98. Für die Kaltprüfung erneut vom eigenen DOS starten.

## English

Attach only `DOS-Dateitest.vdi` as the primary IDE master of a powered-off BIOS
test VM. Insert `English/dos-test.img` as A: and boot the floppy. Select **1**
for FAT16 P1 (C:) or **2** for FAT32 P2 (D:). **W** creates a 98,321-byte
`RBT11.DAT` in the selected root and displays `RB DOS WRITE PASS`. Power off,
boot the same floppy again, choose the same partition and press **V**.
`RB DOS READ PASS` confirms every byte and the exact end of file. **D**
rechecks and deletes the file, reporting `RB DOS DELETE PASS`. **Esc** keeps it.
Repeat for the other partition. An existing file is never overwritten.

For a test under an original DOS system, boot a compatible system floppy,
swap to the test floppy at the DOS prompt and run `A:\RBT11.COM`. After
power-off, boot the same original system for the readback. MS-DOS 6.22
can test P1. A FAT32-capable DOS can test both volumes.

### Fixture and software

The two filesystems come from the actual RetroBoot FAT16 and FAT32 formatter
diskettes. The kit builder transfers their metadata to a fresh data disk at the
same partition offsets, exposes P1 and P2, then installs one read-only volume
identifier on each. The test checks the DOS volume serial and identifier before
creating a file. It uses DOS file handles for creation, writing, committing, reading, closing
and deletion. The 96 KiB plus 17 bytes span four FAT16 or 25 FAT32 clusters.
The disk is separate from the formatter/recovery fixtures.

On Linux, `make toolchain` and `make dos-guest-test` build and exercise the kit
with QEMU, dosfstools and mtools. The test boots a new VM for each cold check,
opens the resulting files independently, compares both FATs, and checks the
FAT32 backup boot records and FSInfo signatures.

The boot floppies include the unmodified FreeDOS 2046 kernel and its FAT12 boot
loader assembled from the release source. The matching source archive and
license accompany the kit in `FreeDOS/`. The original release is available
from the [FreeDOS kernel project](https://github.com/FDOS/kernel/releases/tag/ke2046).
