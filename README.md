# RetroBoot

Ein eigener BIOS-Bootmanager für klassische x86-PCs: getrennte primäre
DOS-/Windows-9x-Systeme, gemeinsame Datenvolumes und optionale Übergabe an
vorhandene NT-Bootloader. Die Entwicklung erfolgt im Branch `historical`.

**Stand: Einstieg in Phase 2.** Der Referenzplan lässt sich jetzt auf dem
Entwicklungsrechner automatisch prüfen. Bootcode, Installer und bootfähige
Images folgen in den nächsten Entwicklungsstufen.

## Dokumentation

- [Aktuelle Spezifikation v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build, Prüfumfang und nächste Schritte](docs/Entwicklung.md)
- [Alle Unterlagen und archivierten Entwürfe](docs/README.md)

Die aktuelle Spezifikation ist maßgeblich. Frühere Gesprächsnotizen und der
ursprüngliche Auftrag enthalten inzwischen korrigierte Layoutvorschläge.

## Lokal prüfen

Die Hostwerkzeuge benötigen Python 3.12 und ausschließlich dessen
Standardbibliothek. Unter Linux/macOS kann GNU Make die Aufrufe bündeln:

```sh
make check
```

Ohne Make, beispielsweise unter Windows mit installiertem Python 3.12:

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tools/retroboot_layout.py profiles/rb-8g-chs255.json
```

Einzelne Layoutprüfung und maschinenlesbarer Bericht:

```sh
python3 tools/retroboot_layout.py profiles/rb-8g-chs255.json
python3 tools/retroboot_layout.py profiles/rb-8g-chs255.json --json
```

Das Werkzeug liest einen JSON-Plan und schreibt seinen Bericht auf die
Standardausgabe. Es öffnet keine Images oder Datenträger, partitioniert und
formatiert nicht. Eine erfolgreiche Rechnung belegt keine BIOS- oder
Betriebssystemkompatibilität.

## Quellstruktur

| Pfad | Inhalt |
| --- | --- |
| `docs/` | Spezifikation, Entwicklungsstand und archivierte Unterlagen |
| `profiles/` | Maschinenlesbare Testbelegungen, zunächst RB-8G-CHS255 |
| `tools/` | Hostwerkzeuge zur Layoutprüfung |
| `tests/` | Referenzwerte, Grenzfälle und Kommandozeilentests |
| `.github/workflows/` | Automatische Hosttests für Pull Requests nach `historical` |

Die späteren Boot-, BIOS- und C-Komponenten werden gemäß der Spezifikation
ergänzt, sobald sie implementiert werden. OS-Medien und BIOS-ROMs gehören nicht
in dieses Repository.
