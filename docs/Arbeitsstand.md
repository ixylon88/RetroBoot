# Arbeitsstand und Wiederaufnahme

Stand: 10. November 2026.

## Gesicherte Grundlage

PR #7 (lesende MBR-/EBR-Prüfung) ist in `historical` übernommen, Merge-Commit
`cc750633d8abd7427b6da7838317f5eb0cbbc90b`. Seine CI war vollständig grün.
Die manuellen Prüfungen des Menüs aus PR #6 und des Scanners aus PR #7 wurden
am 10. November als erfolgreich zurückgemeldet. Die Rückmeldung enthält keine
zusätzlichen Angaben zu VM, Rechner oder BIOS; solche Angaben werden nicht
aus älteren Tests übernommen. C-Einstieg und Testdiskette wurden zuvor
ebenfalls manuell bestätigt.

## Aktueller Schritt: englische und deutsche Menü-Builds

Branch `codex/english-german-builds`: Englisch ist die Standardsprache;
`RB_LANGUAGE=de` wählt Deutsch. Beide Varianten verwenden dieselbe
Programmlogik. UTF-8-Kataloge werden beim Build in CP437 umgewandelt, mit
echten Umlauten und `ß`. Getrennte Ausgabeordner erlauben abwechselnde Builds
ohne Bereinigung. Details stehen in [Languages](Languages.md).

Bootfehlercodes und Testmarker bleiben englisches ASCII. Katalogschlüssel,
Zeichen und Feldbreiten werden vor dem Build geprüft; Sprache und Kataloghash
stehen im Manifest. Repo-Texte verwenden neutrale Formulierungen ohne
persönliche Anrede oder private Personendaten; `AGENTS.md` hält dies fest.
Der Projektauftrag und die Gesprächsnotizen sind redaktionell neutralisiert,
ihre überholten technischen Aussagen bleiben als solche gekennzeichnet.
Die eingefrorene Spezifikation v0.2 bleibt unverändert.

Prüfumfang dieses Schritts:

- 93 Hosttests und der Referenzlayout-Bericht.
- Je Sprache zwei bytegleiche HDD-Builds; getrennte Ausgabepfade und Manifeste.
- 86 Bootfälle mit 38 EDD-/CHS-Paaren im englischen Build; darin 26 native
  C/16-Bedingungen für Auswahl/Timer und 51 für den Partitionsparser.
- Je Sprache fünf allgemeine Menükampagnen mit 75 VGA-/Tastaturzuständen.
- Je Sprache 32 Scanner-Kampagnen mit 204 Zuständen, einschließlich echter
  Lesefehler, Blättern, exakter Sektorfolgen sowie RAM-, BSS-, Stack- und
  Schreibüberwachung. Zusammen ergeben beide Sprachen 558 Bildschirmzustände.

Die automatische CHS-Geometrie des großen QEMU-Images deckt weiterhin nur
einen Teil des Containers ab. Der negative Geometriefall bleibt geprüft;
positive Referenztests verwenden die dokumentierte logische BIOS-Geometrie.
Belegung, Leseweg und Grenzen des Scanners bleiben unverändert.

CI-Ergebnisse und Artefakte stehen am Pull Request dieses Branches.
`historical` wird erst durch einen geprüften Merge aktualisiert. Die lokale
Arbeitskopie allein ist kein dauerhafter Sicherungspunkt.

## Noch offen

1. Neue Sprachvarianten manuell prüfen, einschließlich Umlauten und `ß`;
   VM-/BIOS-Version, Rechnermodell und Leseweg im Testprotokoll festhalten.
2. BPB-/VBR-Plausibilität und Startziele lesend prüfen, danach den
   Übergabevertrag mit einem eigenen Test-VBR nachweisen (T07).
3. Erst anschließend gültige Startprofile und die vollständige Startauswahl
   anbinden. Persistente Medienidentität und Installationsstatus ergänzen;
   die bisherige Disk-ID-Prüfung allein ist noch kein solcher Nachweis.

## Nach einer Unterbrechung

Am Anfang stehen der aktuelle Branch-/PR-Stand auf GitHub, der Code und die
offenen Punkte dieses Dokuments. Ein abgebrochener Build oder Test wird erneut
gestartet; temporärer Emulatorzustand ist kein gesicherter Projektstand.
Abgeschlossene Schritte werden als Commits gesichert. PRs bleiben bis zur
Prüfung und zum Merge durch die Projektbetreuung offen.
