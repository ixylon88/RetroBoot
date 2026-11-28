# FAT16 and FAT32 format preview

The independently booted `fat-plan.img` reads BIOS disk `0x80` and previews the
filesystem layout of a selected primary partition. It performs no writes.
The test VDI uses the frozen RB-8G-CHS255 MBR/EBR layout with a logical
capacity of 8,000,000,000 bytes. A sparse VDI stores the few populated sectors.

## VirtualBox-Test auf Deutsch

1. Bei ausgeschalteter BIOS-VM `Format-Test.vdi` als einzige IDE-Festplatte
   einbinden (primärer Master, Port 0, Gerät 0). `Deutsch/fat-plan.img` in
   Laufwerk A einlegen und von Diskette starten.
2. **1**, dann **Enter** zeigt den FAT16-Plan für P1. **2**, dann **Enter**
   zeigt den FAT32-Plan für P2. Enter wählt jeweils die automatische Clustergröße.
3. **2**, dann **G** wählt 64 Sektoren je Cluster für P2. Damit entstehen zu
   wenige Datencluster für FAT32 und die Vorschau meldet den Grund.
4. **3**, dann **Enter** erkennt den vorhandenen FAT32-Header auf P3.
   **Esc** in der Partitionsauswahl beendet die Vorschau.

| Ziel | Sektoren je Cluster | Sektoren je FAT | Datencluster |
| --- | ---: | ---: | ---: |
| P1 · FAT16 | 64 | 193 | 49.191 |
| P2 · FAT32 | 8 | 3.075 | 392.819 |
| P3 · FAT32 | 8 | 4.079 | 521.088 |

## VirtualBox test in English

Boot `English/fat-plan.img` in drive A with `Format-Test.vdi` as the only IDE
hard disk (primary master, port 0, device 0). The digits **1** to **4** select
physical MBR slots. **Enter** at the cluster-size prompt selects the default.
**A** to **G** select 1, 2, 4, 8, 16, 32 or 64 sectors per cluster.
On P2, **G** produces too few clusters for FAT32. P3 contains a recognizable
FAT32 header. **Esc** returns from the cluster prompt or exits from the slot
prompt.

## What the preview establishes

Each successful display requires two matching observations of BIOS capacity,
CHS geometry, the MBR, the validated partition layout and the selected first
sector. A supported LBA primary type requires EDD. A CHS primary type
requires both encoded endpoints to match the reported BIOS geometry and the
whole extent to be reachable. The preview accepts hidden variants of the
supported FAT types. Logical volumes and the extended container are outside
this primary selection.

The plan uses 512-byte sectors and two FATs. FAT16 reserves one sector and
512 fixed root entries. FAT32 reserves 32 sectors, places FSInfo at relative
sector 1 and proposes the backup boot and FSInfo at relative sectors 6 and 7.
The FAT32 root directory occupies cluster 2. The display includes both FAT
ranges, the root range and the first data LBA. All range ends are inclusive.

For each candidate cluster size the FAT budget includes two reserved entries
and every possible cluster before the two tables are deducted. Subtracting
both tables yields the actual data-cluster count. Close to the lower FAT
cutover, the plan can reduce this reservation while still requiring room
for every FAT entry. FAT16 requires 4,085 to
65,524 clusters. FAT32 starts at 65,525 and uses the same upper bound as
the volume header reader. FAT32 prefers eight sectors per cluster. Otherwise
the automatic choice uses the smallest valid power of two up to 64.

The header check reads just the first sector of the selected volume. P1
deliberately contains data nine sectors beyond its zero first sector. P3
contains a test BPB. A recognized header establishes neither filesystem
integrity nor the presence of OS boot files.

This is the first installer increment for issue #50. The next
[target review](FATFormatReview.md) checks a separate copy of the selected
metadata and rehearses the confirmation. Actual formatting, interruption
handling and the T11 guest filesystem read/write test remain open.
