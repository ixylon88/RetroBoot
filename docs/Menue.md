# Textmenü: Bedienung und Nachweisstand

Stand: 10. November 2026. Menü aus Phase 4 mit lesender Partitionsprüfung aus Phase 5.

Das normale `retroboot-hdd.img` öffnet nach den vier C-/Stage-2-Erfolgsmeldungen
ein blaues 80×25-Textmenü. Der Auswahlbalken ersetzt den blinkenden Cursor.
Das Hauptmenü bietet drei Informationsseiten und noch keine freigegebenen
OS-Starts. F5 liest gespeicherte Profilbeschreibungen zur Diagnose.
Deshalb steht ausdrücklich **Automatic boot: off** beziehungsweise
**Automatischer Start: aus** im Hauptmenü. Englisch ist Standard;
`RB_LANGUAGE=de` wählt Deutsch mit Umlauten und `ß`.
Die [Sprachanleitung](Languages.md) beschreibt Kodierung und Ausgabepfade.

## Bedienung

| Taste | Wirkung |
| --- | --- |
| Pfeil hoch / herunter | Informationsseite auswählen; am Listenende umlaufen |
| Enter | Ausgewählte Informationsseite öffnen |
| Esc | Zum Hauptmenü zurückkehren; Auswahl bleibt erhalten |
| F2 | MBR und EBR-Kette erneut lesen und prüfen; Partitionen ab Seite 1 anzeigen |
| F3 | Tabellen erneut prüfen und einen FAT-Volume-Header untersuchen; auf der Volume-Seite den aktuellen Eintrag aktualisieren |
| Pfeil links / rechts | Auf der Volume-Seite zum vorherigen/nächsten Dateneintrag wechseln; leere Slots und Container überspringen |
| Bild hoch / herunter | Auf der Partitionsseite blättern; maximal acht Einträge pro Seite |
| F7 | Current/intended primary types and active flags; no writes or target execution |
| F6 | Independent installation-state records and current-VBR cross-check; no target execution |
| F5 | Konfigurationskopien und gespeicherte Profilbeschreibungen frisch prüfen und anzeigen |
| F8 | Von jeder Seite zu den Recovery-Hinweisen wechseln |

Andere Tasten starten keine Aktion. Auf einer Informationsseite verändern
Pfeile hoch/herunter und Enter die Hauptmenüauswahl nicht. Die Hinweise nennen die derzeit
verfügbare Funktion; F8 bietet noch keine Wiederherstellung an.

| Seite | Angezeigte Daten |
| --- | --- |
| Systeminformationen | BIOS-Laufwerk, tatsächlich gewählter Leseweg EDD/CHS, erreichbare Sektorzahl, Disk-ID und gegebenenfalls BIOS-CHS-Geometrie |
| Partitionen | Vier primäre Slots und bis zu 16 logische Einträge mit Flag, Typ, Start-LBA, Sektorzahl und Tabellen-LBA; Werte außer den Eintragsnummern sind hexadezimal |
| Recovery-Hinweise | Hinweis auf die noch fehlende Wiederherstellung und die verfügbaren Informationsseiten |
| Volume-Bootsektor (F3) | Partition, Typ, VBR-LBA und Prüfergebnis; nur bei Erfolg FAT-Typ, Clustergröße, Sektoren, Clusterzahl und Datenanfang |

Die Systeminformationen stammen weiterhin aus dem Bootvorgang. Die
Partitionsseite liest dagegen die Tabellensektoren frisch ein und prüft
unter anderem Grenzen, Überlappungen, Typen, Disk-ID und EBR-Schleifen.
Leere primäre Slots werden mit ihren Nullwerten angezeigt. Ein Fehler zeigt
Ursache und betroffene LBA; Esc und F8 bleiben bedienbar. Aus einem Typbyte
wird kein Betriebssystemname oder gültiges Dateisystem abgeleitet. Der
[Scanner-Nachweis und seine Grenzen](Partitionen.md) sind getrennt beschrieben.
Die zusätzliche [F3-Ansicht](VolumeHeaders.md) liest nach erfolgreicher
Tabellenprüfung einen Volume-Header. Links/Rechts verwendet die zuletzt
geprüfte Belegung; F3 liest auch die Tabellen erneut. Fehler lassen abgeleitete
Werte leer. Ein plausibler BPB gibt keinen OS-Start frei; NTFS bleibt ungeprüft.

Bei CHS ist die Sektorzahl die vom BIOS adressierbare Reichweite, keine
unabhängig gemessene Mediengröße. Bei EDD wird keine CHS-Geometrie erfunden;
die Anzeige erklärt, dass sie nicht abgefragt wurde.

