# Textmenü: Bedienung und Nachweisstand

Stand: 10. November 2026. Erster bedienbarer Teil von Phase 4.

Das normale `retroboot-hdd.img` öffnet nach den vier C-/Stage-2-Erfolgsmeldungen
ein blaues 80×25-Textmenü. Der Auswahlbalken ersetzt den blinkenden Cursor.
Es gibt drei Informationsseiten, noch keine registrierten Startprofile.
Deshalb steht ausdrücklich **Automatischer Start: aus** im Hauptmenü.

## Bedienung

| Taste | Wirkung |
| --- | --- |
| Pfeil hoch / herunter | Informationsseite auswählen; am Listenende umlaufen |
| Enter | Ausgewählte Informationsseite öffnen |
| Esc | Zum Hauptmenü zurückkehren; Auswahl bleibt erhalten |
| F2 | Von jeder Seite zu den vier primären MBR-Einträgen wechseln |
| F8 | Von jeder Seite zu den Recovery-Hinweisen wechseln |

Andere Tasten starten keine Aktion. Auf einer Informationsseite verändern
Pfeile und Enter die Auswahl nicht. Die Hinweise nennen die derzeit
verfügbare Funktion; F8 bietet noch keine Wiederherstellung an.

| Seite | Angezeigte Daten |
| --- | --- |
| Systeminformationen | BIOS-Laufwerk, tatsächlich gewählter Leseweg EDD/CHS, erreichbare Sektorzahl, Disk-ID und gegebenenfalls BIOS-CHS-Geometrie |
| MBR-Partitionen | Alle vier primären Slots mit Aktivflag, Typ, Start-LBA und Sektorzahl; die Werte sind hexadezimal |
| Recovery-Hinweise | Hinweis auf die noch fehlende Wiederherstellung und die verfügbaren Informationsseiten |

Die MBR-Daten stammen aus dem Sektor, der beim Start bereits in den Speicher
geladen wurde. Das Menü liest keine weiteren Plattensektoren. Leere Slots
werden mit ihren Nullwerten angezeigt. Aus einem Typbyte wird weder ein
Betriebssystemname noch die Startfähigkeit abgeleitet. Das ist noch kein
MBR-/EBR-Scanner oder vollständiger Partition Manager nach T06.

Bei CHS ist die Sektorzahl die vom BIOS adressierbare Reichweite, keine
unabhängig gemessene Mediengröße. Bei EDD wird keine CHS-Geometrie erfunden;
die Anzeige erklärt, dass sie nicht abgefragt wurde.

## Manueller Test

Das kompakte Image aus dem erfolgreichen Workflow **HDD BIOS boot** wie in
der [HDD-Anleitung](HDD_Boot.md) beschrieben in QEMU oder einer leeren
VirtualBox-BIOS-VM starten. Für ein neues Image eine neue VDI erzeugen;
eine früher konvertierte VDI enthält weiterhin den alten Programmstand.

1. Das Hauptmenü zeigt keine Startprofile und keinen Countdown.
2. Pfeile bewegen den Balken über alle drei Zeilen und über den Listenrand.
3. Enter öffnet die gewählte Seite, Esc bringt das Hauptmenü zurück.
4. F2 zeigt vier Slots. Im kompakten Image sind 1–3 leer; Slot 4 hat Typ `05`.
5. F8 zeigt, dass Wiederherstellung noch nicht verfügbar ist.
6. Unter Systeminformationen stehen Laufwerk `80` und der verwendete Leseweg.

Bitte bei einer Rückmeldung auch VM-/BIOS-Version oder Rechnermodell und die
beobachtete Leseart nennen. Das neue Menü ist bislang automatisch in QEMU
geprüft; der manuell bestätigte C-Einstieg aus PR #5 ist die Vorgängerversion.

## Implementierung und Grenzen

`core/menu.c` zeichnet die Seiten. `bios/ui.asm` stellt den VGA-Modus 03h ein,
schreibt Zeichen und Attribute nach `B800:0000`, fragt die BIOS-Tastatur ab
und liest die BIOS-Ticks aus der BDA. Die Ausgabefunktionen begrenzen ihre
Schreibzugriffe auf 2.000 Textzellen. Zwischen Eingaben wartet die CPU mit
`STI; HLT` auf einen Interrupt. Debugmeldungen gehen nur an Port `E9h` und
überschreiben deshalb keine Menütexte.

Menüzustand und die 520-Byte-Kopie von Geometrie und MBR liegen auf dem eigenen
C-Stack. Der bestehende Stage-2-Speichervertrag, das Schutzwort und die
BSS-Prüfungen bleiben erhalten. Das Image enthält weder einen Disk-Schreibpfad
noch eine OS-Übergabe. Die Spezifikation v0.2 bleibt unverändert.

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
```

`make hdd-test` baut zweimal, prüft 84 positive/negative HDD-Startfälle und
führt anschließend die Menüprüfung aus. `make menu-test` baut einmal und
prüft gezielt das Menü. Bereits gebaute Images lassen sich ohne Neubau prüfen:

```sh
python3 tools/test_menu.py --qemu /pfad/qemu-system-i386 --bios /pfad/bios-256k.bin
```

- 26 Bedingungen der tatsächlichen C/16-Auswahl-/Timerlogik laufen im
  `hdd-menu-model`-Image, jeweils mit EDD und CHS. Darunter sind leere und
  gesperrte Listen, ungültiger Standard, Umlaufen, Enter, Tastendruck beim
  Ablauf, Tageswechsel und fehlerhafte Uhren.
- Die normalen Images `retroboot-hdd.img` und `retroboot-reference.img`
  laufen jeweils mit EDD und CHS. QMP sendet echte emulierte PS/2-Tastendrücke.
  Jede der vier Kampagnen prüft 15 Zustände, insgesamt 60 VGA-Textseiten.
- Die Prüfung liest Zeichen und Attribute direkt aus dem VGA-Speicher:
  Auswahlbalken, Texte, BIOS-Kontext und alle vier MBR-Einträge müssen stimmen.
  Letztere werden mit den Bytes des Quellimages verglichen.
- Nach jeder Aktion werden Stage-2-Dateibytes, C-BSS und Stack-Schutzwort
  erneut im RAM geprüft. Die Disk-Traces dürfen keine Schreiboperation
  enthalten; vollständige SHA-256-Werte der Images bleiben gleich. Beide
  Lesewege müssen je Image dieselbe Sektorfolge liefern.

Ergebnisse stehen in `build/menu/menu-results.json`, Textseiten, VGA-/RAM-Abzüge,
ausgewählte echte QEMU-Screenshots und I/O-Traces daneben. Diese Nachweise
kommen zusammen mit dem kompakten Image ins CI-Artefakt. Die zusätzlichen
Hosttests prüfen den VGA-Dekoder und FAT-Clusterketten bis zur maximalen
Stage-2-Dateigröße von 48 KiB. Insgesamt sind es 83 Hosttests.

Teststeuerung: [QEMU QMP – send-key und screendump](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html).
