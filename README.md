# RetroBoot

Ein eigener BIOS-Bootmanager für klassische x86-PCs: getrennte primäre
DOS-/Windows-9x-Systeme, gemeinsame Datenvolumes und optionale Übergabe an
vorhandene NT-Bootloader. Die Entwicklung erfolgt im Branch `historical`.

**Stand: bedienbares, ausschließlich lesendes Textmenü in Phase 4.** Der eigene MBR lädt über
BIOS-EDD oder den automatischen CHS-Fallback das verborgene
FAT16-Verwaltungsvolume und eine fragmentierte
Stage-2-Datei bis zum C-Einstieg. Der eigene Startcode richtet Segmente und
Stack ein, löscht BSS und übergibt den BIOS-Kontext an C. Die C-/Assembly-
Testdiskette bleibt als eigener Nachweis erhalten. Das Menü zeigt Systemdaten
und die vier primären MBR-Einträge. OS-Starts, Partitionsänderungen und Installer folgen.

## Dokumentation

- [Aktuelle Spezifikation v0.2](docs/spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md)
- [Build, Prüfumfang und nächste Schritte](docs/Entwicklung.md)
- [BIOS-Probe bauen und testen](docs/ABI_Probe.md)
- [Festplattenstart, Speichervertrag und Fehlerprüfungen](docs/HDD_Boot.md)
- [Textmenü: Bedienung und Prüfumfang](docs/Menue.md)
- [Gesicherter Arbeitsstand und Wiederaufnahme](docs/Arbeitsstand.md)
- [Windows-/Linux-CI verständlich erklärt](docs/CI.md)
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

## Festplattenprobe

Mit derselben vorbereiteten Toolchain:

```sh
make hdd-test
```

Das baut die HDD-Artefakte zweimal und prüft 84 Starts mit QEMU, darunter
das 8-GB-Referenzlayout, beide Lesewege, fragmentierte Dateien und gezielt
erzeugte Lese- und C-Startfehler.
Danach werden 60 Menüansichten über echte emulierte Tastendrücke geprüft.
Das kompakte `build/hdd/retroboot-hdd.img` öffnet nach den Erfolgsmeldungen
das Textmenü. Pfeile wählen, Enter öffnet die Seite, Esc führt zurück;
F2 zeigt die MBR-Einträge, F8 die Recovery-Hinweise. Ohne eingerichtete
Startprofile bleibt der automatische Start aus.
Der Workflow **HDD BIOS boot** liefert es als Artefakt **retroboot-hdd-bios**.
Es ist ein Testmedium für eine leere BIOS-VM, kein Installer oder Rettungsmedium.
Grenzen und Startanleitungen für QEMU und VirtualBox stehen in der
[HDD-Anleitung](docs/HDD_Boot.md). Für den Stand aus PR #3 wurde auch ein
erfolgreicher manueller VirtualBox-Start zurückgemeldet. Auch die C-Erfolgsmeldungen
aus PR #5 wurden manuell bestätigt; das neue Menü ist noch manuell zu prüfen.

## Quellstruktur

| Pfad | Inhalt |
| --- | --- |
| `docs/` | Spezifikation, Entwicklungsstand und archivierte Unterlagen |
| `profiles/` | Maschinenlesbare Testbelegungen, zunächst RB-8G-CHS255 |
| `tools/` | Layoutprüfung, native Builds und Emulatorprüfungen |
| `tests/` | Referenzwerte, Grenzfälle und Kommandozeilentests |
| `tests/abi/`, `include/` | BIOS-Probe, eigene C-Schnittstellen und Speicherverträge |
| `boot/` | MBR, FAT16-VBR und Bootstrap |
| `core/` | Stage-2-Startcode, C-Einstieg, Menü, Auswahllogik und Linkerskript |
| `bios/` | VGA-Textausgabe, Tastatur und BIOS-Ticks für das Menü |
| `runtime/` | Gemeinsam verwendete ABI-/BIOS-Ausgabehelfer und Linker-Endmarken |
| `.github/workflows/` | Automatische Host- und BIOS-Prüfungen für Pull Requests nach `historical` |

Die Produktionskomponenten werden gemäß der Spezifikation auf dieser
geprüften Grundlage ergänzt. OS-Medien und BIOS-ROMs gehören nicht in dieses
Repository.
