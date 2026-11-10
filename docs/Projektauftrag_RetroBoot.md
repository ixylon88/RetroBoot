# Projektauftrag: RetroBoot – Eigener BIOS-Multibootmanager für DOS, Windows 95 und Windows 98

**RetroBoot** ist ein eigenständiges Softwareprojekt mit einem gleichnamigen GitHub-Repository.

Redaktioneller Hinweis: Persönliche Anreden wurden neutralisiert. Die ursprünglichen technischen Anforderungen bleiben dokumentiert; bei Abweichungen gilt die aktuelle Spezifikation v0.2.

## 1. Projektziel

Projektziel ist ein eigenständiger Bootmanager für klassische x86-PCs mit BIOS und MBR.

RetroBoot soll technisch folgende Betriebssysteme parallel auf einer Festplatte unterstützen:

* MS-DOS 6.22
* Windows 3.11 / Windows for Workgroups 3.11
* Microsoft Windows 95 (RTM, OSR1, OSR2.x)
* Microsoft Windows 98 (beide Edition)
* Microsoft Windows ME

Falls technisch kein großer Mehraufwand auch:
* Windows NT 3.51
* Windows NT 4.0
* Windows NT 5.x (Windows 2000, XP, Server 2003 x86/x64 und damit Windows XP x64)

Im Falle eines deutlichen Mehraufwands können Windows NT Anforderungen ausgelassen werden.

Der Benutzer soll beim Einschalten des PCs ein eigenes Bootmenü erhalten und das gewünschte Betriebssystem auswählen können.

Die Betriebssysteme sollen vollständig voneinander isoliert sein.

## 2. Technische Grundarchitektur

Zielplattform:

* Klassisches PC-BIOS
* MBR-Partitionierung
* x86-Prozessorarchitektur mit der Möglichkeit auf x64-Erweiterung
* IDE/ATA-Festplatten als erste Zielplattform
* Spätere Unterstützung für SATA und virtuelle Festplatten
* FAT16 und FAT32, NTFS-Unterstützung ist nicht unbedingt erforderlich (Begrenzung des Aufwands)
* Chainloading der jeweiligen Betriebssystem-Bootsektoren

RetroBoot soll aus folgenden Komponenten bestehen:

1. RetroBoot MBR Bootcode
2. RetroBoot Stage-2-Loader
3. RetroBoot Bootmenü
4. RetroBoot Partition Manager
5. RetroBoot Installer
6. RetroBoot Recovery System
7. RetroBoot Konfigurationsverwaltung

## 3. Festplattenaufteilung

Als Ausgangsbeispiel dient eine 40-GB-Festplatte.

Vorgesehene Partitionen:

| Partition            | Größe | Dateisystem | Verwendung       |
| -------------------- | ----: | ----------- | ---------------- |
| P1                   | 64 MB | FAT16       | RetroBoot        |
| P2                   |  2 GB | FAT16       | MS-DOS 6.22      |
| P3                   |  4 GB | FAT32       | Windows 95 OSR2  |
| P4                   |  8 GB | FAT32       | Windows 98 SE    |
| Erweiterte Partition |  Rest | FAT16/FAT32 | Gemeinsame Daten |

Die endgültigen Größen und Partitionstypen müssen auf historische BIOS-, DOS- und Windows-Kompatibilität geprüft werden.

Die Datenpartition soll ein gemeinsames FAT16-Laufwerk für alle Betriebssysteme sowie einen zusätzlichen FAT32-Bereich für Windows 95 und Windows 98 bereitstellen.

## 4. Partitionierungs- und Isolationskonzept

Jedes Betriebssystem bekommt seine eigene primäre Systempartition.

Beim Start eines Betriebssystems:

* Wird dessen eigene Systempartition eingeblendet.
* Werden die anderen Systempartitionen versteckt.
* Wird die Zielpartition als C: bereitgestellt.
* Bleibt die gemeinsame Datenpartition zugänglich, soweit das Betriebssystem das jeweilige Dateisystem unterstützt.

RetroBoot verwaltet die Sichtbarkeit der Partitionen über geeignete MBR-Partitionstypen und die aktive Partition.

Wichtig: Die Isolation muss vor dem Start des Betriebssystems erfolgen und darf nicht nur auf einer Änderung der Laufwerksbuchstaben beruhen.

## 5. RetroBoot-Partition

RetroBoot erhält eine eigene FAT16-Partition mit zunächst 64 MB.

Sie enthält:

* Stage-2-Bootloader
* Bootmanager
* Konfigurationsdateien
* Betriebssystemeinträge
* Installationsverwaltung
* Diagnosewerkzeuge
* Reparaturprogramm

Der MBR enthält lediglich den notwendigen ersten Bootcode. Der eigentliche Bootmanager liegt auf der RetroBoot-Partition.

Die RetroBoot-Partition soll gegen unbeabsichtigte Änderungen durch die Betriebssysteminstallationen geschützt werden.

## 6. Bootmenü

