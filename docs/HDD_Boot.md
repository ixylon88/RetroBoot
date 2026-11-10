# Festplattenstart: EDD-/CHS-Ladeweg über FAT16 bis C

Stand: 10. November 2026. Ladeweg aus Phase 3, mit Menü und lesendem MBR-/EBR-Scanner.
Der Start erreicht ohne Betriebssystem den eigenen C-Einstieg. Bootmeldungen
bei einem BIOS mit EDD:

```text
C entry, data, BSS, pointers and integer calls OK
BIOS disk path: EDD
RetroBoot Stage 2 ready
RB HDD PASS
```

Beim Fallback steht in der zweiten Zeile `CHS`. Die letzten beiden Zeilen
erscheinen erst nach erfolgreicher C-Rückkehr und den Assembly-Nachprüfungen.
Das normale Image öffnet anschließend das [Textmenü](Menue.md). Die Meldungen
werden dabei vom Menübild abgelöst und bleiben im QEMU-Debugprotokoll erhalten.

Der MBR lädt den eigenen VBR des verborgenen logischen FAT16-Volumes. Dieser
lädt die zusammenhängende Datei `RBBOOT.SYS` über ihren installierten
Sektorzeiger. Der Bootstrap sucht `RBSTG2.BIN` im FAT16-Rootverzeichnis,
folgt ihrer Clusterkette und prüft ihren Header und CRC32 vor der Übergabe.
Die Testdatei liegt fragmentiert, beginnend mit **20 → 300 → 40 → 500 → 60**;
die benötigte Kettenlänge wächst mit der Datei. Damit werden sowohl
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
| `make hdd-test` | Wiederholungsbuild, 86 Bootfälle, 75 Menüansichten und 204 Scannerzustände in QEMU |
| `make menu-test` | Einmal bauen und gezielt die Menübedienung prüfen |
| `make scan-test` | Einmal bauen und gezielt Scannerfehler und Blättern prüfen |
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

Nach der Erfolgsmeldung erscheint das bedienbare Textmenü. Das Artefakt
**retroboot-hdd-bios** im Workflow **HDD BIOS boot** enthält dieses Image,
Bootdateien, Linkerkarten, SHA-256-Manifest, Ergebnisse, Menü-Screenshots und I/O-Traces. Der Workflow lädt
das große Referenzimage ausdrücklich nicht hoch.

### Manueller Test mit VirtualBox

QEMU ist unser automatisierter Testweg. Das normale Image kann auch in einer
VirtualBox-BIOS-VM auf einem Intel-/AMD-Rechner getestet werden. Der Benutzer
hat am 9. November 2026 einen erfolgreichen VirtualBox-Start des Stands aus
PR #3 zurückgemeldet. VirtualBox-Version und genaue VM-Einstellungen wurden
dabei nicht protokolliert. Inzwischen wurden auch die vier C-Erfolgsmeldungen
aus PR #5 manuell bestätigt, ohne erneute genaue Plattformangabe. Der neue
Menüstand und der erzwungene CHS-Fallback sind noch manuell zu prüfen.

Die 64-MiB-Datei ist ein rohes Festplattenabbild. Im Ordner mit
`retroboot-hdd.img` lässt sie sich unter Windows/PowerShell so umwandeln:

```powershell
& "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe" convertfromraw `
  "retroboot-hdd.img" "retroboot-hdd.vdi" --format=VDI
