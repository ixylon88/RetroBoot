# Festplattenstart: EDD-/CHS-Ladeweg über FAT16

Stand: 9. November 2026. Dies ist ein überprüfbarer Teil von Phase 3.
Der Start erreicht ohne Betriebssystem die Meldungen
`RetroBoot Stage 2 ready` und `RB HDD PASS`.

Der MBR lädt den eigenen VBR des verborgenen logischen FAT16-Volumes. Dieser
lädt die zusammenhängende Datei `RBBOOT.SYS` über ihren installierten
Sektorzeiger. Der Bootstrap sucht `RBSTG2.BIN` im FAT16-Rootverzeichnis,
folgt ihrer Clusterkette und prüft ihren Header und CRC32 vor der Übergabe.
Die Testdatei liegt in den Clustern **20 → 300 → 40**. Damit werden sowohl
Fragmentierung als auch FAT-Einträge in unterschiedlichen Sektoren benutzt.

## Bauen und starten

Unter Linux x86_64 mit Python 3.12, GCC, Make und `qemu-system-x86`:

```sh
make toolchain
make check
make hdd-test
```

| Befehl | Ergebnis |
| --- | --- |
| `make hdd` | Eigene Bootdateien und neue Testimages unter `build/hdd/` |
| `make hdd-check` | Zwei getrennte Builds; Vergleich aller Binärdateien, Images und Manifeste |
| `make hdd-test` | Wiederholungsbuild und 62 QEMU-Szenarien einschließlich Fehlerfällen |
| `python3 tools/test_hdd.py --qemu /pfad/qemu-system-i386 --bios /pfad/bios-256k.bin` | Bereits gebaute Images mit ausdrücklich gewähltem Emulator/BIOS prüfen |

Das kompakte `build/hdd/retroboot-hdd.img` ist 64 MiB groß und kann als erste
IDE-Festplatte einer leeren BIOS-VM gestartet werden. Es enthält weder OS
noch Installer. Sein Code schreibt nicht auf die Platte. Es ist kein
Rettungsmedium und kein Image zum Überschreiben einer vorhandenen Festplatte.

Beispiel mit einem regulär installierten QEMU:

```sh
qemu-system-i386 -machine pc-i440fx-8.2,accel=tcg -cpu 486 -m 16 \
  -nic none -boot c \
  -drive file=build/hdd/retroboot-hdd.img,format=raw,if=ide,snapshot=on
```

Nach der Erfolgsmeldung hält Stage 2 an; ein Menü folgt später. Das Artefakt
**retroboot-hdd-bios** im Workflow **HDD BIOS boot** enthält dieses Image,
Bootdateien, SHA-256-Manifest, Ergebnisse und I/O-Traces. Der Workflow lädt
das große Referenzimage ausdrücklich nicht hoch.

### Manueller Test mit VirtualBox

QEMU ist unser automatisierter Testweg. Das normale Image kann auch in einer
VirtualBox-BIOS-VM auf einem Intel-/AMD-Rechner getestet werden. Der Benutzer
hat am 9. November 2026 einen erfolgreichen VirtualBox-Start des Stands aus
PR #3 zurückgemeldet. VirtualBox-Version und genaue VM-Einstellungen wurden
dabei nicht protokolliert; das ist noch kein Nachweis für den neuen CHS-Fallback.

Die 64-MiB-Datei ist ein rohes Festplattenabbild. Im Ordner mit
`retroboot-hdd.img` lässt sie sich unter Windows/PowerShell so umwandeln:

```powershell
& "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe" convertfromraw `
  "retroboot-hdd.img" "retroboot-hdd.vdi" --format=VDI
