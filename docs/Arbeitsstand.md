# Arbeitsstand und Wiederaufnahme

Stand: 10. November 2026.

## Gesicherte Grundlage

PR #5 ist in `historical` übernommen. Der C-Einstieg von Festplatte ist mit
80 Hosttests, drei ABI- und 82 HDD-Startfällen geprüft. Der Benutzer hat die
vier erwarteten C-/EDD-/Stage-2-Erfolgsmeldungen auch beim manuellen Start
bestätigt. Genaue Rechner-, BIOS- und VM-Daten sind noch nicht protokolliert.

## Aktueller Schritt: lesendes Menü

Branch `codex/read-only-menu`: bedienbares 80×25-Textmenü mit Pfeilen,
Enter, Esc, F2 und F8. Es zeigt den BIOS-Kontext und die vier primären
Einträge des beim Booten geladenen MBR. Es gibt noch keine registrierten
Startprofile; automatische Starts bleiben aus. Datenträger werden nicht
verändert. Recovery erhält zunächst eine Informationsseite.

Implementiert sind VGA-Ausgabe, BIOS-Tastatur, Auswahlbalken und die drei
Informationsseiten. Die [Menüanleitung](Menue.md) beschreibt Bedienung und
Grenzen. Es gibt keine OS-Übergabe, Partitionsänderung oder Wiederherstellung.
Die eingefrorene Spezifikation v0.2 bleibt unverändert.

Lokaler Prüfumfang für diesen Stand:

- 83 Hosttests und der Referenzlayout-Bericht.
- Zwei bytegleiche HDD-Builds; 84 Bootfälle mit 37 EDD-/CHS-Paaren.
- 26 native C/16-Bedingungen für Auswahl und Timer, in beiden Lesewegen.
- Vier Menükampagnen mit insgesamt 60 geprüften VGA-/Tastaturzuständen,
  einschließlich RAM-, BSS-, Stack- und Schreibüberwachung.
- Zwei bytegleiche ABI-Builds und drei Diskettenstarts; alle sieben
  ABI-Binärdateien und -Images entsprechen weiterhin dem bisherigen Stand.

Die zugehörigen CI-Ergebnisse und Artefakte stehen am Pull Request dieses
Branches. `historical` wird erst durch den vom Benutzer geprüften Merge
aktualisiert. Die lokale Arbeitskopie allein ist kein dauerhafter Sicherungspunkt.

## Noch offen

1. Das Menü manuell in VirtualBox beziehungsweise auf der Zielmaschine
   bedienen; VM-/BIOS-Version, Rechnermodell und Leseweg protokollieren.
2. MBR-/EBR-Strukturen und Startziele lesend prüfen (T06), danach den
   Übergabevertrag mit einem eigenen Test-VBR nachweisen (T07).
3. Erst anschließend gültige Startprofile und die vollständige Startauswahl
   anbinden. Die Zeitrechnung ist getestet, ein automatischer OS-Start nicht.

## Nach einer Unterbrechung

Zuerst den aktuellen Branch- und PR-Stand auf GitHub prüfen. Anschließend
den Code und die offenen Punkte dieses Dokuments lesen. Ein abgebrochener
Build oder Test wird erneut gestartet; temporärer Emulatorzustand ist kein
gesicherter Projektstand. Abgeschlossene Schritte werden als Commits
gesichert. PRs werden vom Benutzer geprüft und gemergt.