## Manueller Test

Das kompakte Image aus dem erfolgreichen Workflow **HDD BIOS boot** wie in
der [HDD-Anleitung](HDD_Boot.md) beschrieben in QEMU oder einer leeren
VirtualBox-BIOS-VM starten. Das Artefakt enthält Englisch unter `hdd/` und
Deutsch unter `hdd-de/`. Für ein neues Image eine neue VDI erzeugen;
eine früher konvertierte VDI enthält weiterhin den alten Programmstand.

1. Das Hauptmenü zeigt keine Startprofile und keinen Countdown.
2. Pfeile bewegen den Balken über alle drei Zeilen und über den Listenrand.
3. Enter öffnet die gewählte Seite, Esc bringt das Hauptmenü zurück.
4. F2 zeigt im kompakten Image fünf Einträge: P1–P3 leer, P4 Typ `05`,
   L1 Typ `16`. Das Ergebnis lautet „Structure checked; no OS boot authorized.“
   beziehungsweise „Struktur geprüft; kein OS-Start freigegeben.“
5. F8 zeigt, dass Wiederherstellung noch nicht verfügbar ist.
6. Unter Systeminformationen stehen Laufwerk `80` und der verwendete Leseweg.
7. F3 zeigt L1, Typ `16`, VBR-LBA `0000007E`, FAT16 und 2.048 Byte pro
   Cluster. Die vollständigen Sollwerte stehen in der Volume-Anleitung.
   Links/Rechts bleibt bei diesem einzigen Volume; F3, F2, Esc und F8 bleiben bedienbar.

