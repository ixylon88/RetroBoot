# Entwicklung – Hostprüfungen und erste Bootlader

Updated: 11 November 2026.

Die [BIOS-/ABI-Probe](ABI_Probe.md) ergänzt den Layoutprüfer um einen echten
Real-Mode-Start mit Open-Watcom-C/16 und NASM. Die folgende Beschreibung des
Layoutprüfers bleibt gültig; er selbst erzeugt weiterhin nur Berichte.
Hinzu kommt der [Festplattenladeweg](HDD_Boot.md) über BIOS-EDD/CHS und FAT16
bis zum C-Einstieg mit eigenem Startcode.
Darauf baut jetzt das [lesende Textmenü](Menue.md) auf.
Die [MBR-/EBR-Prüfung](Partitionen.md) ergänzt die Untersuchung tatsächlich
gelesener Partitionstabellen im Menü; der Host-Layoutprüfer bleibt davon getrennt.
Die neue [F3-Ansicht](VolumeHeaders.md) prüft anschließend FAT16-/FAT32-
Volume-Header lesend, ohne damit Dateisystemintegrität oder Startfähigkeit zu bestätigen.
Der separate [T07-Test](Handoff.md) ergänzt jetzt die kontrollierte Übergabe
an einen eigenen Test-Bootsektor; ein Original-OS wird weiterhin nicht gestartet.
Die [Sprachanleitung](Languages.md) beschreibt englische und deutsche Builds
mit gemeinsamen Programmquellen und CP437-Zeichen einschließlich `ß`.
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
| `make hdd` | Englische HDD-Testimages mit MBR, Verwaltungs-VBR, Bootstrap und Stage 2 bauen |
| `make hdd RB_LANGUAGE=de` | Deutsches Menü mit Umlauten und Eszett; Ausgabe unter `build/hdd-de/` |
| `make hdd-ui-test RB_LANGUAGE=de` | Deutschen Wiederholungsbuild und alle 2.480 UI-Zustände prüfen |
| `make hdd-check` | HDD-Artefakte zweimal bauen und vollständig vergleichen |
| `make hdd-test` | Repeat build, 98 boot cases and 2,816 keyboard/VGA states for the selected language |
| `make menu-test` | Einmal bauen und gezielt die Menübedienung in QEMU prüfen |
| `make scan-test` | Einmal bauen und gezielt Scannerfehler, Wiederholungen und mehrseitige Tabellen prüfen |
| `make volume-test` | Einmal bauen und gezielt FAT-Header, Lesefehler und F3-Bedienung prüfen |
| `make config-test` | Einmal bauen und F5-Konfigurationsdiagnose samt A/B-Auswahl prüfen |
| `make visibility-test` | Build once and verify F7 current/intended primary-partition previews |
| `make state-test` | Build once and verify F6 record bindings, phases and the current VBR |
| `make handoff-test` | Einmal bauen und die Übergabe an den Test-VBR einschließlich Abweisungen prüfen |

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

Lokal bestanden: **121 Hosttests** einschließlich fester Referenzwerte,
FAT-Typgrenzen, Überlappungen, Überläufen, EBR-Kollisionen, ungültiger Geometrie,
fehlerhaften Eingaben und zweier bytegleicher JSON-Berichte. Die CLI-Tests
prüfen außerdem, dass der Layoutprüfer im Arbeitsverzeichnis keine Dateien
erzeugt. Hinzu kommen Prüfungen des binären Probe-Headers, der Größenbudgets,
der Ausgabeziele und der Auswertung der Emulatorergebnisse.
Die HDD-Ergänzung prüft außerdem den Erhalt der geschützten MBR-Bytes, binäre
EBR-Adressen und das Zusammensetzen einer FAT16-Datei bis zur maximalen
Stage-2-Größe von 48 KiB. Zwei Tests prüfen zusätzlich den VGA-Textdekoder.
Die Scanner-Fixtures erhalten den Ladeweg und die MBR-Identität; ihre
zusätzlichen Test-EBRs liegen im freien Bereich hinter dem Verwaltungsvolume.
Sieben Katalogtests prüfen außerdem CP437-Zeichen einschließlich `ß`,
C-Escapes, Feldbreiten, Schlüsselmengen und die Trennung der Sprach-Builds.
Vier weitere Tests prüfen die Volume-Fixtures: Loadererhalt, feste BPB-Werte,
überschneidungsfreie Bereiche und abgewiesene Eingaben.
Fünf T07-Hosttests ergänzen Zielbindung, Fixture-Erhalt und die unabhängige
Auswertung der geladenen Bytes und Eingangsregister.

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
98 Bootfälle prüfen Erfolg, beschädigte Metadaten/Dateien, C-Startfehler, Menü-/Parserlogik und echte induzierte
Blocklesefehler. Quellimages bleiben unverändert; die I/O-Traces zeigen ab
dem MBR-Lesen keine Schreiboperationen. Die HDD-Artefakte sind in zwei Builds
bytegleich. Der Speichervertrag steht in `include/boot.inc` und der HDD-Anleitung.

