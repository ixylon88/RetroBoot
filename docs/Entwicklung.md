# Entwicklung – Phase 2: Hostprüfungen und BIOS-/ABI-Probe

Stand: 9. November 2026.

Die [BIOS-/ABI-Probe](ABI_Probe.md) ergänzt den Layoutprüfer um einen echten
Real-Mode-Start mit Open-Watcom-C/16 und NASM. Die folgende Beschreibung des
Layoutprüfers bleibt gültig; er selbst erzeugt weiterhin nur Berichte.

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

Lokal bestanden: **58 Hosttests** einschließlich fester Referenzwerte,
FAT-Typgrenzen, Überlappungen, Überläufen, EBR-Kollisionen, ungültiger Geometrie,
fehlerhaften Eingaben und zweier bytegleicher JSON-Berichte. Die CLI-Tests
prüfen außerdem, dass der Layoutprüfer im Arbeitsverzeichnis keine Dateien
erzeugt. Hinzu kommen Prüfungen des binären Probe-Headers, der Größenbudgets,
der Ausgabeziele und der Auswertung der Emulatorergebnisse.

Die native Probe startet unter QEMU 8.2.2/SeaBIOS erfolgreich. Zwei
Fehlervarianten (BSS nicht gelöscht, initialisierte Daten beschädigt) werden
erkannt. Alle Probe-Binärdateien und Abbilder sind in zwei getrennten Builds
bytegleich. Eine zusätzliche Linkerprobe weist nach, dass eine fehlende
Laufzeitfunktion den Build abbricht.

Damit liegt ein abgegrenzter T01-Nachweis für die **Probe-Artefakte** vor.
Der produktive MBR-/VBR-/FAT-Ladeweg existiert noch nicht; dessen vollständiger
T01- und T03-Nachweis bleibt offen. T06 erfordert später die Prüfung realer
Partitionsstrukturen. Der Speichervertrag ist für die Probe festgelegt;
die Bereiche und Schnittstellen der Produktionslader werden im nächsten
Schritt ergänzt. Phase 2 wird deshalb nicht pauschal als abgeschlossen markiert.

Die nächsten Schritte sind:

1. Den Speichervertrag um die Produktionslader und deren Übergaben erweitern.
2. Darauf den minimalen MBR → Verwaltungs-VBR → Bootstrap → Stage-2-Ladeweg
   mit sichtbarer Bootmeldung und Größenprüfungen bauen.
3. Reproduzierbare Testimages in QEMU starten, EDD/CHS und Fehlerpfade prüfen;
   danach die historische Referenzmaschine vermessen.

Derzeit gibt es einen BIOS-Probestart, aber keinen Installations- oder
Betriebssystemnachweis und kein zur Installation bestimmtes Image. Die
Spezifikation v0.2 bleibt als Stand der Phase 1 inhaltlich unverändert.
