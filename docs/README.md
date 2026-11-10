# Dokumentation

## Aktuell

| Dokument | Bedeutung |
| --- | --- |
| [Technische Spezifikation v0.2](spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md) | Maßgebliche Architektur und Abnahmekriterien |
| [Entwicklung](Entwicklung.md) | Ausführbare Befehle, aktueller Nachweisstand und nächste Schritte |
| [BIOS-/ABI-Probe](ABI_Probe.md) | Werkzeugfixierung, Speichervertrag, Build und Emulatornachweise |
| [Festplattenstart](HDD_Boot.md) | EDD-/CHS-Ladeweg, C-Startvertrag, VirtualBox-Anleitung und Fehlerfälle |
| [Textmenü](Menue.md) | Bedienung, Informationsseiten und Tastatur-/Bildschirmnachweise |
| [Partitionsprüfung](Partitionen.md) | MBR-/EBR-Scanner, Grenzen, Fehlerseiten und Blättertests |
| [Arbeitsstand](Arbeitsstand.md) | Gesicherter Stand, offene Schritte und Wiederaufnahme nach einer Pause |
| [CI erklärt](CI.md) | Bedeutung der Windows-/Linux-Jobs, Ergebnisse und Artefakte |
| [Projektauftrag](Projektauftrag_RetroBoot.md) | Ursprüngliche Ziele; technische Korrekturen stehen in v0.2 |

## Archiv

| Dokument | Bedeutung |
| --- | --- |
| [Technische Spezifikation v0.1](archive/RetroBoot_Phase1_Technische_Spezifikation_v0.1.md) | Vorherige Revision; durch v0.2 abgelöst |
| [Ursprüngliches Gespräch](archive/Gespraech_RetroBoot.md) | Ideensammlung mit den ursprünglichen Referenzbildern |
| [Referenzbilder](archive/images/) | Unveränderte Bilder 1–7 aus dem Gespräch |

Die Archivunterlagen bleiben als Entstehungsgeschichte erhalten. Insbesondere
die ursprünglichen 40-GB-Beispiele und der Vorschlag mit fünf primären
Partitionen sind keine Implementierungsvorgabe. V0.2 legt das 8.000.000.000-Byte-
Referenzmedium mit drei primären Systemplätzen und einem erweiterten Container
fest; RetroBoot selbst liegt auf einem verborgenen logischen FAT16-Volume.