Ohne EDD-Unterstützung verwendet derselbe MBR jetzt CHS über die mit AH=08h
abgefragte BIOS-Geometrie. Fehlerhafte Geometrie oder ein zu kleiner Bereich
werden abgewiesen. 44 EDD-/CHS-Testpaare lesen identische Sektorfolgen; die
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
Tests wurde nicht erneut angegeben. Am 10. November wurden auch Menü (PR #6)
und Scanner (PR #7) manuell bestätigt, ohne zusätzliche Plattformdaten.
Auch die Sprachvarianten aus PR #8 wurden inzwischen manuell bestätigt,
ohne neue Plattformdaten. Auch F3 aus PR #9 wurde manuell bestätigt.
Auch T07 aus PR #10 wurde manuell bestätigt, ohne neue Plattformdaten.
F5 and F6 were reported complete. German [F7](Visibility.md) screenshots
were confirmed under VirtualBox; the English [F9 test](ProfileTest.md) is pending.

Das normale Image zeigt ein 80×25-Menü mit Auswahlbalken und drei
Informationsseiten. Pfeile, Enter, Esc, F2 und F8 funktionieren in fünf
QEMU-Kampagnen: kompaktes und großes Layout jeweils mit EDD und CHS sowie
ein erwarteter Geometriefehler. 75 echte VGA-Textseiten werden nach emulierten
Tastendrücken auf Texte, Partitionswerte und Auswahlattribute geprüft. Dateibytes, BSS und Stack-Schutzwort
bleiben bei jeder Aktion gültig; es gibt keine Disk-Schreibzugriffe.
26 native C/16-Bedingungen prüfen Auswahl- und Timerlogik, auch Tageswechsel
und fehlerhafte Zeitquellen. Im normalen Menü ist der Timer ausgeschaltet,
weil noch keine unabhängig geprüfte OS-Startfreigabe besteht.

F2 liest inzwischen den MBR und eine begrenzte EBR-Kette. 51 native C/16-
Bedingungen prüfen die Strukturlogik, darunter Disk-ID-Vergleich, Überläufe,
Überlappungen, falsche Typen und Schleifen. Weitere 32 QEMU-Kampagnen prüfen
204 Bildschirmzustände mit echten Scannerfehlern, I/O-Wiederholungen und
Blättern über drei Seiten. Bei Fehlern bleiben Menü und Recovery-Hinweise
erreichbar; unvollständige Belegungen werden nicht als Erfolg angezeigt.
F3 ergänzt die begrenzte FAT16-/FAT32-Headerprüfung. 114 native C16-Bedingungen
prüfen BPB-Grenzen, Lesegrenzen und die neuen 32-Bit-Rechenhelfer. Weitere
43 Kampagnen je Sprache prüfen 318 Volume-Zustände einschließlich tatsächlicher
Lesefehler. Die 75 allgemeinen, 204 Scanner- und 318 Volume-Zustände laufen
für Englisch und Deutsch. Die neuen T07-Tests ergänzen je Sprache 43 Kampagnen
und 185 Zustände. F5 ergänzt 63 Kampagnen mit 678 Zuständen je Sprache;
F6 adds 65 campaigns and 650 states per language; F7 adds 37 campaigns and
370 states. The F9 checked-profile test adds 37 campaigns and 336 states,
giving 5,632 states across both languages. Jede Sprache
wird zweimal bytegleich gebaut; die 98 gemeinsamen Bootfälle laufen in CI
einmal mit Englisch.

Die automatische CHS-Geometrie des großen QEMU-Images reicht für den
Verwaltungsbereich, aber nicht für den gesamten erweiterten Container.
Der Scanner weist das korrekt ab. Die positiven Referenz-Menütests verwenden
eine ausdrücklich vorgegebene logische BIOS-Geometrie; Belegung und Imagegröße
bleiben die des eingefrorenen Referenzplans. Details stehen in der Partitionsanleitung.

Damit liegen T01-Nachweise für beide Artefaktgruppen sowie T02/T03/T04 und ein
abgegrenzter T05-Nachweis für den beschriebenen QEMU-Testaufbau vor.
Für T08 sind Bedienung und Zeitrechnung abgegrenzt geprüft; die Integration
mit gültigen Startprofilen und einem echten Startziel steht noch aus.
T06 ist für die beschriebenen MBR-/EBR-Strukturfehler abgegrenzt geprüft.
T07 ist mit einem eigenen VBR für den beschriebenen QEMU-Aufbau nachgewiesen:
29 native Vorprüfungen sowie erfolgreiche und absichtlich fehlerhafte echte
Übergaben kontrollieren Ladeadresse, Register, Stack, Zielbytes und Partitionszeiger.
Die FAT-BPB-Plausibilität ist nun zusätzlich im beschriebenen Umfang geprüft.
F5 liest nun persistente Konfigurationskopien mit Disk-ID-/Layoutbindung und
prüft Profilbeschreibungen. F6 adds independent installation identities and a
current-VBR cross-check. F7 adds a read-only current/intended primary-table
preview with DOS/Win9x and NT-group rules. Allgemeine Dateisystemintegrität und eine Freigabe echter OS-Ziele fehlen weiterhin; eine passende Typkennung oder ein plausibler Header
reichen dafür nicht.
Die alten Zielmaschinen und weitere reale BIOS-Implementierungen bleiben
zusätzlich zu prüfen; die Emulatornachweise ersetzen diese Tests nicht.

Die nächsten Schritte sind:

1. Manually verify the [F7 primary-table preview](Visibility.md), then prepare
   controlled original-OS validation and recovery-backed writes. A matching
   preview, declared profile status or fixed T07 binding does not authorize
   an OS start.
2. Rechner-/BIOS-Daten der historischen Referenzmaschine erfassen und die
   Bootnachweise dort ergänzen.

Derzeit gibt es Disketten- und Festplattenprobestarts, aber keinen Installations- oder
Betriebssystemnachweis und kein zur Installation bestimmtes Image. Die
Spezifikation v0.2 bleibt als Stand der Phase 1 inhaltlich unverändert.

The F7 increment is checked locally with QEMU 10.0.13/SeaBIOS on
`pc-i440fx-8.2`, CPU `486`, 16 MiB RAM. CI records its own emulator and ROM
versions. Four additional host tests verify fixture preservation, independent
target bindings, isolated target faults and rejection of stale F7 screen data.
