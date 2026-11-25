# Dokumentation

## Aktuell

| Dokument | Bedeutung |
| --- | --- |
| [Getting started](GettingStarted.md) | Beginner guide: correct build, image, screen and key; VirtualBox demo check |
| [Technische Spezifikation v0.2](spec/RetroBoot_Phase1_Technische_Spezifikation_v0.2.md) | Maßgebliche Architektur und Abnahmekriterien |
| [Entwicklung](Entwicklung.md) | Ausführbare Befehle, aktueller Nachweisstand und nächste Schritte |
| [BIOS-/ABI-Probe](ABI_Probe.md) | Werkzeugfixierung, Speichervertrag, Build und Emulatornachweise |
| [External rescue diagnosis](ExternalRescue.md) | Independent FAT12 floppy, read-only HDD metadata checks and manual test |
| [Rescue CD](RescueCD.md) | Bootable ISO with unchanged rescue floppy, VirtualBox setup and CD evidence |
| [External backup container](ExternalBackup.md) | Bounded metadata format, host inspector and native integrity model; no restore |
| [Rescue backup files](RescueBackupFile.md) | F4 file validation, bounded FAT12 access and synthetic demo procedure |
| [Rescue target comparison](RescueTargetCheck.md) | F5 file/HDD comparison, matching synthetic image pair and manual setup |
| [Target-claim comparison core](BackupTarget.md) | Independent current metadata acquisition, comparison codes and limits |
| [Preliminary capture plan](BackupCapturePlan.md) | Live ranges, size and complete FAT boot-area checks; no backup writer |
| [Live payload checksums](BackupPayloads.md) | F6 CRC32 column, two validated passes and standalone test floppy |
| [Provisional container output](BackupStreaming.md) | Sequential bytes from explicit sources, failure/discard contract and standalone model |
| [Saved FAT boot areas](BackupBootAreas.md) | Complete reserved regions, FAT32 copies/FSInfo and selected READY VBR CRCs |
| [Saved backup records](BackupRecords.md) | Native approved-layout, A/B record and installation-reference consistency |
| [Festplattenstart](HDD_Boot.md) | EDD-/CHS-Ladeweg, C-Startvertrag, VirtualBox-Anleitung und Fehlerfälle |
| [English/German builds](Languages.md) | Sprachwahl, CP437, Umlaute und Eszett; englische Anleitung |
| [Textmenü](Menue.md) | Bedienung, Informationsseiten und Tastatur-/Bildschirmnachweise |
| [Partitionsprüfung](Partitionen.md) | MBR-/EBR-Scanner, Grenzen, Fehlerseiten und Blättertests |
| [FAT volume headers](VolumeHeaders.md) | F3-BPB-Prüfung, unterstützte Formate, Grenzen und Nachweise; englische Anleitung |
| [Journal diagnosis](JournalDiagnosis.md) | F8/Enter, identity checks, bounded journal reads and manual test |
| [Transaction-journal model](TransactionJournal.md) | Three-sector records, conservative pair selection and current-MBR observations |
| [Management allocation](AdminAllocation.md) | F10 eight-file ownership, full FAT comparison and read-only diagnostics |
| [Checked-profile test](ProfileTest.md) | F9 from F7, fresh records and visibility, exact owned T07 target |
| [Partition visibility](Visibility.md) | F7 current/intended primary types and active flags; read-only preview |
| [Installation-state records](InstallationState.md) | F6, independent identities, current-VBR checks and the prepared DOS boot block |
| [Configuration records](Configuration.md) | F5-Diagnose, A/B-Auswahl und Profilformat; englische Anleitung |
| [Test-VBR handoff](Handoff.md) | T07-Übergabevertrag, separates F4-Testimage und Nachweise; englische Anleitung |
| [Arbeitsstand](Arbeitsstand.md) | Gesicherter Stand, offene Schritte und Wiederaufnahme nach einer Pause |
| [CI erklärt](CI.md) | Bedeutung der Windows-/Linux-Jobs, Ergebnisse und Artefakte |
| [Projektauftrag](Projektauftrag_RetroBoot.md) | Ursprüngliche Ziele; technische Korrekturen stehen in v0.2 |

## Archiv

| Dokument | Bedeutung |
| --- | --- |
| [Technische Spezifikation v0.1](archive/RetroBoot_Phase1_Technische_Spezifikation_v0.1.md) | Vorherige Revision; durch v0.2 abgelöst |
| [Gesprächsnotizen](archive/Gespraech_RetroBoot.md) | Redaktionell neutralisierte Ideensammlung mit den ursprünglichen Referenzbildern |
| [Referenzbilder](archive/images/) | Unveränderte Bilder 1–7 aus dem Gespräch |

Die Archivunterlagen bleiben als Entstehungsgeschichte erhalten. Insbesondere
die ursprünglichen 40-GB-Beispiele und der Vorschlag mit fünf primären
Partitionen sind keine Implementierungsvorgabe. V0.2 legt das 8.000.000.000-Byte-
Referenzmedium mit drei primären Systemplätzen und einem erweiterten Container
fest; RetroBoot selbst liegt auf einem verborgenen logischen FAT16-Volume.