Ein Testprotokoll enthält nach Möglichkeit VM-/BIOS-Version oder Rechnermodell
und die beobachtete Leseart. Menü (PR #6) und Scanner (PR #7) wurden am
10. November manuell als erfolgreich bestätigt; zusätzliche Plattformdaten
wurden nicht angegeben. Auch die Sprachvarianten aus PR #8 wurden inzwischen
manuell bestätigt, ohne neue Plattformdaten. F3 aus PR #9 wurde ebenfalls bestätigt. Auch das separate
[T07-Testimage](Handoff.md) aus PR #10 wurde manuell bestätigt, ohne neue
Plattformdaten. F5 and F6 were reported complete. German [F7](Visibility.md) screenshots
were confirmed under VirtualBox; the English [F9 test](ProfileTest.md) is pending.

## Implementierung und Grenzen

`core/menu.c` zeichnet die Seiten. `bios/ui.asm` stellt den VGA-Modus 03h ein,
schreibt Zeichen und Attribute nach `B800:0000`, fragt die BIOS-Tastatur ab
und liest die BIOS-Ticks aus der BDA. Die Ausgabefunktionen begrenzen ihre
Schreibzugriffe auf 2.000 Textzellen. Zwischen Eingaben wartet die CPU mit
`STI; HLT` auf einen Interrupt. Debugmeldungen gehen nur an Port `E9h` und
überschreiben deshalb keine Menütexte.

Menüzustand, die 520-Byte-Kopie von Geometrie und MBR sowie das 480-Byte-
Scannergebnis sowie das neue 24-Byte-Volume-Ergebnis liegen auf dem eigenen
C-Stack. Der bestehende Stage-2-Speichervertrag, das Schutzwort und die
BSS-Prüfungen bleiben erhalten. Das Image enthält weder einen Disk-Schreibpfad
noch eine OS-Übergabe. Nur das separate T07-Testimage ergänzt F4 im
Hauptmenü und einen nicht zurückkehrenden Sprung zum eigenen Test-VBR. Die Spezifikation v0.2 bleibt unverändert.

`core/menu_model.c` trennt Auswahl und Zeitrechnung von BIOS und Anzeige.
Das Modell kann bis zu acht freigegebene Einträge verwalten und gibt nur
einen ausgewählten Index zurück. Eine ungültige Standardwahl schaltet den
Timer aus; eine ersatzweise Auswahl wird nicht automatisch zum Standard.
Jede gelieferte Taste, auch eine unbekannte oder der BIOS-Wert `0000h`,
stoppt den Timer. Ablauf liefert den Index genau einmal. Tageswechsel wird
berücksichtigt, eine stehende Uhr löst nichts aus. Ungültige Tickwerte,
eine rückläufige Uhr außerhalb des Tageswechsels oder ein Abstand von mehr
als 182 Ticks zwischen Aufrufen verwerfen den Countdown. Das Modell nimmt
höchstens 1.093 Countdown-Ticks an; eine Konfigurationsoberfläche gibt es noch nicht.

**Im normalen Menü ist der Timer immer aus.** Die Modelltests belegen noch
keinen zeitgesteuerten OS-Start. Ein späteres Startprofil muss erst zusammen
mit gültiger Konfiguration, Installationsstatus und Zielprüfung freigegeben
werden. Damit liegt ein abgegrenzter T08-Nachweis für Bedienung und
Zeitrechnung vor; die vollständige Startintegration bleibt offen.

## Automatische Prüfungen

```sh
make toolchain
make check
make hdd-test
make hdd-ui-test RB_LANGUAGE=de
```

`make hdd-test` baut zweimal, prüft 98 positive/negative HDD-Startfälle und
führt anschließend Menü-, Scanner-, Volume- und Übergabeprüfungen aus. `make menu-test` baut einmal und
prüft gezielt das Menü. Bereits gebaute Images lassen sich ohne Neubau prüfen:

```sh
python3 tools/test_menu.py --qemu /pfad/qemu-system-i386 --bios /pfad/bios-256k.bin
```

- 26 Bedingungen der tatsächlichen C/16-Auswahl-/Timerlogik laufen im
  `hdd-menu-model`-Image, jeweils mit EDD und CHS. Darunter sind leere und
  gesperrte Listen, ungültiger Standard, Umlaufen, Enter, Tastendruck beim
  Ablauf, Tageswechsel und fehlerhafte Uhren.
- Die normalen Images `retroboot-hdd.img` und `retroboot-reference.img`
  laufen jeweils mit EDD und CHS. Der positive Referenztest verwendet eine
  festgelegte ausreichende logische BIOS-Geometrie. Eine fünfte Kampagne
  prüft die korrekte Ablehnung der zu kleinen automatischen CHS-Reichweite.
  QMP sendet echte emulierte PS/2-Tastendrücke: je 15 Zustände, insgesamt 75 VGA-Textseiten.
- Die Prüfung liest Zeichen und Attribute direkt aus dem VGA-Speicher:
  Auswahlbalken, Texte, BIOS-Kontext sowie primäre und logische Einträge müssen
  stimmen. Die Tabellenwerte werden mit den Bytes des Quellimages verglichen.
- Nach jeder Aktion werden Stage-2-Dateibytes, C-BSS und Stack-Schutzwort
  erneut im RAM geprüft. Die Disk-Traces dürfen keine Schreiboperation
  enthalten; vollständige SHA-256-Werte der Images bleiben gleich. Beide
  Lesewege müssen je Image dieselbe Sektorfolge liefern.

Ergebnisse stehen in `build/menu/menu-results.json`, Textseiten, VGA-/RAM-Abzüge,
ausgewählte echte QEMU-Screenshots und I/O-Traces daneben. Diese Nachweise
kommen zusammen mit dem kompakten Image ins CI-Artefakt. Die zusätzlichen
Hosttests prüfen den VGA-Dekoder und FAT-Clusterketten bis zur maximalen
Stage-2-Dateigröße von 48 KiB. Zusammen mit den Scanner-Fixtures und sieben
Katalogprüfungen, vier Volume-Fixture-, fünf Übergabe- und sechs Konfigurationstests sowie fünf State- und vier Visibility-Tests. Four checked-profile tests bring
the host total to 121. Beide Sprachen durchlaufen
dieselben Menü- und Scanner-Kampagnen, zusammen 558 Bildschirmzustände. Die
deutschen Nachweise liegen unter `build/menu-de/` und `build/scan-de/`.
Die zusätzlichen 32 Scanner-Kampagnen je Sprache mit 204 Bildschirmzuständen
stehen in der [Partitionsprüfung](Partitionen.md).
Weitere 43 Volume-Kampagnen je Sprache prüfen je 318 Zustände, insgesamt
mit Menü/Scanner also 1.194 UI-Zustände. Ihre Nachweise liegen unter `build/volume/` und
`build/volume-de/`; Details stehen in der [Volume-Anleitung](VolumeHeaders.md).
43 T07-Kampagnen ergänzen je Sprache 185 Zustände; 63 F5-Kampagnen ergänzen
678 Konfigurationszustände. F6 adds 650, F7 adds 370 and F9 adds 336 states per language, giving 5,632
states across both languages. F4 bleibt im normalen Image ohne Wirkung.

Teststeuerung: [QEMU QMP – send-key und screendump](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html).
