# Entwicklung – Hostprüfungen und erste Bootlader

Stand: 10. November 2026.

Die [BIOS-/ABI-Probe](ABI_Probe.md) ergänzt den Layoutprüfer um einen echten
Real-Mode-Start mit Open-Watcom-C/16 und NASM. Die folgende Beschreibung des
Layoutprüfers bleibt gültig; er selbst erzeugt weiterhin nur Berichte.
Hinzu kommt der [Festplattenladeweg](HDD_Boot.md) über BIOS-EDD/CHS und FAT16
bis zum C-Einstieg mit eigenem Startcode.
Darauf baut jetzt das [lesende Textmenü](Menue.md) auf.
Die [CI-Erklärung](CI.md) beschreibt die automatischen Windows-/Linux-Prüfungen.

## Was jetzt funktioniert

`tools/retroboot_layout.py` prüft den geplanten Aufbau eines CHS-erreichbaren
MBR-Datenträgers. Der erste Plan in `profiles/rb-8g-chs255.json` bildet die
Sektor- und FAT-Werte aus den Abschnitten 5 und 10 der
[Spezifikation v0.2](spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md) ab.
Der Prüfer legt OS-Namen, Größen und Slotbelegung nicht im Code fest.

| Prüfung | Umfang |
| --- | --- |
| Eingabe | Formatversion, Pflichtfelder, unbekannte Felder, doppelte JSON-Schlüssel, Ganzzahlen und IDs |
| Datenträger | Genau 512 Byte je Sektor; vollständige Sektoren; gesamtes Medium innerhalb der angegebenen CHS-Reichweite |
| MBR-Plan | Höchstens vier Einträge, genau ein `05h`-Container; keine Überlappung, Bereichsüberschreitung oder 32-Bit-LBA-Überläufe |
| Logische Volumes | Datenbereiche und EBR-Sektoren vollständig im Container, paarweise überschneidungsfrei |
| EBR-Adressen | Erster EBR an der Containerbasis; streng aufsteigende Planung; Dateneintrag relativ zum eigenen EBR, Weiterverweis relativ zur Containerbasis |
| Verwaltung | Genau ein logisches RetroBoot-Volume, dauerhaft verborgen als FAT16-Typ `16h` |
| FAT | Typ und Clusterzahl, Zweierpotenz der Clustergröße, höchstens 32 KiB/Cluster, zwei ausreichende FATs und FAT16-Rootbereich |
| Bericht | CHS-Werte einschließlich der drei gepackten MBR-Bytes; deterministisches JSON ohne Zeitstempel oder lokale Pfade |

Das Werkzeug prüft **Pläne**, keine vorhandenen MBR-/EBR-Sektoren. Es erkennt
deshalb noch keine beschädigte EBR-Kette auf einer Platte, keine falschen BPBs
und keine fragmentierten oder beschädigten Dateien. Ebenso prüft es noch
keine Aktivflags, profilspezifische OS-Grenzen, Journaltransaktionen oder
tatsächliche BIOS-Geometrie. NTFS- und weitere LBA-Profile folgen getrennt.
Die aufsteigende EBR-Reihenfolge ist eine Einschränkung dieses Planformats,
keine Aussage über alle zulässigen fremden Partitionstabellen.

## Befehle

Getestete lokale Werkzeuge: Python 3.12.14 und GNU Make 4.3 auf Linux.
Es gibt keine pip-Abhängigkeiten. Der CI-Workflow prüft Python 3.12 zusätzlich
auf Ubuntu 24.04 und Windows Server 2022; Ergebnisse stehen am jeweiligen PR.
Ein macOS-Lauf wurde noch nicht protokolliert.

| Befehl | Ergebnis |
| --- | --- |
| `make` / `make check` | Unittests und Textbericht des Referenzplans |
| `make layout` | Textbericht des Referenzplans |
| `make report` | Ausschließlich der JSON-Bericht auf stdout |
| `python3 -m unittest discover -s tests -v` | Tests ohne Make |
| `python3 tools/retroboot_layout.py profiles/rb-8g-chs255.json --json` | JSON-Bericht ohne Make |
| `make toolchain` | Festgelegte native Compiler für Linux x86_64 laden, prüfen und vorbereiten |
| `make abi` | Isolierte BIOS-Testdisketten und Binärdateien bauen |
| `make abi-check` | Zweimal bauen; Binärdateien, Abbilder und Manifeste vergleichen |
| `make boot-test` | Reproduzierbarkeit sowie erfolgreichen und zwei fehlerhafte BIOS-Starts prüfen |
| `make hdd` | Neue HDD-Testimages mit MBR, Verwaltungs-VBR, Bootstrap und Stage 2 bauen |
| `make hdd-check` | HDD-Artefakte zweimal bauen und vollständig vergleichen |
| `make hdd-test` | Wiederholungsbuild, 84 positive/negative HDD-Boots und 60 Menüansichten prüfen |
| `make menu-test` | Einmal bauen und gezielt die Menübedienung in QEMU prüfen |

