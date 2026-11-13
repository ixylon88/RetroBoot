# Lesende MBR-/EBR-Prüfung

Stand: 10. November 2026. Erster Schritt von Phase 5; abgegrenzter T06-Nachweis.

F2 oder Enter auf **Partitionen** liest jetzt den MBR und die verketteten
EBR-Sektoren des Bootlaufwerks. Bei Erfolg zeigt das Menü die vier primären
Slots und bis zu 16 logische Einträge mit Flag, Typ, Start-LBA, Sektorzahl
und Adresse ihrer Partitionstabelle. P1–P4 bezeichnen primäre Slots, L1–L16
die gefundenen logischen Einträge. Diese Bezeichnungen sind keine OS-Namen.

Pro Seite werden acht Einträge angezeigt. Bild hoch/runter blättert;
F2 liest erneut und beginnt wieder auf Seite 1. Esc führt ins Hauptmenü,
F8 zu den Recovery-Hinweisen. Auch nach einem Scanfehler bleiben diese
Tasten verfügbar. Auf dem kompakten Testimage sind P1–P3 leer, P4 ist der
erweiterte Container und L1 das verborgene FAT16-Verwaltungsvolume.
Die separate [F3-Ansicht](VolumeHeaders.md) ergänzt inzwischen die lesende
FAT-BPB-Prüfung. F2 selbst untersucht weiterhin nur die Partitionstabellen.

## Was geprüft wird

| Bereich | Prüfung |
| --- | --- |
| MBR | Vollständiger Sektor, `55AA`, Disk-ID stimmt mit der Kopie aus dem Bootvorgang überein |
| Primäre Einträge | Nichtleere Bereiche beginnen nach LBA 0, sind nicht leer und liegen innerhalb der vom BIOS erreichbaren Sektoren |
| Arithmetik | Addition von relativen Adressen und Berechnung letzter Sektoren ohne 32-Bit-Überlauf |
| Belegung | Primäre Bereiche überschneiden sich nicht; der erweiterte Container wird dabei als primärer Bereich geprüft |
| Aktivflags | Nur `00h` oder `80h`; höchstens eine aktive primäre Datenpartition; Container und logische Einträge bleiben inaktiv |
| Typen | Datenkennungen `06/16`, `0E/1E`, `0B/1B`, `0C/1C`, `07/17`; höchstens ein erweiterter Container `05/0F` |
| Leere Einträge | Alle 16 Bytes müssen null sein; Restdaten werden als uneindeutig abgewiesen |
| EBR-Form | `55AA`; Dateneintrag in Slot 1, nächster EBR in Slot 2; Slots 3 und 4 leer |
| EBR-Adressen | Datenanfang relativ zum eigenen EBR, Weiterverweis relativ zur Containerbasis; auch die angegebene Linklänge muss im Container liegen |
| Logische Bereiche | Vollständig im Container, untereinander überschneidungsfrei, kein EBR-Sektor innerhalb eines Datenbereichs |
| Begrenzung | Besuchte EBR-Adressen werden gespeichert; Wiederholungen und mehr als 16 EBR-Sektoren beenden den Scan |

Ein EBR darf einen leeren Dateneintrag haben. Auch eine nicht monoton
aufsteigende EBR-Kette wird geprüft; eine besuchte Adresse darf jedoch
nicht erneut auftreten. Unbekannte Typen, einschließlich des GPT-Schutztyps
`EEh`, werden nicht als bekanntes Format geraten. Die Typenliste ist eine
Lesepolitik dieser Version, keine universelle Liste gültiger Fremdformate.
Insbesondere werden alte FAT12-/kleine FAT16-Typen `01h` und `04h` hier noch
nicht unterstützt.

Bei einem Fehler erscheint eine verständliche Ursache mit der LBA des
betroffenen Tabellensektors und gegebenenfalls dessen Eintragsnummer. Eine
unvollständig geprüfte Belegung wird nicht als erfolgreiche Tabelle gezeigt.
Ein noch nicht gelesener problematischer Weiterverweis nennt seine Ziel-LBA.
Fehler im früheren Bootladeweg behalten ihre bisherigen Halt-Meldungen.

## Leseweg und Speicher

`bios/disk.asm` passt den bestehenden Code aus `boot/disk.inc` an die
C/16-Aufrufschnittstelle an. Der beim Booten gewählte EDD-/CHS-Leseweg bleibt
erhalten. Jeder Aufruf liest einen Sektor, kontrolliert die Medien-/CHS-Grenze
und erlaubt höchstens drei Versuche. Der Scanner liest keine Volume-Inhalte
oder Bootsektoren von OS-Partitionen. Ohne Lesewiederholung benötigt er
höchstens 17 Sektoren: MBR und 16 EBRs.

`core/partitions.c` arbeitet mit einem Sektorlese-Callback. Das erlaubt die
gleichen Prüfungen sowohl mit dem echten BIOS-Leser als auch mit gezielt
präparierten Sektoren in den nativen Tests. Ergebnisstruktur (480 Byte),
Sektorpuffer und Menüzustand liegen auf dem bestehenden C-Stack. Der feste
Stackschutz, die BSS-Prüfung und das Dateibudget von 48 KiB bleiben erhalten.
Der Scanner enthält keine Schreibfunktion und führt keinen Chainload aus.

## Grenzen des Nachweises

Eine passende Disk-ID belegt nur die Übereinstimmung mit dem Bootvorgang.
Es gibt noch keine persistente Installationsidentität, keinen vollständigen
Layout-Fingerabdruck und keinen Schutz vor identischen oder kopierten IDs.
Ein erfolgreicher Scan ist eine Momentaufnahme der gelesenen Metadaten.

