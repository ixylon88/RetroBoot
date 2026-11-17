# Was die Windows-/Linux-CI prüft

CI bedeutet *Continuous Integration*: GitHub baut und prüft den Code
automatisch auf vorübergehend bereitgestellten Rechnern. Ein Pull Request
bekommt so Prüfergebnisse, bevor sein Code in `historical` übernommen wird.
Diese Prüfungen laufen bei Änderungen am PR erneut.

Die Anweisungen dafür stehen lesbar in `.github/workflows/`. Ein **Workflow**
ist ein Prüfablauf, ein **Job** läuft auf einem Rechner, und dessen **Steps**
sind die einzelnen Befehle. Die Dateien beschreiben dieselben Befehle, die
auch lokal ausführbar sind.

| Workflow | Rechner | Was passiert? |
| --- | --- | --- |
| [Host checks](../.github/workflows/host-checks.yml) | Ubuntu 24.04 **und** Windows Server 2022 | Python 3.12 installieren, alle Hosttests ausführen und das 8-GB-Layout nachrechnen |
| [BIOS ABI and Rescue](../.github/workflows/abi-probe.yml) | Ubuntu 24.04 | Repeat the ABI build and three boot cases, then rescue floppies (252 boots / 1,848 states) and CDs (66 boots / 632 states) in both languages |
| [HDD BIOS boot](../.github/workflows/hdd-boot.yml) | Ubuntu 24.04 | Build English and German twice; 104 shared boot cases and 3,681 UI states per language; publish both normal and both handoff images with evidence |

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

