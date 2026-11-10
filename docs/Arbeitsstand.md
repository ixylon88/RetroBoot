# Arbeitsstand und Wiederaufnahme

Stand: 10. November 2026.

## Gesicherte Grundlage

PR #5 ist in `historical` übernommen. Der C-Einstieg von Festplatte ist mit
80 Hosttests, drei ABI- und 82 HDD-Startfällen geprüft. Der Benutzer hat die
vier erwarteten C-/EDD-/Stage-2-Erfolgsmeldungen auch beim manuellen Start
bestätigt. Genaue Rechner-, BIOS- und VM-Daten sind noch nicht protokolliert.

## Aktueller Schritt

Branch `codex/read-only-menu`: bedienbares 80×25-Textmenü mit Pfeilen,
Enter, Esc, F2 und F8. Es zeigt den BIOS-Kontext und die vier primären
Einträge des beim Booten geladenen MBR. Es gibt noch keine registrierten
Startprofile; automatische Starts bleiben aus. Datenträger werden nicht
verändert. Recovery erhält zunächst eine Informationsseite.

Noch offen: Implementierung, gezielte Tastatur-/Bildschirmprüfungen in QEMU,
Regressionstests, Dokumentation und PR. Die eingefrorene Spezifikation v0.2
bleibt unverändert; der Prüfumfang wird im Entwicklungsstand abgegrenzt.

## Nach einer Unterbrechung

Zuerst den aktuellen Branch- und PR-Stand auf GitHub prüfen. Anschließend
den Code und die offenen Punkte dieses Dokuments lesen. Ein abgebrochener
Build oder Test wird erneut gestartet; temporärer Emulatorzustand ist kein
gesicherter Projektstand. Abgeschlossene Schritte werden als Commits
gesichert. PRs werden vom Benutzer geprüft und gemergt.