```

Eine leere VM mit beispielsweise 32 MiB RAM und einer CPU anlegen, EFI/UEFI
deaktivieren und die VDI als erste IDE-Festplatte (Primary Master) einhängen.
Von dieser Platte starten; ein Installations-ISO ist nicht erforderlich.
Nach `RetroBoot Stage 2 ready` und `RB HDD PASS` ist der Test beendet.
Stage 2 hält bewusst an. Ein weiterhin blinkender Textcursor ist dabei normal.
Ein eigener CHS-Test verlangt zusätzlich ein BIOS ohne EDD beziehungsweise
unseren beschriebenen Emulator-Testaufbau; ein normaler VirtualBox-Start
wählt bei funktionierender EDD-Unterstützung weiterhin EDD.

Oracle dokumentiert die [Raw-zu-VDI-Konvertierung](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/vboxmanage.html)
und die [BIOS-/UEFI-Auswahl](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/working-with-vms.html).

## Testmedien und Grenzen

| Image | Aufbau |
| --- | --- |
| `retroboot-hdd.img` | 64 MiB; MBR-Slots 1–3 leer, Slot 4 Typ `05h` ab LBA 63; EBR bei 63; verborgenes FAT16-Volume Typ `16h` ab LBA 126 mit 128.457 Sektoren; alle Aktivflags null |
| `hdd-fragmented.img` | Gleicher Aufbau mit QEMU-Testausstieg; Stage 2 fragmentiert |
| `hdd-contiguous.img` | Stage 2 in Clustern 20 → 21 → 22 |
| `hdd-boundaries.img` | Cluster 25 → 151 → 40; Zugriffe über LBA 503/504 und 1007/1008 prüfen Spur-/Zylindergrenzen bei 16 Köpfen und 63 Sektoren/Spur |
| `hdd-reference.img` | Sparse-Datei mit exakt 8.000.000.000 Byte und MBR-/EBR-Adressen aus `rb-8g-chs255.json`; Verwaltungs-VBR bei LBA 11.518.668 |
| Weitere `hdd-*.img` | Jeweils ein absichtlich beschädigter Ladeweg |

Nur das eigene Verwaltungsvolume wird in diesen **neu erzeugten** Dateien
mit FAT16-Strukturen befüllt. Die übrigen Volumes des Referenzimages sind
unformatierte Platzhalter. Es werden keine bestehenden Platten eingelesen,
verändert oder mit OS-Daten gefüllt. LBA 1–62 bleiben frei von Bootcode.
Das große Image ist lokal normalerweise eine Sparse-Datei; ein Kopieren mit
ungeeigneten Werkzeugen kann trotzdem 8 GB Speicher belegen.

Die Hostwerkzeuge erlauben ausschließlich die festen Ausgabeordner
`build/hdd/` und `build/hdd-repeat/`. Symlinks und nicht reguläre Einträge in
diesen Ordnern werden abgewiesen. Es gibt keine Option für einen Gerätepfad.

Diese Version verlangt ein BIOS-Laufwerk **80h**, 512-Byte-Sektoren sowie
mindestens einen 386-Prozessor. Der MBR wählt den Leseweg einmalig:

| BIOS-Antwort | Verhalten |
| --- | --- |
| AH=41h erfolgreich, BX=AA55h und CX-Bit 0 gesetzt | EDD: AH=48h muss einen ausreichenden Parameterblock, 512-Byte-Sektoren und die Medienkapazität liefern; gelesen wird mit AH=42h. |
| AH=41h fehlerhaft, falsche Kennung oder kein Extended-Read-Bit | CHS: AH=08h liefert die Geometrie; gelesen wird mit AH=02h. |
| Ausgewählter Leseweg meldet später einen Fehler | Begrenzte Wiederholungen, dann Halt; kein Wechsel des Lesewegs zur Umgehung des Fehlers. |

Bei CHS werden Sektoren/Spur aus CL[5:0], die Kopfzahl aus DH+1 und die
Zylinderzahl aus CH/CL[7:6]+1 bestimmt. Null Sektoren/Spur und eine
fehlgeschlagene Abfrage werden vor einer Division abgewiesen. Die durch das
Registerformat begrenzten Werte ergeben höchstens 1024 Zylinder, 256 Köpfe
und 63 Sektoren/Spur. Für die Umrechnung zählt allein diese BIOS-Geometrie;
BPB-Geometrie und die gepackten CHS-Werte der Partitionstabelle werden nicht
als Leseparameter übernommen.

32-Bit-LBAs werden vor jedem Aufruf gegen die EDD-Sektorzahl beziehungsweise
den mit CHS erreichbaren Bereich geprüft. Auch das gesamte Verwaltungsvolume
muss in diesen Bereich passen. CHS meldet keine unabhängige exakte
Mediengröße; zusätzliche echte Lesefehler werden über den BIOS-Status erkannt.
Die historische Zielmaschine und weitere reale BIOS-Varianten sind noch
nicht vermessen. T04 ist für den unten beschriebenen QEMU-Testaufbau belegt.

Stage 2 ist hier ein kleiner Assembly-Testkörper mit 5.000 Byte einschließlich
Prüfdaten. Die separate C-/Assembly-Probe bleibt bestehen; ihre geprüfte
C-Laufzeit wird erst im nächsten Integrationsschritt in Stage 2 eingebunden.
Es gibt noch keine OS-Übergabe, Partitionserkennung, Umschaltung oder Recovery.

## Speichervertrag

Die Adressen stehen in `include/boot.inc`. Alle frühen Lader verwenden DS=0
und einen Stack unterhalb von `0000:7C00`. Der MBR normalisiert CS und kopiert
sich vollständig nach `0000:0600`, bevor der VBR an die BIOS-Ladeadresse kommt.

| Physischer Bereich | Verwendung |
| --- | --- |
| `00000h–004FFh` | IVT und BDA, nicht überschreiben |
| `00500h–005FFh` | Laufwerk, Leseweg, Kontextkennung, BIOS-Geometrie, EDD-Paket und BIOS-Parameter |
| `00600h–007FFh` | Relokierter MBR einschließlich unveränderter Partitionstabelle |
| `01000h–011FFh` | Ein Sektor Root-/FAT-Puffer |
| `02000h–03FFFh` | Maximal 8 KiB zusammenhängender Bootstrap; derzeit 1.536 Byte |
| `04000h–07BFFh` | Freiraum und früher, nach unten wachsender Stack |
| `07C00h–07DFFh` | Verwaltungs-VBR mit einem reservierten Sektor |
| `10000h–1BFFFh` | Stage-2-Datei, höchstens 48 KiB einschließlich Header |
| `1C000h–1DFFFh` | Reserve für spätere Daten-/BSS-Integration |
| `1E000h–1FFFFh` | Stage-2-Stackbereich, initial `SS=1000h`, `SP=FFFEh` |

Vor dem Laden von Stage 2 prüft der Bootstrap mit INT 12h mindestens 128 KiB
konventionellen Speicher und, falls vorhanden, die EBDA-Untergrenze aus der
BDA. Stage 2 setzt DS/ES/SS auf `1000h`, löscht DF und erhält DL=`80h`.
Der jetzige Assembly-Test benötigt keine BSS-Initialisierung.

## Binärformate und Abbruchbedingungen

| Stufe | Vertrag und Prüfung |
| --- | --- |
| MBR | Genau 440 Byte einschließlich Padding; Magic `RBM1` bei 432, Verwaltungs-VBR-LBA bei 436. Der Host ersetzt nur Byte 0–439; Byte 440–511 bleiben erhalten. |
| VBR | 512 Byte, `55AA`, FAT16-BPB, Magic `RBV1` bei 62; Bootstrap-LBA bei 66, Sektorzahl bei 70, Prüfsumme bei 72. Der MBR verlangt eine 16-Bit-Wortsumme von null über den gesamten VBR. |
| Bootstrap | Magic `RBB1` bei 2, gepaddete Dateilänge bei 6, Wortprüfsumme bei 8, Einstieg bei 32. VBR prüft Bereich, 1–16 Sektoren, Magic, Länge und Wortsumme vor der Übergabe. |
| Stage 2 | Magic `RBS1` bei 2; Headerlänge bei 6, Dateilänge bei 8, CRC32 bei 12, Ladesegment bei 16, Einstieg bei 18, Version bei 20. Erwartet werden 32-Byte-Header, Segment `1000h`, Einstieg 32 und Version 1. CRC32 umfasst Byte 32 bis Dateiende. |

Mehrbytewerte sind Little Endian. CRC32 verwendet das reflektierte Polynom
`EDB88320h`, Anfangswert `FFFFFFFFh` und abschließende Invertierung. Beide
Prüfsummen erkennen Beschädigungen; sie sind keine Authentifizierung.

Der FAT16-Leser akzeptiert gezielt das eigene Format: 512 Byte/Sektor, einen
reservierten Sektor, zwei FATs, 512 Root-Einträge und eine Gesamtsektorzahl im
32-Bit-BPB-Feld. Clustergröße, FAT-Kapazität, FAT16-Clusterzahl, Datenbereich,
Überläufe und BIOS-Mediengrenze werden geprüft. Rootsuche und Datei sind
begrenzt; gelöschte Einträge, Verzeichnisse, Volume-Labels und LFNs werden
übersprungen. Genutzte FAT-Einträge müssen in beiden Kopien übereinstimmen.
Die Kopien werden nicht vollständig auf unbenutzte Einträge verglichen.

Eine Datei darf höchstens 96 Sektoren benötigen. Nach genau ihrer erwarteten
Länge muss die Clusterkette mit EOC enden. Dadurch enden auch Schleifen
begrenzt mit Fehler; es gibt keine endlose FAT-Suche. Freie, reservierte,
defekte oder außerhalb des Datenbereichs liegende Cluster werden abgewiesen.
Das gesamte geladene File wird vor dem Sprung über Header und CRC geprüft.

Jeder BIOS-Leseaufruf liest genau einen Sektor ohne 64-KiB-Grenzübertritt.
Nach einem Fehler wird das Laufwerk zurückgesetzt, das EDD-Paket beziehungsweise CHS-Register neu aufgebaut
und höchstens zweimal erneut gelesen. Fehler zeigen die zuständige Stufe
beziehungsweise Ursache an und halten den Rechner an.

## Nachweise

Lokal geprüft mit QEMU 8.2.2/SeaBIOS, i440FX, CPU `486`, 16 MiB RAM:

- 76 Hosttests, darunter MBR-Erhalt, EBR-Adressierung und unabhängiges
  Zusammensetzen der fragmentierten Datei über ihre FAT-Kette.
- Bytegleiche Binärdateien, vollständige Image-SHA-256-Werte und Manifeste
  aus zwei getrennten Builds.
- 62 Bootläufe: kompakte und große positive Images, beschädigte VBR- und
  Bootstrap-Prüfsummen, ungültige Bereiche/BPBs, fehlende oder zu große Datei,
  kurze/lange/zyklische FAT-Ketten, freie/defekte/falsche Cluster, abweichende
  FAT-Kopien, Header- und CRC-Fehler einschließlich des letzten Fragments.
- QEMU-`blkdebug` erzeugt einen einmaligen und einen dauerhaften echten
  Blocklesefehler. Die IDE-Traces zeigen zwei beziehungsweise drei Versuche
  am betroffenen LBA; danach folgt Erfolg beziehungsweise `RB READ ERROR`.
- Das ausgelieferte Image ohne QEMU-Testausstieg wird ebenfalls gestartet.
  Die Teststeuerung stoppt nach seiner Erfolgsmeldung die VM über QMP,
  liest alle 5.000 Byte Stage 2 aus dem physischen Speicher ab `10000h` zurück
  und vergleicht sie mit `stage2.bin`. Dies geschieht mit EDD, mit CHS und
  zusätzlich einmal ohne das Test-Option-ROM. Erst danach wird QEMU beendet.

Das eigene Option-ROM `tests/bios/int13_rom.asm` protokolliert INT-13h-Aufrufe
und kann EDD als nicht vorhanden melden. Der MBR selbst bleibt in diesen
Tests unverändert. Die ROM-Varianten prüfen außerdem eine falsche EDD-Kennung,
fehlendes Extended-Read-Bit, AH=08h-Fehler, null Sektoren/Spur und ungültige
AH=48h-Antworten. Die ROMs sind ausschließlich Testzubehör und müssen bei
einem normalen manuellen Start nicht eingebunden werden.
Sie reservieren 1 KiB am oberen Ende des konventionellen Speichers über den
BDA-Speicherzähler und hängen sich in den INT-13h-Vektor ein. Diese Eingriffe
gehören zum Testaufbau, nicht zum ausgelieferten Festplattenimage.

26 Szenarien laufen jeweils mit EDD und CHS. Die IDE-Traces müssen exakt
dieselbe geordnete Sektorfolge einschließlich Wiederholungen enthalten.
Die BIOS-Traces beweisen dabei die Benutzung von AH=42h beziehungsweise
AH=02h nach der Auswahl. Spur-/Zylinderwechsel werden bei 16/63 geprüft;
das 8-GB-Image prüft auch Zylinder über 255. Zwei zusätzliche Tests begrenzen
die echte emulierte BIOS-Geometrie: Ein unerreichbarer VBR führt zu
`RB MBR ERROR`, ein nur teilweise erreichbares Verwaltungsvolume zu
`RB BPB ERROR`. Die Dateisystemdaten werden dabei nicht angepasst.

QEMU verwendet wegwerfbare Snapshot-Overlays, weil sein IDE-Frontend ein
schreibbares Medium verlangt. Die Quelldateien werden davor und danach
vollständig gehasht. Ab dem ersten MBR-Lesen darf der Trace keine IDE- oder
Blockschreiboperation enthalten; die vorherige Anlage des Overlays zählt
nicht als Gastzugriff. Die Tests bestätigen diese Bedingungen in allen Fällen.
Hashes von QEMU, SeaBIOS und VGA-ROM stehen zusätzlich in `boot-results.json`.

Damit sind T01 für diese Artefakte sowie T02/T03/T04 und ein abgegrenzter Teil
von T05 im beschriebenen Testaufbau nachgewiesen. Weitere BIOS-/Geometrie-
und Hardwaretests bleiben nötig. Ein erfolgreicher Bootnachweis ist kein Nachweis
für spätere Installations- oder Partitionsänderungen.

Formatgrundlagen: die in v0.2 referenzierten FAT- und Phoenix-EDD-Dokumente.
Die Fehlerinduktion folgt der
[QEMU-Dokumentation zu blkdebug](https://www.qemu.org/docs/master/devel/testing/blkdebug.html).