Das Bootmenü soll einen klassischen DOS-/Windows-9x-Look erhalten (der Windows 2000 Bootmanager sollte denselben Look haben). Die Benennung erfolgt im Partitionsmanager.

Beispiel Menüeinträge:

* MS-DOS 6.22
* Windows 95 OSR2
* Windows 98 SE

Funktionen:

* Auswahl über Pfeiltasten
* Start mit ENTER
* Einstellbarer Standard-Starteintrag
* Einstellbare Wartezeit
* Automatischer Start
* Konfigurierbare Betriebssystemnamen
* Fehlerbehandlung
* Recovery-Modus

## 7. Chainloading

RetroBoot soll Chainloading verwenden.

Der Bootmanager lädt den jeweiligen Bootsektor der ausgewählten Betriebssystempartition und übergibt die Kontrolle an den vorhandenen Bootmechanismus.

Die Original-Bootdateien und Original-Installationsmedien von z.B. DOS, Windows 95 und Windows 98 sollen unverändert verwendet werden.

## 8. Eigenes Installationsprogramm

RetroBoot soll einen eigenen Installer bekommen.

Dieser soll folgende Aufgaben übernehmen:

1. Festplatte erkennen.
2. Partitionierung vorbereiten.
3. FAT-Dateisysteme erstellen.
4. RetroBoot installieren.
5. MBR und Bootloader einrichten.
6. Betriebssystempartitionen vorbereiten.
7. Originale Installationsprogramme starten.
8. Installationsstatus verwalten.
9. Bootmanager nach Windows-Installationen gegebenenfalls wiederherstellen.
10. Betriebssystemeinträge automatisch konfigurieren.

Die Installation von DOS, Windows 95 und Windows 98 soll mit den originalen Installationsmedien erfolgen.

## 9. Recovery-System

Ein eigenes Wiederherstellungssystem soll Folgendes ermöglichen:

* MBR wiederherstellen
* Bootloader reparieren
* RetroBoot-Konfiguration wiederherstellen
* Partitionseinträge überprüfen
* Versteckte Partitionen wieder sichtbar machen
* Betriebssysteminstallationen erneut erkennen

## 10. Entwicklungsanforderungen

Die Entwicklung erfolgt schrittweise und nachvollziehbar.

Vorgesehene Lieferbestandteile:

* Vollständigen Quellcode
* Sinnvolle Projektstruktur
* Build-System
* Dokumentation
* Installationsanleitung
* Testumgebung
* Bootfähfiges Abbild für Disketten
* Bootfähige ISO-Datei
* Bootfähiges Festplattenimage

Geeignete Programmiersprachen für einen klassischen x86-Bootloader sind beispielsweise Assembly und C.

## 11. Entwicklungsreihenfolge

Die Entwicklung gliedert sich in folgende Phasen:

**Phase 1:** Technische Spezifikation und Überprüfung der historischen Kompatibilität.

**Phase 2:** Projektstruktur und Build-Umgebung.

**Phase 3:** MBR-Bootcode und Stage-2-Loader.

**Phase 4:** Eigenes Bootmenü.

**Phase 5:** Chainloading und Partitionserkennung.

**Phase 6:** Partition Manager und Isolationsmechanismus.

**Phase 7:** Installer.

**Phase 8:** Recovery-System.

**Phase 9:** Tests mit DOS 6.22, Windows 95 OSR2 und Windows 98 SE in VirtualBox, 86Box oder PCem.

**Phase 10:** Erstellung des fertigen bootfähigen RetroBoot-Images.

## 12. Besonders wichtige Anforderungen

* Keine Abhängigkeit von modernen UEFI-Funktionen.
* Kompatibilität mit klassischen BIOS-PCs.
* Keine Veränderung der originalen Windows- und DOS-Installationsmedien.
* Schutz vor versehentlichem Überschreiben der RetroBoot-Partition.
* Zuverlässige Wiederherstellung des Bootmanagers.
* Datenverlust bei der Partitionierung unbedingt vermeiden.
* Alle destruktiven Aktionen müssen vorher bestätigt werden.
* Zunächst in einer virtuellen Maschine entwickeln und testen.
* Keine ungeprüften Annahmen über die Kompatibilität historischer Betriebssysteme treffen.

## 13. Arbeitsweise

Kleine, geprüfte Entwicklungsschritte bilden die Grundlage.

Vorgesehener Ablauf:

1. Technische Architektur prüfen.
2. Mögliche Probleme mit den angegebenen Betriebssystemen aus Punkt 1 identifizieren.
3. Partitionierungsplanung gegebenenfalls korrigieren.
4. Vollständige technische Spezifikation erstellen.
5. Ersten lauffähigen Bootloader entwickeln.
6. Jede Komponente mit vollständigem Quellcode und Build-Anleitung bereitstellen.
7. Jede Entwicklungsstufe vor Beginn der nächsten testen.

**Ziel ist ein tatsächlich bootfähiges, selbst entwickeltes Retro-Multibootsystem namens RetroBoot.**

Am Anfang steht Phase 1: technische Prüfung und endgültige Architekturplanung.