Unter Windows können die direkten Python-Aufrufe mit `py -3.12` erfolgen.
Alle Befehle werden im Repository-Stamm ausgeführt. Fehler liefern Exitcode 1
und eine Meldung auf stderr; bei ungültigen Kommandozeilenoptionen verwendet
`argparse` Exitcode 2. Ein gültiger Plan liefert Exitcode 0.

Noch nicht vorhandene Ziele wie `make images`, `make run`
und `make release` werden nicht als erfolgreiche Platzhalter angeboten.
Die Namen in der Phase-1-Spezifikation bleiben die geplanten Schnittstellen.

## Planformat 1

Das JSON enthält `format_version`, `name`, `sector_size`, `disk_bytes`,
`geometry`, `primary` und `logical`. Die vollständige Referenz ist das
[eingecheckte Profil](../profiles/rb-8g-chs255.json).

- `geometry`: `cylinders` (1–1024), `heads` (1–255),
  `sectors_per_track` (1–63). Dies sind zu verifizierende BIOS-Werte.
- Jeder Partitionseintrag: freie eindeutige `id`, `role`, numerischer `type`,
  `start_lba` und `sectors`. Die Reihenfolge von `primary` bestimmt die Slots.
  Typen werden als dezimale JSON-Zahlen gespeichert, etwa 22 für `16h`.
- Primäre Rollen: `system` oder `extended`. Logische Rollen: `shared` oder
  `retroboot`. Ein logischer Eintrag enthält zusätzlich `ebr_lba`.
- FAT-Volumes: `fat` mit `bits` (16/32), `sectors_per_cluster` und optional
  `sectors_per_fat`. Ein erweiterter Container enthält kein `fat`-Objekt.
- Fehlendes `sectors_per_fat` lässt den Prüfer die kleinste ausreichende FAT
  berechnen. Ein expliziter Wert wird geprüft und beibehalten. `null` gilt
  nicht als gültige Zahl.

Für FAT16 gelten ein reservierter Sektor und 512 Root-Einträge, für FAT32
32 reservierte Sektoren und kein fester Rootbereich. Beide verwenden zwei
FATs. Diese Werte sind die derzeitige Formatierungsvorgabe, keine Erkennung
eines fremden Dateisystems. FAT32-Rootcluster, FSInfo, Backup-Bootsektoren und
Dateiinhalte werden erst beim späteren Formatter erzeugt und geprüft.

Der Bericht verwendet inklusive `end_lba`. Intern bleiben alle Intervalle
halboffen, sodass unmittelbar angrenzende Partitionen erlaubt sind.
`next_ebr_relative_lba: null` bezeichnet das Ende der geplanten Kette.
Es wird noch kein vollständiger binärer EBR-Datensatz ausgegeben.

## FAT-Größen aus v0.2

Die FAT32-Tabellen der Spezifikation enthalten etwas Reserve. Sie sind
ausreichend und werden im Referenzprofil ausdrücklich beibehalten:

| Volume | Geplante Sektoren/FAT | Rechnerisches Minimum | Datencluster mit geplanter FAT |
| --- | ---: | ---: | ---: |
| P2 | 3.075 | 3.069 | 392.819 |
| P3 | 4.079 | 4.072 | 521.088 |
| L3 | 3.875 | 3.868 | 495.026 |

Das Minimum berücksichtigt, dass beide FAT-Kopien selbst Platz belegen:
`Cluster = floor((Gesamtsektoren − reserviert − Rootsektoren − 2 × FATsektoren) / SektorenProCluster)`.
Eine FAT muss mindestens `Cluster + 2` Einträge fassen. Binäre Suche bestimmt
das Minimum; eine größere gültige FAT wird nicht stillschweigend verkleinert.

## Nachweisstand und nächste Schritte

Lokal bestanden: **83 Hosttests** einschließlich fester Referenzwerte,
FAT-Typgrenzen, Überlappungen, Überläufen, EBR-Kollisionen, ungültiger Geometrie,
fehlerhaften Eingaben und zweier bytegleicher JSON-Berichte. Die CLI-Tests
prüfen außerdem, dass der Layoutprüfer im Arbeitsverzeichnis keine Dateien
erzeugt. Hinzu kommen Prüfungen des binären Probe-Headers, der Größenbudgets,
der Ausgabeziele und der Auswertung der Emulatorergebnisse.
Die HDD-Ergänzung prüft außerdem den Erhalt der geschützten MBR-Bytes, binäre
EBR-Adressen und das Zusammensetzen einer FAT16-Datei bis zur maximalen
Stage-2-Größe von 48 KiB. Zwei Tests prüfen zusätzlich den VGA-Textdekoder.

Die native Probe startet unter QEMU 8.2.2/SeaBIOS erfolgreich. Zwei
Fehlervarianten (BSS nicht gelöscht, initialisierte Daten beschädigt) werden
erkannt. Alle Probe-Binärdateien und Abbilder sind in zwei getrennten Builds
bytegleich. Eine zusätzliche Linkerprobe weist nach, dass eine fehlende
Laufzeitfunktion den Build abbricht.

