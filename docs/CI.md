# Was die Windows-/Linux-CI prüft

CI bedeutet *Continuous Integration*: GitHub baut und prüft den Code
automatisch auf vorübergehend bereitgestellten Rechnern. Ein Pull Request
bekommt so Prüfergebnisse, bevor sein Code in `historical` übernommen wird.
Diese Prüfungen laufen bei Änderungen am PR erneut.

Die Anweisungen dafür stehen lesbar in `.github/workflows/`. Ein **Workflow**
ist ein Prüfablauf, ein **Job** läuft auf einem Rechner, und dessen **Steps**
sind die einzelnen Befehle. Die Dateien beschreiben dieselben Befehle, die
wir lokal ausführen können.

| Workflow | Rechner | Was passiert? |
| --- | --- | --- |
| [Host checks](../.github/workflows/host-checks.yml) | Ubuntu 24.04 **und** Windows Server 2022 | Python 3.12 installieren, alle Hosttests ausführen und das 8-GB-Layout nachrechnen |
| [BIOS ABI probe](../.github/workflows/abi-probe.yml) | Ubuntu 24.04 | Festgelegte Werkzeuge laden, C-/Assembly-Diskette zweimal bauen, drei QEMU-Starts prüfen |
| [HDD BIOS boot](../.github/workflows/hdd-boot.yml) | Ubuntu 24.04 | HDD-Lader und C-Stage-2 zweimal bauen, 82 Start-/Fehlerszenarien mit EDD und CHS in QEMU prüfen, kompaktes Testimage bereitstellen |

Die **Matrix** in `host-checks.yml` startet denselben Job zweimal mit
unterschiedlichem `os`. So werden beispielsweise Unterschiede bei Pfaden,
Zeilenenden und Textkodierung sichtbar. `fail-fast: false` sorgt dafür, dass
das Ergebnis des anderen Systems auch bei einem Fehler noch ermittelt wird.

Windows und Linux sind hier **Entwicklungsrechner**. RetroBoot selbst startet
im BIOS vor einem Betriebssystem. Der Windows-Job testet deshalb weder einen
Windows-9x-Start noch die Kompatibilität eines späteren Windows-Bootloaders.
Die native Toolchain ist bisher für Linux x86_64 festgelegt; ihre Binärdateien
laufen anschließend im emulierten klassischen PC.

## Ergebnisse lesen

Im PR unter **Checks** einen Job öffnen. Grüne Schritte sind erfolgreich;
ein roter Schritt zeigt seinen ausgeführten Befehl und dessen Ausgabe.
Ein Buildfehler unterscheidet sich dort von einem fehlgeschlagenen Hosttest
oder einem unerwarteten Bootergebnis. Ein Abbruch durch Zeitlimit ist ebenfalls
kein bestandener Test.

Im Workflow-Lauf unter **Artifacts** liegen die erzeugten Dateien:

- `retroboot-abi-probe`: Testdiskette, Binärdateien und Prüfnachweise.
- `retroboot-hdd-bios`: kompaktes HDD-Testimage, Binärdateien, Manifest,
  Linkerkarten, Bootprotokolle und I/O-Traces.

Die Artefakte werden 30 Tage aufgehoben. Weil der Upload auch nach einem
Fehler versucht wird, beweist ein vorhandenes Artefakt allein keinen grünen
Lauf. Maßgeblich sind der Jobstatus und die Ergebnisse. `manifest.json`
enthält Größen und SHA-256-Werte; `boot-results.json` wird nur nach einem
vollständig erfolgreichen Boot-Testlauf neu geschrieben.

## Warum zweimal bauen?

Zwei getrennte Ausgabeordner müssen dieselben Binärdateien und Images ergeben.
Das findet unbeabsichtigte Zeitstempel oder andere wechselnde Build-Eingaben.
Compiler-/Assembler-Versionen und Downloads sind zusätzlich festgelegt und
mit Prüfsummen abgesichert. QEMU und BIOS stammen dagegen derzeit aus den
Ubuntu-Paketen; ihre tatsächlichen Versionen beziehungsweise Hashes werden
pro Lauf protokolliert. Die VM-Prüfumgebung ist also nicht vollständig eingefroren.

Ein kleines eigenes **Test-Option-ROM** kann dem Lader fehlende EDD-Funktionen
oder fehlerhafte BIOS-Antworten vorspiegeln. Dadurch wird der unveränderte MBR
zur echten automatischen CHS-Auswahl veranlasst. Die Tests protokollieren die
BIOS-Aufrufe, vergleichen die gelesenen Sektorfolgen und lesen Stage 2 zur
Byteprüfung aus dem VM-Speicher zurück. Für das normale Image werden auch
C-Bootkontext, BSS und Stack-Schutzwort geprüft. Das ROM gehört nur zum Testaufbau;
für den manuellen Start des Images wird es nicht benötigt.

Ein grüner Lauf besagt: **Dieser Commit besteht die beschriebenen Prüfungen
in diesen Umgebungen.** Der Test auf echter Hardware bleibt eine zusätzliche
Prüfung. Dein erfolgreicher Diskettentest mit `RB ABI PASS` ergänzt die CI um
genau diesen praktischen Startnachweis; genaue Rechner-/BIOS-Daten sind dazu
noch nicht protokolliert.
Auch ein erfolgreicher manueller HDD-Start in VirtualBox wurde für PR #3
zurückgemeldet. VirtualBox ist bislang kein zusätzlicher automatischer CI-Job.

Alle drei Workflows lesen das Repo mit `contents: read`, benötigen keine
privaten Schlüssel und verändern keine Branches. Sie lösen weder einen
Merge noch eine Installation aus. Neben PRs laufen sie auch bei Änderungen
an `historical` und können über `workflow_dispatch` manuell gestartet werden.
