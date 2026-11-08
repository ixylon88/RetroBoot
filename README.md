# RetroBoot

Ein eigener BIOS-Bootmanager für klassische x86-PCs: getrennte primäre
DOS-/Windows-9x-Systeme, gemeinsame Datenvolumes und optionale Übergabe an
vorhandene NT-Bootloader. Die Entwicklung erfolgt im Branch `historical`.

**Stand: Phase 2 mit erfolgreichem BIOS-Probestart.** Neben den Layoutprüfungen
gibt es ein kleines bootfähiges Diskettenabbild, das die C-/Assembly-Anbindung,
Dateninitialisierung und den Stack ohne DOS prüft. Der eigentliche
Festplatten-Bootpfad und der Installer folgen anschließend.

## Dokumentation

- [Aktuelle Spezifikation v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build, Prüfumfang und nächste Schritte](docs/Entwicklung.md)
- [BIOS-Probe bauen und testen](docs/ABI_Probe.md)
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

## BIOS-Probe

Unter Linux x86_64 (Referenz: Ubuntu 24.04), mit Python 3.12, GCC, GNU Make
und `qemu-system-x86`:

```sh
make toolchain
make boot-test
```

`make toolchain` lädt die festgelegten, per SHA-256 geprüften Werkzeuge.
`make boot-test` baut zweimal und prüft anschließend drei Starts in QEMU:
eine erfolgreiche Probe und zwei erwartete Fehler. Das eigene Abbild liegt
unter `build/abi/abi-probe.img`. Der GitHub-Workflow stellt es zusammen mit
den Prüfnachweisen als Artefakt **retroboot-abi-probe** bereit.

Dies ist eine isolierte BIOS-Testdiskette mit der Meldung `RB ABI PASS`,
noch kein RetroBoot-Installations- oder Rettungsmedium. Details und Grenzen
stehen in der [Probe-Anleitung](docs/ABI_Probe.md).

## Quellstruktur

| Pfad | Inhalt |
| --- | --- |
| `docs/` | Spezifikation, Entwicklungsstand und archivierte Unterlagen |
| `profiles/` | Maschinenlesbare Testbelegungen, zunächst RB-8G-CHS255 |
| `tools/` | Hostwerkzeuge zur Layoutprüfung |
| `tests/` | Referenzwerte, Grenzfälle und Kommandozeilentests |
| `tests/abi/`, `include/` | BIOS-Probe, eigene C-Schnittstelle und Speichervertrag |
| `.github/workflows/` | Automatische Hosttests für Pull Requests nach `historical` |

Die Produktionskomponenten werden gemäß der Spezifikation auf dieser
geprüften Grundlage ergänzt. OS-Medien und BIOS-ROMs gehören nicht in dieses
Repository.