Ein Typbyte belegt weder ein gültiges FAT-/NTFS-Dateisystem noch eine
startfähige OS-Installation. Die F3-Prüfung ergänzt begrenzte FAT-BPB-
Plausibilität; der separate [T07-Test](Handoff.md) weist jetzt die Übergabe
an einen eigenen Test-VBR nach. OS-Profilzuordnung und Freigabe fehlen weiterhin.
Auch ein lesbar erfasster `0Fh`-Container
ist dadurch nicht für DOS 6.22 oder ältere NT-Versionen freigegeben.
Die eingefrorene Spezifikation v0.2 wird nicht geändert.

Bei CHS kennt das Programm die vom BIOS gemeldete Reichweite, keine davon
unabhängige Medienkapazität. QEMU/SeaBIOS meldet beim unverändert großen
Referenzimage mit automatischer Geometrie weniger erreichbare Sektoren als
für den gesamten erweiterten Container erforderlich. Der Loader kann das
Verwaltungsvolume trotzdem erreichen; der neue vollständige Strukturscan
weist P4 in dieser Konstellation korrekt ab. Diese Unterscheidung ist jetzt
ein eigener negativer Menütest.

Für die positiven Referenz-Menütests wird QEMUs logische BIOS-Geometrie
ausdrücklich mit `lcyls=973,lheads=255,lsecs=63` vorgegeben. Der Test vergleicht
die tatsächlich gelesenen Sektorfolgen von EDD und CHS; die Dateigröße und
die Belegung aus dem Referenzplan bleiben gleich. Die langen kompakten
Testketten liegen vollständig innerhalb der dort gemeldeten CHS-Reichweite.

Im lokalen QEMU-8.2.2-/SeaBIOS-Lauf ergaben sich:

| Referenz-CHS-Test | Gemeldete erreichbare Sektoren | Ergebnis für P4 bis LBA 15.615.179 |
| --- | ---: | --- |
| Automatische Geometrie | 15.599.115 | Abgewiesen |
| Vorgegebene logische Geometrie | 15.615.180 | Strukturprüfung erfolgreich |

## Prüfungen und Artefakte

```sh
make toolchain
make check
make hdd-test
make hdd-ui-test RB_LANGUAGE=de
```

`make scan-test` baut einmal und prüft gezielt die neuen Scanner-Szenarien.
Mit bereits gebauten Images ist auch ein direkter Aufruf möglich:

```sh
python3 tools/test_scan.py --qemu /pfad/qemu-system-i386 --bios /pfad/bios-256k.bin
```

- 130 Hosttests, darunter der Erhalt aller Loaderdaten in den Scanner-Fixtures
  und die Kodierungs-/Feldbreitenprüfungen für beide Menükataloge.
- 51 Bedingungen im tatsächlichen C/16-Parser, jeweils nach einem EDD- und
  CHS-Start. Darunter sind andere Disk-ID, fehlende Signaturen, falsche Typen,
  Aktivflags, Überlappungen, Überläufe, leere Einträge und rückwärts laufende
  EBR-Ketten. Der letzte zulässige LBA `FFFFFFFFh` wird ohne Überlauf geprüft.
- Insgesamt 102 HDD-Bootfälle mit 46 EDD-/CHS-Paaren und bytegleichen
  Wiederholungsbuilds; die vorhandenen 26 Auswahl-/Timerbedingungen bleiben erhalten.
- Fünf normale Menükampagnen mit insgesamt 75 Bildschirmzuständen,
  einschließlich der absichtlich zu kleinen automatischen Referenz-CHS-Geometrie.
- 16 Scanner-Fixtures, jeweils mit EDD und CHS: 32 Kampagnen und 204
  Bildschirmzustände. Dazu gehören echte permanente und einmalige
  Blocklesefehler am EBR, eine Schleife, Daten-/EBR-Kollisionen, 16 gültige
  EBRs mit drei Anzeigeseiten und ein abgewiesener 17. EBR.

Jede Kampagne prüft zweimaliges Einlesen, Esc/F8 nach Fehlern, die exakte
Sektorfolge einschließlich Wiederholungen und ausbleibende Schreibzugriffe.
VGA-Zeichen und Attribute, geladene Dateibytes, BSS und Stackschutz werden
im Gast-RAM geprüft. Vollständige Image-Hashes bleiben gleich.
Die allgemeinen Menü- und Scanner-Kampagnen laufen für Englisch und Deutsch,
zusammen 558 Bildschirmzustände. Alle sichtbaren übersetzten Texte werden
geprüft, einschließlich der konkreten Fehlermeldung mit Umlauten und `ß`.
Mit den zusätzlichen 318 F3- und 185 T07-Zuständen je Sprache sind es insgesamt 1.564.
Die [Sprachanleitung](Languages.md) beschreibt die Build-Auswahl.

`build/scan/scan-results.json` entsteht erst nach dem vollständigen Erfolg.
Screenshots, VGA-/RAM-Abzüge, Textseiten, BIOS- und I/O-Protokolle liegen
daneben und werden im CI-Artefakt unter `scan/` bereitgestellt. Die absichtlich
fehlerhaften Images gehören nicht zum Download; dieser enthält das normale
kompakte englische Menüimage unter `hdd/retroboot-hdd.img`. Die deutsche
Entsprechung liegt unter `hdd-de/retroboot-hdd.img`, ihre Scanner-Nachweise
unter `scan-de/` beziehungsweise lokal `build/scan-de/`.

Formatgrundlage: Microsoft, *Windows NT Server Resource Guide 4.0*, Kapitel 3,
Abschnitt „Extended Partitions“ ([Originaldokument auf Archivspiegel](https://bitsavers.trailing-edge.com/pdf/microsoft/resource_kits/Windows_NT_4.0_Resource_Kit_1996/097-0001648_Windows_NT_4.0_Server_Resource_Guide_1996.pdf)).