```

Eine leere VM mit beispielsweise 32 MiB RAM und einer CPU anlegen, EFI/UEFI
deaktivieren und die VDI als erste IDE-Festplatte (Primary Master) einhängen.
Von dieser Platte starten; ein Installations-ISO ist nicht erforderlich.
Nach den Bootmeldungen erscheint jetzt das Menü. Pfeile wählen eine
Informationsseite, Enter öffnet sie, Esc führt zurück; F2 prüft MBR und EBR-Kette,
F8 zeigt die Recovery-Hinweise. Im kompakten Image erscheinen vier primäre
Slots und das logische Verwaltungsvolume. Der Auswahlbalken ersetzt den Cursor.
Eine alte VDI muss aus dem neuen Image erneut erzeugt werden.
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
| `hdd-contiguous.img` | Stage 2 zusammenhängend ab Cluster 20 |
| `hdd-boundaries.img` | Kette beginnt mit 25 → 151 → 40; Zugriffe über LBA 503/504 und 1007/1008 prüfen Spur-/Zylindergrenzen bei 16 Köpfen und 63 Sektoren/Spur |
| `hdd-reference.img` | Sparse-Datei mit exakt 8.000.000.000 Byte und MBR-/EBR-Adressen aus `rb-8g-chs255.json`; Verwaltungs-VBR bei LBA 11.518.668 |
| `retroboot-reference.img` | Dasselbe große Referenzlayout mit normalem, bedienbarem Menü; nur lokal gebaut, kein CI-Upload |
| `hdd-menu-model.img` | Native C/16-Auswahl- und Timerprüfungen mit QEMU-Testausstieg |
| `hdd-scan-model.img` | 51 native C/16-Parserbedingungen mit QEMU-Testausstieg |
| Weitere `hdd-*.img` | Jeweils ein absichtlich beschädigter Ladeweg |
| `scan-*.img` | Normaler Ladeweg und normales Menü mit gezielten Partitionsfehlern beziehungsweise langen EBR-Ketten; kein CI-Upload |

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

Stage 2 besteht aus dem Startcode und C-Code in `core/`, den Menü-BIOS-Helfern
in `bios/` und den mit der Diskettenprobe geteilten Helfern in `runtime/`. Open Watcom C/16
und NASM erzeugen OMF-Objekte, WLINK daraus eine flache Binärdatei ohne DOS-
oder C-Standardbibliothek. Compilerflags und Werkzeugfixierung entsprechen
der [ABI-Probe](ABI_Probe.md). Der Build prüft die ausführbaren Compilerdateien,
behandelt Warnungen als Fehler und gleicht Header, Linkersegmente und die
Adressen der C-Variablen ab.

4.096 Byte festes Padding am Ende der initialisierten Daten erzwingen weiterhin
mehrere FAT-Cluster. BSS folgt erst nach diesem Padding. Damit bleiben die
Fragmentierungs- und Grenztests aussagekräftig. Der Imagebau verlängert die
Kette entsprechend der Dateigröße; das Budget bleibt 48 KiB. Die exakten Dateigrößen und Speicher-
grenzen jedes Builds stehen in `manifest.json`.
Nach dem C-Starttest ruft das normale Image `rb_menu_run()` auf. Die lesende
Partitionsprüfung ist in der [Scanner-Anleitung](Partitionen.md) beschrieben.
Es gibt noch keine OS-Übergabe, Partitionsänderung oder Recovery.

## Speichervertrag

Die Adressen stehen in `include/boot.inc` und `include/memory.inc`. Alle frühen Lader verwenden DS=0
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
| Ab `10000h`, maximal bis `1BFFFh` | Stage-2-Datei, höchstens 48 KiB einschließlich Header und Padding |
| Ab `10000h + bss_begin` bis vor `10000h + bss_end` | C-BSS einschließlich Bootkontext; beginnt nach der Datei und endet spätestens bei `1E000h` |
| `1E000h–1E001h` | Stack-Schutzwort `A55Ah` |
| `1E002h–1FFFDh` | C-Stack, initial `SS=1000h`, `SP=FFFEh`, wächst abwärts |

Vor dem Laden von Stage 2 prüft der Bootstrap mit INT 12h mindestens 128 KiB
konventionellen Speicher und, falls vorhanden, die EBDA-Untergrenze aus der
BDA. Stage 2 setzt DS/ES/SS auf `1000h`, richtet SP ein, löscht DF und die vom
Linker bestimmte BSS und setzt das Stack-Schutzwort. Erst danach werden
Interrupts freigegeben und C aufgerufen. Zum Löschen verwendet der Startcode
seine gelinkten Symbole, nicht die eingelesenen Headerwerte. Die Headergrenzen
sind eine zusätzliche Prüfung vor der Übergabe.

`rb_main(const rb_boot_context *boot)` bekommt einen Near-Zeiger auf eine
Kopie des Loader-Kontexts in der eigenen BSS. Der Vertrag steht in
`include/stage2.h`; alle Felder sind vor dem C-Aufruf initialisiert:

| Offset im Kontext | Typ | Inhalt |
| --- | --- | --- |
| 0 | `rb_u16` | BIOS-Laufwerk, derzeit `0080h` |
| 2 | `rb_u16` | Leseweg: 0 für CHS, 1 für EDD |
| 4 | `rb_u32` | Untere 32 Bit der erreichbaren Sektorzahl |
| 8 | `rb_u32` | Obere 32 Bit der erreichbaren Sektorzahl |

Die Sektorzahl stammt aus AH=48h oder der CHS-Geometrie; bei CHS ist sie keine
unabhängige Messung der Mediengröße. C prüft Kontext, initialisierte Daten,
BSS, Near-/Far-Zeiger und Integeraufrufe. Nach der Rückkehr prüft Assembly
SI/DI/BP, DS/SS, IF/DF, den ausgeglichenen Stack, das Schutzwort und eine
32-Bit-C-Rückgabe in DX:AX. ES ist nach dem Watcom-Vertrag caller-saved und
wird nach C-Rückkehr nicht als erhalten vorausgesetzt. Ein Fehler liefert
`RB C STARTUP ERROR` und Halt. Das Schutzwort ersetzt keine spätere Analyse
des maximalen Stackbedarfs.

## Binärformate und Abbruchbedingungen

| Stufe | Vertrag und Prüfung |
| --- | --- |
| MBR | Genau 440 Byte einschließlich Padding; Magic `RBM1` bei 432, Verwaltungs-VBR-LBA bei 436. Der Host ersetzt nur Byte 0–439; Byte 440–511 bleiben erhalten. |
| VBR | 512 Byte, `55AA`, FAT16-BPB, Magic `RBV1` bei 62; Bootstrap-LBA bei 66, Sektorzahl bei 70, Prüfsumme bei 72. Der MBR verlangt eine 16-Bit-Wortsumme von null über den gesamten VBR. |
| Bootstrap | Magic `RBB1` bei 2, gepaddete Dateilänge bei 6, Wortprüfsumme bei 8, Einstieg bei 32. VBR prüft Bereich, 1–16 Sektoren, Magic, Länge und Wortsumme vor der Übergabe. |
| Stage 2 | 32-Byte-Header `RBS2`, Speichergrenzen und CRC32; die Felder stehen unten. |

Der Stage-2-Header wurde auf Version 2 angehoben, weil er jetzt auch den
C-Speichervertrag beschreibt. Bootstrap und Stage-2-Datei müssen gemeinsam
aktualisiert werden; ein alter `RBS1`-Header wird abgewiesen.

| Byteoffset | Breite | Inhalt / Erwartung |
| --- | --- | --- |
| 0 | 2 | `EB 1E`, Sprung zum Einstieg bei 32 |
| 2 | 4 | `RBS2` |
| 6 | 2 | Headergröße 32 |
| 8 | 4 | Exakte Dateilänge einschließlich Header und Padding |
| 12 | 4 | CRC32 über Byte 32 bis Dateiende |
| 16 | 2 | Ladesegment `1000h` |
| 18 | 2 | Eintrittsoffset 32 |
| 20 | 2 | Formatversion 2 |
| 22 | 2 | BSS-Anfang als Segmentoffset, mindestens Dateilänge |
| 24 | 2 | Exklusives BSS-Ende, größer als Anfang und höchstens `E000h` |
| 26 | 2 | Stack-Untergrenze `E000h` |
| 28 | 2 | Initialer SP `FFFEh` |
| 30 | 2 | Reserviert, muss null sein |

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

- 86 Hosttests, darunter MBR-Erhalt, EBR-Adressierung, VGA-Dekodierung und
  unabhängiges Zusammensetzen der Datei über ihre FAT-Kette bis 48 KiB.
- Bytegleiche Binärdateien, vollständige Image-SHA-256-Werte und Manifeste
  aus zwei getrennten Builds.
- 86 Bootläufe: kompakte und große positive Images, beschädigte VBR- und
  Bootstrap-Prüfsummen, ungültige Bereiche/BPBs, fehlende oder zu große Datei,
  kurze/lange/zyklische FAT-Ketten, freie/defekte/falsche Cluster, abweichende
  FAT-Kopien, Header- und CRC-Fehler einschließlich des letzten Fragments.
  Dazu kommen alte Header, überlappende/leere/überlaufende BSS-Grenzen,
  falscher Stackvertrag und gesetzte reservierte Headerbits.
- Vier C-Fehlervarianten je Leseweg: fehlende BSS-Löschung, beschädigte
  Initialwerte, falscher Bootkontext und zerstörtes Stack-Schutzwort. Alle
  haben gültige Datei-CRCs und erreichen tatsächlich den C-Startcode. Der
  Test-Bootstrap füllt die validierte BSS nach dem Laden mit `A5h`; zufällig
  nullgefüllter VM-Speicher oder die Sektorrundung können den BSS-Fehler somit
  nicht verdecken. Das normale Image enthält diese Testeingriffe nicht.
- QEMU-`blkdebug` erzeugt einen einmaligen und einen dauerhaften echten
  Blocklesefehler. Die IDE-Traces zeigen zwei beziehungsweise drei Versuche
  am betroffenen LBA; danach folgt Erfolg beziehungsweise `RB READ ERROR`.
- Das ausgelieferte Image ohne QEMU-Testausstieg wird ebenfalls gestartet.
  Die Teststeuerung stoppt nach seiner Erfolgsmeldung die VM über QMP,
  liest das 64-KiB-Stage-2-Segment ab `10000h` zurück und vergleicht alle
  Dateibytes mit `stage2.bin`. Zusätzlich müssen C-Bootkontext, das von C
  geschriebene BSS-Wort `BEADh`, alle übrigen BSS-Bytes und das Stack-Schutzwort
  stimmen. Dies geschieht mit EDD, mit CHS und
  zusätzlich einmal ohne das Test-Option-ROM. Erst danach wird QEMU beendet.
- Zwei der Bootfälle prüfen 26 Bedingungen der tatsächlichen C/16-Menülogik
  einschließlich Auswahl, ungültigem Standard, Timeout und Tageswechsel.
  Zwei weitere prüfen 51 Bedingungen des C/16-Partitionsparsers.
  Zusätzlich werden die normalen Images in fünf Menükampagnen bedient:
  insgesamt 75 VGA-Textseiten mit RAM- und I/O-Nachprüfungen, siehe [Textmenü](Menue.md).
- 32 Scanner-Kampagnen prüfen weitere 204 Zustände: Strukturfehler, begrenzte
  EBR-Suche, echte Lesefehler und Blättern. Die exakten Scan-Sektorfolgen und
  erhaltene Bedienbarkeit werden kontrolliert, siehe [Partitionsprüfung](Partitionen.md).

Das eigene Option-ROM `tests/bios/int13_rom.asm` protokolliert INT-13h-Aufrufe
und kann EDD als nicht vorhanden melden. Der MBR selbst bleibt in diesen
Tests unverändert. Die ROM-Varianten prüfen außerdem eine falsche EDD-Kennung,
fehlendes Extended-Read-Bit, AH=08h-Fehler, null Sektoren/Spur und ungültige
AH=48h-Antworten. Die ROMs sind ausschließlich Testzubehör und müssen bei
einem normalen manuellen Start nicht eingebunden werden.
Sie reservieren 1 KiB am oberen Ende des konventionellen Speichers über den
BDA-Speicherzähler und hängen sich in den INT-13h-Vektor ein. Diese Eingriffe
gehören zum Testaufbau, nicht zum ausgelieferten Festplattenimage.

38 Boot-Szenarien laufen jeweils mit EDD und CHS. Die IDE-Traces müssen exakt
dieselbe geordnete Sektorfolge einschließlich Wiederholungen enthalten.
Die BIOS-Traces beweisen dabei die Benutzung von AH=42h beziehungsweise
AH=02h nach der Auswahl. Spur-/Zylinderwechsel werden bei 16/63 geprüft;
das 8-GB-Image prüft auch Zylinder über 255. Zwei zusätzliche Tests begrenzen
die echte emulierte BIOS-Geometrie: Ein unerreichbarer VBR führt zu
`RB MBR ERROR`, ein nur teilweise erreichbares Verwaltungsvolume zu
`RB BPB ERROR`. Die Dateisystemdaten werden dabei nicht angepasst.

Der neue Scanner prüft zusätzlich die Reichweite aller eingetragenen
Partitionen. Beim großen Referenzimage reicht QEMUs automatische CHS-Geometrie
für das Verwaltungsvolume, aber nicht für ganz P4. Ein negativer Menütest
prüft die verständliche Ablehnung dieser Konstellation; die positiven
Referenz-Menütests verwenden eine festgelegte ausreichende logische BIOS-Geometrie.

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