| Workflow | Artifacts |
| --- | --- |
| [BIOS ABI and Rescue](https://github.com/ixylon88/RetroBoot/actions/workflows/abi-probe.yml) (formerly BIOS ABI probe) | `retroboot-abi-probe`, `retroboot-rescue-diagnostics`, `retroboot-rescue-cd` |
| HDD BIOS boot | `retroboot-hdd-bios` |

The display name changed; the workflow file and `bios-probe` job/check name
remain stable. Rescue target HDDs belong to the rescue artifact.

- `retroboot-abi-probe`: Testdiskette, Binärdateien und Prüfnachweise.
- `retroboot-rescue-cd`: four normal/demo ISOs and manifests under `rescue-iso/`
  and `rescue-iso-de/`; CD evidence under `rescue-iso-test/`,
  `rescue-iso-test-de/`, `rescue-iso-test-bare/` and `rescue-iso-test-bare-de/`.
  The matching HDD remains in `retroboot-rescue-diagnostics`.
- `retroboot-rescue-diagnostics`: independent FAT12 floppies in `rescue/` and
  `rescue-de/`, with binaries, manifests and evidence in `rescue-test/` and
  `rescue-test-de/`. Both normal floppies, both synthetic demo floppies and the
  matching `retroboot-rescue-target-hdd.img` (identical in both language folders)
  are published, together with the deliberately damaged
  `retroboot-rescue-bad-fsinfo-hdd.img` and `retroboot-rescue-bad-reference-hdd.img`.
  The standalone `backup-plan-model.img`, `backup-encode-model.img` and
  `backup-payload-model.img`
  are included in both language folders. F6 evidence is under
  `rescue-plan-test*` and `rescue-plan-iso-test*`. F5 evidence is under `rescue-match-test/` and
  `rescue-match-test-de/`, including `match-results.json`.
- `retroboot-hdd-bios`: englisches und deutsches HDD-Testimage, Binärdateien, Manifeste,
  Linkerkarten, Bootprotokolle und I/O-Traces; zusätzlich Menü-Screenshots,
  VGA-/RAM-Abzüge, `menu-results.json`, `scan-results.json`, `volume-results.json`,
  `handoff-results.json`, `config-results.json`, `state-results.json`,
   `visibility-results.json`, `profile-results.json` and `audit-results.json`; zusätzlich die separaten 128-MiB-Übergabetestimages.

Im HDD-Artefakt liegen Image und Bootnachweise unter `hdd/`, die
allgemeinen Bildschirm- und Tastaturnachweise unter `menu/`, die Scanner-
Fehler- und Blätternachweise unter `scan/` und die FAT-Headernachweise unter
`volume/`. Übergabenachweise liegen unter `handoff/`, Konfigurationsnachweise unter `config/`. F6/F7/F9/F10 evidence is under `state/`, `visibility/`, `profile/` and `audit/`. Die deutschen Entsprechungen
liegen unter `hdd-de/`, `menu-de/`, `scan-de/`, `volume-de/`, `handoff-de/`, `config-de/`, `state-de/`, `visibility-de/`, `profile-de/`, `audit-de/` and `journal-de/`. Sprache, CP437-Kodierung
und Kataloghash sind in den Manifesten und UI-Berichten vermerkt.
Die [Sprachanleitung](Languages.md) beschreibt die getrennten Builds.
Die 104 gemeinsamen Bootfälle laufen einmal mit Englisch; ihre Protokolle
liegen unter `hdd/`. Beide Sprachen erhalten die vollständigen UI-Prüfungen.

The journal reports, screenshots and read traces are under `journal/` and
`journal-de/`; the [diagnosis guide](JournalDiagnosis.md) describes the campaign.

The base [external rescue campaign](ExternalRescue.md) has 73 boots per language,
including 58 seven-state UI campaigns and fifteen terminal model/failure boots.
Each successful full run writes `rescue-results.json`. Evidence checks exact
reads, VGA/RAM, source and disposable-media hashes, and absence of disk writes.
The existing ABI job shares its toolchain setup with these checks; there is
no additional runner job. Both host jobs install the hash-pinned PyCdlib
dependency and run 203 tests. The
[target-comparison model](BackupTarget.md) adds 178 native assertions and an
independently checked 542-address acquisition trace per language.
The [capture-plan model](BackupCapturePlan.md) has 710 native assertions and
a 2,188-address oracle per language. Its standalone `backup-plan-model.img`
is included under both language directories in the rescue artifact. It uses
in-memory metadata and performs no actual HDD reads or writes.

The [metadata-encoder model](BackupEncoding.md) adds one terminal boot per
language, included in the base total above. Its 64 scenarios / 1,266 assertions
compare complete encoded sectors with independent Python wire images, check
input/output guards and clearing, and feed synthetic payloads through the
complete container reader. No HDD, file output or menu action is involved.
Its `H=04F2` and `RB BACKUP ENCODE PASS` must appear on VGA and in the debug
log; it shares the 60-second model deadline.

The [payload observer model](BackupPayloads.md) adds one terminal boot per
language, included above. Its 202 scenarios / 1,014 assertions compare streamed
extent CRCs with Python oracles, test each payload-sector read failure in both
passes, and reject transient resealed changes. `I=03F6` and
`RB BACKUP PAYLOAD PASS` must appear on VGA; the 2,266-address trace remains
in the debug log. It shares the 60-second model deadline.

The separate [F5 campaign](RescueTargetCheck.md) adds 26 boots and 234 states
per language. A successful comparison requires two live acquisitions totaling
1,058 HDD reads and two full saved-file validations totaling 267 floppy reads.
The campaign checks discovery calls, exact reads, VGA/RAM, stale-field clearing,
source hashes and zero guest writes. Two tests deliberately mutate disposable
host fixtures after a first success; their reports distinguish those host
changes from guest writes. `match-results.json` is written after all requested
cases pass. The total is 98 boots / 640 states per language, 196 / 1,280 across
both. The [getting-started guide](GettingStarted.md) identifies the exact
matching image pair and separates rescue F5 from HDD-menu F5/F10.

The [CD campaign](RescueCD.md) adds 22 boots / 198 states per language without
an attached floppy: twelve with BIOS-call instrumentation, ten without it.
Both check actual optical startup, exact HDD reads, VGA/RAM and zero block
writes; only the instrumented cases observe virtual-floppy BIOS calls.
Published ISOs contain byte-identical existing floppies. Packaging repeats and
host tests verify catalog routing, directory mapping and fixed timestamps.
These F4/F5 and model campaigns total 242 boots / 1,676 states before live F6.
The current F6 campaign adds 78 floppy/CD boots / 804 states across both
languages, including full reserved-area checks and bad-FSInfo CD boots with
and without the BIOS observation ROM. Total rescue scope is **320 boots /
2,480 states**. The expanded native planner has a 60-second model deadline;
ordinary startup/UI deadlines remain 15 seconds. This reuses the ABI runner;
no additional job or physical-hardware coverage is implied.

Die Artefakte werden 30 Tage aufgehoben. Weil der Upload auch nach einem
Fehler versucht wird, beweist ein vorhandenes Artefakt allein keinen grünen
Lauf. Maßgeblich sind der Jobstatus und die Ergebnisse. `manifest.json`
enthält Größen und SHA-256-Werte; `boot-results.json` wird nur nach einem
vollständig erfolgreichen Boot-Testlauf neu geschrieben.
The reports `menu-results.json`, `scan-results.json`,
`volume-results.json`, `handoff-results.json`, `config-results.json`,
`state-results.json`, `visibility-results.json`, `profile-results.json` and `audit-results.json`
are written only after all five, 32, 43, 43, 63, 65, 37, 37 and 37 respective
campaigns succeed. Ein erwarteter,
korrekt behandelter Scanfehler gilt dabei als bestandener Test.
Screenshots allein ersetzen diese Prüfungen nicht.

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

Die Menüprüfung startet das normale Image auf dem kompakten und dem großen
Referenzlayout, jeweils mit EDD und CHS. Ein weiterer Lauf prüft eine für den
gesamten Container zu kleine CHS-Geometrie. Sie sendet Pfeile, Enter, Esc, F2,
F8 und eine unbekannte Taste an QEMUs emulierte PS/2-Tastatur. Nach jeder
Aktion liest sie die echte VGA-Textseite und kontrolliert Texte, Zahlen und
Auswahlfarben. Dies läuft für beide Sprachen, einschließlich Umlauten und `ß`.
The menu, scanner, volume, handoff, configuration, installation-state,
visibility, checked-profile, allocation-audit and journal campaigns total 7,362 screen states.
RAM-Prüfung und Schreibüberwachung bleiben dabei aktiv.
Die Countdownlogik wird zusätzlich im tatsächlich gebauten C/16-Code mit
vorgegebenen Zeitwerten geprüft; im normalen Menü ist Autostart ausgeschaltet.

Die Scannerprüfung ergänzt echte MBR-/EBR-Fehler, Lesewiederholungen und
mehrseitige Tabellen. Die 51 nativen C/16-Parserbedingungen prüfen unter
anderem andere Disk-ID, Überläufe und nicht aufsteigende EBR-Ketten.
Die Menütests müssen auch nach Fehlern bedienbar bleiben; ein 17. EBR wird
vor seinem Lesezugriff abgewiesen. Alle diese Nachweise sind ausschließlich lesend.
Die Volume-Prüfung ergänzt F3, Links/Rechts und Fehlerpfade für FAT-Header;
114 native C16-Bedingungen prüfen zusätzlich BPB-Grenzen und die verwendeten
32-Bit-Rechenhelfer. Ein plausibler Header bleibt ohne Startfreigabe.
Der separate T07-Test ergänzt 29 native Vorprüfungen und eine echte Übergabe
an den eigenen Test-VBR. Register, Stack, unveränderte Zielbytes und
Partitionszeiger werden im Ziel und im Gast-RAM geprüft; neun Fehlerzustände
werden absichtlich injiziert. Die normalen Images starten weiterhin kein Ziel.

F5 ergänzt 84 native C16-Prüfungen und 63 Kampagnen je Sprache mit 678
Zuständen für Records, FAT-Zuordnung, Identität, Ersatzkopie und Konflikte.
Details stehen in der [Konfigurationsanleitung](Configuration.md).

F6 adds 86 native C16 assertions and 65 campaigns with 650 states per language.
Evidence is uploaded from `build/state/` and `build/state-de/`; only the four
normal/handoff images are published. The HDD job timeout is 25 minutes to
accommodate the additional builds and emulator checks; it is a ceiling, not
reserved runner time. Details are in the [state guide](InstallationState.md).

F7 adds 52 native C16 assertions and 37 campaigns with 370 states per language.
Evidence is uploaded from `build/visibility/` and `build/visibility-de/`.
The [visibility guide](Visibility.md) describes the exact read-only boundary.

Ein grüner Lauf besagt: **Dieser Commit besteht die beschriebenen Prüfungen
in diesen Umgebungen.** Der Test auf echter Hardware bleibt eine zusätzliche
Prüfung. Der gemeldete erfolgreiche Diskettentest mit `RB ABI PASS` ergänzt die CI um
genau diesen praktischen Startnachweis; genaue Rechner-/BIOS-Daten sind dazu
noch nicht protokolliert.
Auch ein erfolgreicher manueller HDD-Start in VirtualBox wurde für PR #3
zurückgemeldet. VirtualBox ist bislang kein zusätzlicher automatischer CI-Job.
Die vier C-HDD-Erfolgsmeldungen aus PR #5 wurden ebenfalls manuell bestätigt;
auch Menü (PR #6) und Scanner (PR #7) wurden am 10. November manuell bestätigt.
Auch die Sprachvarianten aus PR #8 wurden manuell bestätigt; zusätzliche
Plattformdaten liegen dafür nicht vor. Auch F3 aus PR #9 wurde manuell bestätigt.
Auch T07 aus PR #10 wurde manuell bestätigt, ohne zusätzliche Plattformdaten.
The F5 test from merged PR #11 was reported complete, without added coverage details.
F6 and German/English F7 were subsequently confirmed, as were F9 and the
F10 status. The PR #17 procedure was reported checked and confirmed without
additional image/language or platform details. German external floppy
diagnosis and F4 were subsequently confirmed. English F5 and then the German
numeric/byte display were also confirmed; the linked rescue guides record
their exact scope. English CD F4/F5 and the German F6 preview were subsequently
confirmed; the CD and F6 guides retain their precise manual coverage limits.

## Workflow triggers and compute usage

All three workflows run for pull requests targeting `historical` and remain
available through `workflow_dispatch`. PR updates rerun the complete checks.
They do not start automatically on a push or merge to `historical`, avoiding a
second full campaign after an already checked PR.

A direct push to `historical` also has no automatic CI. Exceptional direct
updates require a manual run on that revision. Manual runs also provide a
fresh check or fresh artifacts when needed. Normal development uses PRs.

The build, test and upload steps, both language variants and both host
platforms remain unchanged. The repeated builds within a campaign still
check reproducibility; only the extra post-merge workflow run is removed.
Test downloads and evidence come from the successful PR run or a manual run;
a merge alone does not produce new artifacts.

All workflows use `contents: read`, require no private keys, modify no branches
and perform no merge or installation.
