# BIOS- und C-/Assembly-Probe

Stand: 10. November 2026. Diese eigenständige Probe prüft die native
Werkzeugkette und die Schnittstelle zu C. Der [HDD-Ladeweg](HDD_Boot.md)
verwendet inzwischen denselben Vertrag und dieselben Helfer aus `runtime/`.

## Bauen und starten

Referenz-Buildhost: **Linux x86_64, Ubuntu 24.04**, Python 3.12, GCC und GNU
Make. The host checks additionally need the isolated Python environment and
pinned ISO dependency from the [root setup](../README.md#host-checks).
Unter Windows ist dafür eine entsprechende WSL-Umgebung möglich;
ein nativer Windows-/macOS-Build der Bootkomponenten ist noch nicht geprüft.
Die bisherigen Python-Hosttests laufen weiterhin auch nativ unter Windows.

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends -y build-essential python3 python3-venv qemu-system-x86
python3 -m venv build/host-venv
. build/host-venv/bin/activate
make iso-deps
make toolchain
make check
make boot-test
```

`make toolchain` lädt ungefähr 151 MB und arbeitet in `build/toolchain/`.
Ein Hashfehler stoppt die Vorbereitung vor dem Ausführen des betreffenden
Werkzeugs. Compiler und BIOS-ROMs werden nicht ins Repository eingecheckt.
Die Vorbereitung wird ausdrücklich aufgerufen; `make check` lädt nichts nach.

Ohne Make lauten die drei nativen Schritte:

```sh
python3 tools/setup_toolchain.py
python3 tools/build_abi_probe.py --repeat
python3 tools/test_abi_probe.py
```

Bei abweichenden Installationspfaden akzeptiert der Emulatorprüfer
`--qemu /pfad/qemu-system-i386` und `--bios /pfad/bios-256k.bin`. Der Standard-
VGA-ROM `vgabios-stdvga.bin` muss neben diesem SeaBIOS-ROM liegen.

Erwarteter positiver Gasttext:

```text
C entry, data, BSS, pointers and integer calls OK
RB ABI PASS
```

Für einen sichtbaren manuellen Start, aus dem Repository-Stamm:

```sh
qemu-system-i386 -machine pc-i440fx-8.2,accel=tcg -cpu 486 -m 16 \
  -drive file=build/abi/abi-probe.img,format=raw,if=floppy,readonly=on \
  -boot a -nic none -no-reboot
```

Der manuelle Aufruf zeigt die Meldung und hält an. Der automatische Prüfer
verwendet zusätzlich QEMUs Debug-Ausgabe und ein Debug-Exit-Gerät, um Erfolg
und erwartete Fehler ohne Bildschirm sicher unterscheiden zu können.

## Festgelegte Werkzeuge

Alle Downloadadressen und vollständigen SHA-256-Werte stehen in
[`tools/toolchain-lock.json`](../tools/toolchain-lock.json).

| Werkzeug | Festlegung |
| --- | --- |
| NASM | 2.16.01; verifiziertes Original-Quellarchiv, lokal gebaut |
| Open Watcom C/16 und WLINK | Fixierter **Vorab-Build** `2026-11-01-Build`, Linux x64; Archiv und beide ausführbaren Dateien geprüft |
| C-Objektformat | 16-Bit-OMF; `-3 -ms -ecc -s -zl -zld -w4 -wx` |
| Assembly-Objektformat | NASM `-f obj`, `BITS 16`, `CPU 386` |
| Verknüpfung | WLINK `FORMAT RAW BIN`, eigener Startcode, `NODEFAULTLIBS` |
| Emulatornachweis | QEMU 8.2.2, `pc-i440fx-8.2`, TCG, CPU `486`, 16 MiB RAM, SeaBIOS, keine Festplatte |

Der Bericht protokolliert zusätzlich die tatsächlich verwendeten
Compilerdatei-Hashes. QEMU-Paketrevision und ROMs werden in
`boot-results.json` mit Version bzw. Hash festgehalten; die ROMs werden aus
den Hostpaketen bezogen. Eine andere Emulatorversion ist ein neuer
Testdatensatz, keine automatische Hardwarefreigabe.

## C-/Assembly-Vertrag

Das Probeprogramm verwendet das **Small-Modell mit einer gemeinsamen
64-KiB-Gruppe** für Code, Daten, BSS und Stack. Eigener NASM-Startcode und
Linkerskript erzeugen daraus ein flaches Binärprogramm ohne DOS-Header,
PSP, C-Startbibliothek oder DOS-Aufruf. Ein Wechsel zu mehreren Segmenten
erfordert später einen eigenen überprüften Vertrag.

| Eigenschaft | Festlegung und Probe |
| --- | --- |
| Modus | 16-Bit-Real-Mode; erzeugter Code für 80386+, derzeit auf emuliertem 486 geprüft |
| Segmente | `CS = DS = ES = SS = 1000h` beim C-Eintritt; Zeiger auf Stacklokale sind damit auch als Near-Datenzeiger verwendbar |
| Aufrufkonvention | Explizites `__cdecl`; Symbole mit führendem `_`; Argumente rechts nach links auf dem Stack; Aufrufer entfernt Argumente |
| Rückgabe | 16 Bit in AX, 32 Bit in DX:AX; beide Richtungen C ↔ Assembly werden ausgeführt |
| Register | SI, DI und BP bleiben erhalten; AX/BX/CX/DX und ES sind nach dem Watcom-cdecl-Vertrag nicht allgemein erhalten |
| Flags | DF gelöscht, IF gesetzt beim C-Eintritt; die BIOS-Ausgabefunktion bewahrt Segmente, Register und Flags |
| Typen | `rb_u8` = 1, `rb_u16`/`int` = 2, `rb_u32` = 4 Byte; Near-Zeiger 2, Far-Zeiger 4 Byte; Compilerassertionen prüfen dies |
| Daten | Initialisierte 16-/32-Bit-Daten und Stringkonstanten werden gelesen; Near-/Far-Zeiger praktisch geprüft |
| BSS | Vom eigenen Startcode gelöscht; vor dem Laden wird der Probe-Speicher mit `A5h` gefüllt |
| Stack | Eigener Bereich, Schutzwort am unteren Ende; erhaltene Register und ausgeglichener SP werden nach C-Rückkehr geprüft |

Geprüfte Integeroperationen sind Addition, Subtraktion und eine Verschiebung
mit konstantem Abstand. Das ist keine Zusage für beliebige Compiler-
Hilfsfunktionen: Fließkomma, 64-Bit-Arithmetik, Heap, C-Standardbibliothek und
weitere aufwendige Operationen sind noch nicht Teil dieses nativen Vertrags.
Fehlende Funktionen dürfen nicht stillschweigend aus einer DOS-Bibliothek
nachgeladen werden. Eine absichtlich unaufgelöste Referenz auf
`rb_missing_runtime` muss daher mit Linkerfehler enden.

## Speicherplan der Probe

| Physischer Bereich | Verwendung |
| --- | --- |
| `00000h–004FFh` | IVT und BIOS-Datenbereich; keine eigenen Schreibzugriffe |
| Unterhalb `07C00h` | Kleiner anfänglicher Bootstack, SP startet bei `7C00h` |
| `07C00h–07DFFh` | BIOS-geladener Probe-Bootsektor |
| `10000h` aufwärts | Probe-Header, Code, Konstanten und initialisierte Daten; derzeit 844 Byte Dateiinhalt |
| Anschließend bis `bss_end` | BSS; genaue Grenzen aus Linker und Header, im Manifest protokolliert |
| `1E000h–1E001h` | Stack-Schutzwort `A55Ah` |
| `1E002h–1FFFDh` | Reservierter C-Stack; initialer SP `FFFEh`, wächst nach unten |
| Ab `20000h` | Von der Probe nicht verwendet |

Der Bootsektor prüft den konventionellen Speicher über INT 12h und eine
vorhandene EBDA-Basis vor dem Schreiben des Testsegments. Eine Stack-
Schutzmarke erkennt nicht jede denkbare Stackbeschädigung und ersetzt keine
spätere Analyse des maximalen Stackbedarfs der Produktionskomponenten.

`include/memory.inc`, der Binärheader und das Linkerskript definieren die
Adressen; der Hostprüfer gleicht sie ab. Überlappungen, falsche Ladeadressen,
unvollständige BSS-Grenzen, falsche Dateilängen oder ein zu großer Probe-
Payload brechen den Build ab. BSS und Stack belegen keinen Platz in der Datei.

## Diskettenformat und Grenzen

Das Abbild hat exakt **1.474.560 Byte**. Sein erster Sektor lädt den Payload
aus den folgenden Sektoren der ersten Spur nach `1000:0000`. Maximal 17
Payloadsektoren sind erlaubt; jeder BIOS-Leseaufruf liest genau einen Sektor
mit höchstens drei Versuchen. Nicht benötigte Bytes im letzten Payloadsektor
enthalten `A5h`, damit Sektorrundung einen fehlenden BSS-Clear nicht verdeckt.

Die Probe besitzt **kein FAT-Dateisystem**, keinen MBR, keine Partitionstabelle
und keinen Festplattenzugriff. Sie ist ein eigenes Testmedium; sie ersetzt
weder die geplante FAT12-Rettungsdiskette noch den produktiven
MBR → Verwaltungs-VBR → FAT16-Bootstrap → Stage-2-Ladeweg. Dessen Prüfsummen,
EDD-/CHS-Fallback und C-Einstieg werden separat geprüft; Wiederherstellung
gehört weiterhin zu einer späteren Stufe.

The separate [FAT12 rescue diagnostic floppy](ExternalRescue.md) is now
available. It starts independently and reads HDD partition metadata; backup
binding and restore remain open. The ABI probe itself is unchanged.

## Nachweise und Artefakte

`make boot-test` prüft nacheinander:

1. Zwei vollständige Builds in getrennten Ausgabeordnern. Alle Probe-Binär-
   dateien, Images und Manifeste müssen übereinstimmen. Linker-Maps und Logs
   enthalten Diagnosepfade bzw. Zeitstempel und gehören nicht zum Bytevergleich.
2. Den erfolgreichen Start mit `RB ABI PASS` und Debug-Exitcode 33.
3. Den Start ohne BSS-Clear: `C BSS FAIL`, `RB ABI FAIL`, Exitcode 35.
4. Den Start mit verändertem Initialwert: `C data FAIL`, `RB ABI FAIL`, Exitcode 35.
5. Unveränderte Image-Hashes nach jedem Start. QEMU bindet die Disketten
   schreibgeschützt ein; keine Festplatte ist angeschlossen.

Unter `build/abi/` liegen das positive `abi-probe.img`, die beiden absichtlich
fehlerhaften Testimages, Binärdateien, Maps, `manifest.json`, `boot-results.json`
und Logs. Der GitHub-Workflow lädt nur das positive Image und die Nachweise
als **retroboot-abi-probe** hoch. Fehlgeschlagene CI-Läufe können zur Diagnose
Teil-Artefakte enthalten; maßgeblich ist der erfolgreiche Prüfstatus.

Die 58 Hosttests und die drei Emulatorfälle bestätigen diese Entwicklungsstufe.
Tests auf 86Box, VirtualBox oder echter Hardware sowie DOS-/Windows-Starts
sind weiterhin offen. Die Produktionslader und ihre zusätzlichen Speicher-
bereiche sind der nächste Arbeitsschritt.

## Primärquellen

- [Open Watcom C/C++ User's Guide](https://open-watcom.github.io/open-watcom-v2-wikidocs/cguide.html): 16-Bit-Speichermodelle, vordefiniertes `__cdecl`, Compileroptionen.
- [Open Watcom Linker Guide](https://open-watcom.github.io/open-watcom-v2-wikidocs/lguide.html): `FORMAT RAW`, `ORDER`, `NODEFAULTLIBS`.
- [Fixierter Open-Watcom-Build](https://github.com/open-watcom/open-watcom-v2/releases/tag/2026-11-01-Build).
- [NASM-Originalquellen 2.16.01](https://www.nasm.us/pub/nasm/releasebuilds/2.16.01/) und [Objekt-/Binärformate](https://www.nasm.us/doc/nasm09.html).
- [QEMU-Systemaufruf](https://www.qemu.org/docs/master/system/invocation.html): Maschine, CPU, BIOS und schreibgeschützte Laufwerke.