Der Benutzer hat zusätzlich die beiden erwarteten Diskettenmeldungen
`C entry, data, BSS, pointers and integer calls OK` und `RB ABI PASS`
zurückgemeldet. Rechner- und BIOS-Daten zu diesem Test sind noch nicht erfasst.

Der HDD-Ladeweg erreicht Stage 2 unter QEMU 8.2.2/SeaBIOS sowohl im kompakten
64-MiB-Image als auch bei den hohen LBAs des 8-GB-Referenzplans. Insgesamt
84 Bootfälle prüfen Erfolg, beschädigte Metadaten/Dateien, C-Startfehler, Menülogik und echte induzierte
Blocklesefehler. Quellimages bleiben unverändert; die I/O-Traces zeigen ab
dem MBR-Lesen keine Schreiboperationen. Die HDD-Artefakte sind in zwei Builds
bytegleich. Der Speichervertrag steht in `include/boot.inc` und der HDD-Anleitung.

Ohne EDD-Unterstützung verwendet derselbe MBR jetzt CHS über die mit AH=08h
abgefragte BIOS-Geometrie. Fehlerhafte Geometrie oder ein zu kleiner Bereich
werden abgewiesen. 37 EDD-/CHS-Testpaare lesen identische Sektorfolgen; die
im Speicher geladene Stage 2 stimmt in beiden Wegen Byte für Byte mit der
gebauten Datei überein. Auch Spur-/Zylinderwechsel und hohe Zylinderbits
werden im Emulator durchlaufen. Ein manueller VirtualBox-HDD-Start wurde
für den vorherigen Stand aus PR #3 als erfolgreich zurückgemeldet; Version,
Host-CPU und genaue VM-Einstellungen liegen dazu noch nicht vor.

Stage 2 führt inzwischen Open-Watcom-C/16 aus. Der Assembly-Startcode
initialisiert BSS und Stack und übergibt Laufwerk, BIOS-Leseweg und erreichbare
Sektorzahl. Fehlende BSS-Löschung, beschädigte Initialwerte, falscher Kontext
und ein zerstörtes Stack-Schutzwort führen zum erwarteten Abbruch. Für das
normale Image bestätigt ein RAM-Abzug zusätzlich die geladenen Dateibytes,
die C-BSS-Inhalte und das Schutzwort. Die gemeinsam verwendeten Helfer stehen
in `runtime/`; alle sieben Disketten-Binärdateien und -Images sind nach dieser
Umstellung bytegleich zum vorherigen Stand. Die vier C-HDD-Erfolgsmeldungen
aus PR #5 wurden inzwischen manuell bestätigt. Die genaue Plattform dieses
Tests wurde nicht erneut angegeben; der neue Menüstand ist noch manuell zu prüfen.

Das normale Image zeigt ein 80×25-Menü mit Auswahlbalken und drei
Informationsseiten. Pfeile, Enter, Esc, F2 und F8 funktionieren in vier
QEMU-Kampagnen: kompaktes und großes Layout jeweils mit EDD und CHS.
60 echte VGA-Textseiten werden nach emulierten Tastendrücken auf Texte,
MBR-Werte und Auswahlattribute geprüft. Dateibytes, BSS und Stack-Schutzwort
bleiben bei jeder Aktion gültig; es gibt keine Disk-Schreibzugriffe.
26 native C/16-Bedingungen prüfen Auswahl- und Timerlogik, auch Tageswechsel
und fehlerhafte Zeitquellen. Im normalen Menü ist der Timer ausgeschaltet,
weil noch keine registrierten Startprofile existieren.

Damit liegen T01-Nachweise für beide Artefaktgruppen sowie T02/T03/T04 und ein
abgegrenzter T05-Nachweis für den beschriebenen QEMU-Testaufbau vor.
Für T08 sind Bedienung und Zeitrechnung abgegrenzt geprüft; die Integration
mit gültigen Startprofilen und einem echten Startziel steht noch aus.
T06 erfordert später die Prüfung tatsächlich vorgefundener Partitionsstrukturen.
Die alten Zielmaschinen und weitere reale BIOS-Implementierungen bleiben
zusätzlich zu prüfen; die Emulatornachweise ersetzen diese Tests nicht.

Die nächsten Schritte sind:

1. Menübedienung manuell bestätigen, anschließend MBR-/EBR-Strukturen und
   Startziele lesend prüfen (T06); dann den Übergabevertrag mit eigenem Test-VBR
   nachweisen (T07). Erst mit gültigen Profilen die vollständige Startauswahl ergänzen.
2. Rechner-/BIOS-Daten der historischen Referenzmaschine erfassen und die
   Bootnachweise dort ergänzen.

Derzeit gibt es Disketten- und Festplattenprobestarts, aber keinen Installations- oder
Betriebssystemnachweis und kein zur Installation bestimmtes Image. Die
Spezifikation v0.2 bleibt als Stand der Phase 1 inhaltlich unverändert.
