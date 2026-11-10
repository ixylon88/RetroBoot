# Arbeitsstand und Wiederaufnahme

Stand: 10. November 2026.

## Gesicherte Grundlage

PR #6 (lesendes Menü) ist in `historical` übernommen, Merge-Commit
`57cb2155922e964c643f34e39b8da476794c7811`. Seine CI war vollständig grün.
Der Benutzer hat den manuellen Menütest für den Abend des 10. November
angekündigt; diese Rückmeldung steht noch aus. Der C-Einstieg aus PR #5 und
die Testdiskette wurden zuvor manuell bestätigt. Genaue Rechner-/BIOS-Daten
fehlen weiterhin.

## Aktueller Schritt: lesende Partitionsprüfung

Branch `codex/read-only-partition-scan`: F2 liest MBR und EBR-Kette und prüft
Grenzen, Überläufe, Überlappungen, Typen, Aktivflags und Schleifen. Die Disk-ID
wird mit der Kopie aus dem Bootvorgang verglichen. Vier primäre und bis zu
16 logische Einträge erscheinen auf Seiten mit je acht Zeilen. Bild hoch/runter
blättert. Fehler nennen Ursache und LBA; Esc/F8 bleiben bedienbar.

Der BIOS-Leser verwendet denselben EDD-/CHS-Code wie der Loader. Es gibt keine
Schreibfunktion, OS-Übergabe oder automatische Startfreigabe. Bedienung und
Grenzen stehen in [Menü](Menue.md) und [Partitionsprüfung](Partitionen.md).
Die eingefrorene Spezifikation v0.2 bleibt unverändert.

Lokaler Prüfumfang für diesen Stand:

- 86 Hosttests und der Referenzlayout-Bericht.
- Zwei bytegleiche HDD-Builds; 86 Bootfälle mit 38 EDD-/CHS-Paaren.
- 26 native C/16-Bedingungen für Auswahl und Timer, in beiden Lesewegen.
- 51 native C/16-Bedingungen des Partitionsparsers, in beiden Lesewegen.
- Fünf allgemeine Menükampagnen mit 75 VGA-/Tastaturzuständen.
- 32 Scanner-Kampagnen mit 204 Zuständen, einschließlich echter Lesefehler,
  Blättern, exakter Sektorfolgen sowie RAM-, BSS-, Stack- und Schreibüberwachung.

Wichtiger Befund: Die automatische CHS-Geometrie des großen QEMU-Images
deckt das Verwaltungsvolume, aber nicht den gesamten Container ab. Das wird
als eigener negativer Menüfall geprüft. Positive Referenz-Menütests verwenden
die dokumentierte logische BIOS-Geometrie. Das Layout selbst wird nicht verändert.

Die zugehörigen CI-Ergebnisse und Artefakte stehen am Pull Request dieses
Branches. `historical` wird erst durch den vom Benutzer geprüften Merge
aktualisiert. Die lokale Arbeitskopie allein ist kein dauerhafter Sicherungspunkt.

## Noch offen

1. Das Menü manuell in VirtualBox beziehungsweise auf der Zielmaschine
   bedienen; VM-/BIOS-Version, Rechnermodell und Leseweg protokollieren.
2. BPB-/VBR-Plausibilität und Startziele lesend prüfen, danach den
   Übergabevertrag mit einem eigenen Test-VBR nachweisen (T07).
3. Erst anschließend gültige Startprofile und die vollständige Startauswahl
   anbinden. Persistente Medienidentität und Installationsstatus ergänzen;
   die bisherige Disk-ID-Prüfung allein ist noch kein solcher Nachweis.

## Nach einer Unterbrechung

Zuerst den aktuellen Branch- und PR-Stand auf GitHub prüfen. Anschließend
den Code und die offenen Punkte dieses Dokuments lesen. Ein abgebrochener
Build oder Test wird erneut gestartet; temporärer Emulatorzustand ist kein
gesicherter Projektstand. Abgeschlossene Schritte werden als Commits
gesichert. PRs werden vom Benutzer geprüft und gemergt.
