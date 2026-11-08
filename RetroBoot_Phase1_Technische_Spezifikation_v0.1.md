# RetroBoot – Technische Spezifikation, Phase 1

Version 0.1 · 8. November 2026 · Sprache: Deutsch

**Status:** Architekturgrundlage für die Implementierung. Quellenprüfung und rechnerische Layoutprüfung abgeschlossen; Bootfähigkeit, Betriebssystemkompatibilität und Wiederherstellung sind noch nicht praktisch nachgewiesen. Diese Datei enthält keinen fertigen Bootloader und keine Installationsfreigabe für reale Festplatten.

## 1. Ergebnis und verbindliche Entwurfsentscheidungen

RetroBoot wird ein eigener BIOS-Bootmanager für x86 mit MBR-Partitionierung, eigenem Textmenü, persistentem Partitionsverstecken und Chainloading unveränderter Betriebssystem-Bootsektoren. GRUB oder ein anderer vorhandener Bootmanager ist keine Laufzeitabhängigkeit.

Der ursprüngliche Entwurf benötigt vier Korrekturen:

1. **Vier MBR-Einträge:** Drei primäre Betriebssystempartitionen und eine erweiterte Partition belegen die Tabelle vollständig. RetroBoot wird deshalb ein eigenes verborgenes **logisches FAT16-Laufwerk** innerhalb der erweiterten Partition. Es benötigt keine aktive primäre Partition: Unser MBR lädt seinen Bootsektor direkt über eine bei der Installation eingetragene Sektoradresse. Die Vier-Einträge-Grenze ist dokumentiert [S01]; der direkte Ladeweg ist unsere Architekturentscheidung.
2. **40 GB sind keine belastbare Windows-95-Basis:** Microsoft schließt Medien über 32 GB für sämtliche Windows-95-Ausgaben einschließlich OSR2.x aus [S02]. Die Größe einzelner Partitionen hebt diese Aussage nicht auf. Das erste Referenzmedium hat daher **8.000.000.000 Byte**, ausdrücklich nicht 8 GiB.
3. **Isolation bedeutet Laufwerkstrennung:** Versteckte Typen verhindern die normale Einbindung fremder Systemlaufwerke. Sie verhindern weder direkte Sektorzugriffe noch das Löschen durch ein Partitionierungsprogramm. Eine Sicherheitsgrenze zwischen Betriebssystemen entsteht damit nicht. Gemeinsame Daten sind ausdrücklich von der Trennung ausgenommen.
4. **Drei gleichzeitige Installationen:** Im Standardlayout bleiben höchstens drei primäre Systempartitionen. Unterstützung verschiedener OS-Versionen bedeutet zunächst, dass diese in einem der drei Plätze installiert und geprüft werden können. Alle genannten Versionen gleichzeitig auf derselben Platte sind mit dieser Architektur nicht erfüllt.

**Umfang des ersten funktionsfähigen Systems:** DOS 6.22, Windows 95 OSR2 und Windows 98 SE gleichzeitig; Windows 3.11 oder WfW 3.11 als Anwendung auf einer DOS-Installation. Weitere Varianten folgen als eigene Testbelegungen. Bei geforderter Isolation zweier unterschiedlicher DOS/Windows-3.x-Umgebungen benötigt jede einen eigenen Systemplatz.

Die Architektur ist für diese erste Ausbaustufe festgelegt. Kompatibilitätsfreigaben entstehen ausschließlich durch die in Abschnitt 16 definierten Prüfungen. Eine negative Prüfung führt zu einer dokumentierten Änderung der Spezifikation, nicht zu einer stillschweigenden Ausnahme.

## 2. Plattform und Grenzen

| Bereich | Festlegung |
| --- | --- |
| Firmware | Klassisches PC-BIOS; kein UEFI-Startpfad |
| Prozessor des Bootmanagers | 80386 oder neuer, Ausführung im 16-Bit-Real-Mode |
| Arbeitsspeicher des Bootmanagers | Herkömmlicher Speicher unter 1 MiB; Zielbudget unter 256 KiB, keine XMS-/EMS-Abhängigkeit |
| Betriebssystemanforderungen | Zusätzlich die Anforderungen der jeweiligen Windows-Ausgabe; der Bootmanager senkt diese nicht |
| Anzeige und Tastatur | VGA-kompatibler 80×25-Textmodus und BIOS-Tastaturdienste |
| Datenträger | Zunächst genau eine Festplatte als BIOS-Laufwerk `80h`, 512 Byte je logischem Sektor |
| Controller | IDE/ATA als Referenz; Laufwerkszugriff des Bootmanagers über BIOS INT 13h |
| Partitionierung | Klassischer MBR, feste primäre Einträge, höchstens eine erweiterte Partition mit EBR-Kette |
| Dateisysteme | FAT16 für RetroBoot; FAT16/FAT32 für System- und Datenvolumes; FAT12 für Rettungsdisketten |
| Installation | Zunächst neue, leere VM-Images; vorhandene fremde Layouts nur lesend untersuchen |
| Nicht enthalten | GPT, UEFI, dynamische Datenträger, Disk-Overlays, Verschlüsselung, Laufwerkskompression, automatische Größenänderung oder Verschiebung belegter Partitionen |

**x64:** Für das Chainloading eines BIOS-installierten x64-NT-Systems ist kein 64-Bit-RetroBoot erforderlich. Den CPU-Moduswechsel übernimmt dessen eigener Loader. CPU, Controller, BIOS und Treiber müssen zur jeweiligen x64-Ausgabe passen. Das ist ein späteres separates Testprofil.

**SATA:** Ein BIOS kann auch SATA-Laufwerke über INT 13h bereitstellen. Daraus folgt keine AHCI-Unterstützung des gestarteten DOS/Windows. Native AHCI-Treiber oder eine eigene ATA/AHCI-Treiberschicht gehören nicht zur ersten Ausbaustufe. SATA im geeigneten Kompatibilitätsmodus ist erst nach Prüfung freizugeben.

**Virtuelle Festplatten** sind bereits die erste Entwicklungsplattform. RAW ist das Referenzformat; VHD, VDI oder andere Container sind spätere Verpackungen derselben Sektordaten, soweit der Emulator sie passend präsentiert.

## 3. Historische Kompatibilitätsmatrix

Alle Einträge dieser Tabelle sind **Zielprofile, keine bereits getesteten Zusagen**. Betriebssystemdateien und Originalmedien werden nicht mit RetroBoot ausgeliefert.

| Betriebssystem | Systemvolume im jeweiligen Profil | Gemeinsame Daten | Besonderheit / Abnahme |
| --- | --- | --- | --- |
| MS-DOS 6.22 | FAT16, unter 2 GiB, Typ `06h` | FAT16 | Ganzes Systemvolume und gemeinsame FAT16-Daten innerhalb tatsächlich erreichbarer BIOS-CHS-Grenzen [S03, S04] |
| Windows 3.11 | DOS-Systemvolume, FAT16 | FAT16 über DOS | Kein eigener unabhängiger Bootkernel; Start nach DOS. Eigene DOS-Partition nur bei gewünschter Trennung |
| WfW 3.11 | DOS-Systemvolume, FAT16 | FAT16 über DOS | DOS-Unterbau; 32-Bit-Plattenzugriff gesondert prüfen [S05, S06] |
| Windows 95 RTM | FAT16, unter 2 GiB | FAT16 | Kein FAT32; gesamtes Medium höchstens 32 GB laut Microsoft [S02, S07] |
| Windows 95 OSR1 | FAT16, unter 2 GiB | FAT16 | Ebenfalls kein FAT32; eigenes Installations-/Updateprofil [S02, S07] |
| Windows 95 OSR2, 2.1, 2.5 | FAT16 oder FAT32; Referenz FAT32 | FAT16 und FAT32 | FAT32-fähige Familie; 32-GB-Mediengrenze bleibt [S02, S07] |
| Windows 98 erste Ausgabe | FAT16 oder FAT32 | FAT16 und FAT32 | Eigenständiger Testfall; große Platten und BIOS-Übersetzung gesondert behandeln [S08] |
| Windows 98 SE | FAT16 oder FAT32; Referenz FAT32 | FAT16 und FAT32 | Drittes Hauptprofil der Erstabnahme |
| Windows ME | Referenz FAT32 | FAT16 und FAT32 | Eigenes Installationsmedium und Reboot-Verhalten prüfen; kein Ersatz für DOS 6.22 |
| Windows NT 3.51 | FAT16 oder vorhandenes NTFS | FAT16 | Optional; alte Partitionskennung und NT-Startpfad prüfen [S09] |
| Windows NT 4.0 | FAT16 oder vorhandenes NTFS | FAT16 | Startdateien und ihr Volume im frühen BIOS-erreichbaren Bereich; Service-Pack-/IDE-Unterschiede prüfen [S09, S10] |
| Windows 2000, XP x86 | FAT16/FAT32/NTFS je Installationsprofil | FAT16/FAT32 | Optional; NTLDR, BOOT.INI, Datenträgersignatur und C:-Zuordnung prüfen |
| Server 2003 x86/x64, XP x64 | Vorzugsweise durch Original-Setup erzeugtes NTFS | FAT16/FAT32 nach Test | Optional; größere separate Testbelegung. Kein Versprechen, dass das kleine Hauptlayout für jede Ausgabe praktisch ausreicht |

Bei NT wird der Partitionsbootsektor geladen, anschließend arbeiten NTLDR und die originalen Startdateien. RetroBoot braucht dazu **keinen NTFS-Dateitreiber**. NTFS formatieren, reparieren oder Dateien daraus zur genauen Versionserkennung lesen ist nicht Teil des Kerns. Jede NT-Installation behält ihre eigenen passenden Loaderdateien; insbesondere wird kein älterer 32-Bit-NTLDR für ein x64-System verwendet [S20].

Der Aufwand für die grundsätzliche NT-Übergabe ist begrenzt; der Aufwand für verlässliche Installations- und Kompatibilitätstests ist erheblich. NT bleibt deshalb optional und blockiert die DOS/95/98-Auslieferung nicht. Die verwendeten Primärslots werden nicht vertauscht; jede NT-Installation erhält von Anfang an dieselbe Sicht, unter der sie später startet.

Für Windows 3.x wird im ersten Testprofil der native 32-Bit-Plattenzugriff nicht aktiviert. Der Toshiba-Herstellerhinweis belegt ein konkretes Treiberproblem bei größeren Platten, keine universelle Aussage über alle Rechner [S06]. Einen eingeschalteten schnellen Plattenzugriff geben wir nur zusammen mit einem getesteten Treiber frei.

## 4. BIOS-Adressierung und Kapazität

Drei Grenzen sind getrennt zu behandeln: Dateisystemgröße, erreichbare Sektoradressen und die Fähigkeiten der später geladenen Betriebssystemtreiber.

MS-DOS 6.22 verwendet den klassischen BIOS-Plattenzugriff und unterliegt dessen 1024-Zylinder-Grenze [S03]. Die Reichweite hängt von der **vom BIOS übersetzten** Geometrie ab; sie ist nicht pauschal 8 GB. Bei 16 Köpfen und 63 Sektoren sind es 528.482.304 Byte. Bei 255 Köpfen und 63 Sektoren ergeben sich 8.422.686.720 Byte. Beide Werte sind hier aus `1024 × Köpfe × Sektoren × 512` berechnet. Emulierte BIOS-Versionen haben ebenfalls unterschiedliche Grenzen [S11].

Für das Referenzlayout werden 255 Köpfe und 63 Sektoren pro Spur als **zu verifizierende VM-Geometrie** festgelegt. Diese Werte dürfen nicht blind auf reale Hardware übertragen werden. Ein 8-GiB-Image wäre größer als diese CHS-Reichweite.

RetroBoot verwendet bevorzugt BIOS-Erweiterungen für LBA-Zugriffe. Die Erkennung prüft bei INT 13h/AH=41h Carry, die Rücksignatur und das Bit für Festplattenzugriff. Nur bei passender Unterstützung werden die erweiterten Lese-/Schreibfunktionen verwendet [S12]. Klassischer CHS-Zugriff bleibt als geprüfter Fallback vorgesehen.

Die Unterstützung von LBA im Bootmanager erweitert **nicht** nachträglich den DOS-Kernel. Insbesondere reicht es nicht, nur den ersten DOS-Bootsektor in einen niedrigen Bereich zu legen: Auch später gelesene Dateien und gemeinsame Daten müssen erreichbar bleiben.

Jede I/O-Anforderung wird gegen Kapazität, Puffergrenzen und erlaubte Schreibbereiche geprüft. Der konservative erste BIOS-Treiber überträgt einen Sektor pro Aufruf; Optimierung erfolgt erst nach Abnahme. Wiederholungen sind begrenzt, Schreibfehler stoppen den Start. Ein BIOS-Reset ist keine allgemeine Garantie für das Leeren eines Hardware-Schreibcaches.

## 5. Korrigierter Referenzplan: RB-8G-CHS255

Die Größe des RAW-Images beträgt exakt **8.000.000.000 Byte = 15.625.000 Sektoren**. Eine übersetzte Zylindereinheit umfasst `255 × 63 = 16.065` Sektoren. Primäre Folgepartitionen und EBR-Bereiche beginnen an solchen Grenzen. P1 sowie logische Volumes lassen jeweils die erste Spur frei.

Die Größen sind bewusst kleiner als im 40-GB-Beispiel. Das schafft eine überschaubare gemeinsame Testbasis für alte Betriebssysteme, den Bootmanager und die gemeinsamen Daten.

| Eintrag | Zweck | Format / sichtbarer Typ | Größe ungefähr |
| --- | --- | --- | ---: |
| P1, primär | DOS 6.22, optional Windows 3.11/WfW | FAT16 / `06h` | 1,50 GiB |
| P2, primär | Windows 95 OSR2 | FAT32 / `0Bh` | 1,50 GiB |
| P3, primär | Windows 98 SE | FAT32 / `0Bh` | 1,99 GiB |
| P4, erweitert | Container für die folgenden Volumes | `05h`, kein eigenes Dateisystem | 2,45 GiB |
| L1, logisch | Gemeinsame Daten aller Profile | FAT16 / `06h` | 509,84 MiB |
| L2, logisch | RetroBoot | FAT16, dauerhaft verborgen als `16h` | 62,72 MiB |
| L3, logisch | Zusätzliche gemeinsame Daten | FAT32 / `0Bh` | 1,89 GiB |

RetroBoot liegt damit nahe der gewünschten anfänglichen Größe von 64 MB. Die Abweichung ergibt sich aus der gewählten historischen Geometrieausrichtung. L1 steht zuerst, damit die gemeinsamen FAT16-Daten vor dem verborgenen Verwaltungsvolume und dem FAT32-Volume in der EBR-Kette liegen.

**Exakte Sektorbelegung; Endadressen sind einschließlich:**

| Bereich | Start-LBA | Sektoren | End-LBA |
| --- | ---: | ---: | ---: |
| P1 | 63 | 3.148.677 | 3.148.739 |
| P2 | 3.148.740 | 3.148.740 | 6.297.479 |
| P3 | 6.297.480 | 4.176.900 | 10.474.379 |
| P4, Container | 10.474.380 | 5.140.800 | 15.615.179 |
| EBR für L1 | 10.474.380 | 1 | 10.474.380 |
| L1 | 10.474.443 | 1.044.162 | 11.518.604 |
| EBR für L2 | 11.518.605 | 1 | 11.518.605 |
| L2 | 11.518.668 | 128.457 | 11.647.124 |
| EBR für L3 | 11.647.125 | 1 | 11.647.125 |
| L3 | 11.647.188 | 3.967.992 | 15.615.179 |

LBA 0 enthält den MBR. Die übrigen Sektoren der ersten Spur bleiben unbenutzt; dort liegt kein versteckter Stage-2-Code. Hinter P4 bleiben 9.820 Sektoren frei. Die absichtliche Überdeckung von P4 mit seinen logischen Volumes ist eine Containerbeziehung, keine Überlappung zweier Datenvolumes.

EBR-Dateneinträge verwenden Adressen relativ zum jeweiligen EBR. Verweise auf den nächsten EBR sind relativ zum Anfang der erweiterten Partition. Für dieses Layout lauten die beiden Weiterverweis-Startwerte 1.044.225 und 1.172.745. Auch ihre Längen und CHS-Felder müssen konsistent berechnet werden; nur Startwerte zu schreiben genügt nicht.

P4 bleibt im Basisprofil `05h`. Eine erweiterte LBA-Partition `0Fh` wäre für DOS 6.22 und NT 3.x/4.0 keine gleichwertige gemeinsame Grundlage [S04, S09]. Alle Basisvolumes liegen deshalb im ausgewählten CHS-Bereich. Ob jedes Original-Setup die gemischte EBR-Kette aus FAT16, verborgenem FAT16 und FAT32 unverändert lässt, ist ein ausdrücklicher Abnahmetest.

Für Windows 95 RTM/OSR1 wird ein freier Systemplatz von Anfang an als FAT16 angelegt. Ein Wechsel des Partitions-Typbytes konvertiert niemals ein Dateisystem. Ein bereits belegter Platz wird nicht stillschweigend umformatiert.

## 6. Was aus dem 40-GB-Ziel wird

Eine 40-GB-Platte kann ein späteres Profil für Windows 98/ME und passende NT-Systeme werden. Sie wird **nicht** als allgemein kompatibles DOS/95/98-Referenzmedium bezeichnet. Bei Windows 98 sind außerdem dokumentierte Probleme bestimmter BIOS-Übersetzungen und IDE-Treiber zu beachten [S08]. Ein nicht zugeteilter Rest allein beseitigt die Windows-95-Mediengrenze nicht.

Mögliche spätere Wege sind eine kleinere physische Platte oder ein vom Controller tatsächlich kleiner präsentiertes Laufwerk. Eine eventuell vorhandene Kapazitätsbegrenzung per Hardware wird nur anhand des konkreten Laufwerks beurteilt. RetroBoot verändert in Version 1 weder HPA noch DCO und installiert kein Disk-Overlay.

Mehr als drei unabhängige Systeminstallationen auf einer Platte würden eine wesentliche Änderung erfordern: etwa wechselnde MBR-Tabellen mit einem eigenen Partitionskatalog oder andere Startmodelle. Nicht eingeblendete Bereiche erscheinen fremden Installern dabei leicht als frei. Wegen dieses Risikos wird ein solches Verfahren nicht als einfache Erweiterung des Versteckens eingeplant. Mehrere Platten oder wechselbare Medien sind ebenfalls gesonderte Projekte, keine bereits gelösten Eigenschaften.

## 7. Bootarchitektur

| Komponente | Aufgabe | Darf beim normalen Start schreiben? |
| --- | --- | --- |
| Stage 1 im MBR | Bootlaufwerk übernehmen, RetroBoot-VBR laden, Fehler kurz anzeigen | Nein |
| RetroBoot-VBR und Bootstrap | Kleinen eigenen Lader laden und Stage 2 aus FAT16 lesen | Nein |
| Stage 2 | Menü, Konfiguration, Prüfung, Sichtbarkeitswechsel, Chainloading | Nur geprüfte eigene Metadaten und MBR |
| Partition Manager | Layout prüfen und geplante Änderungen anzeigen/ausführen | Nur nach erforderlicher Bestätigung |
| Installer | Neue Volumes erzeugen, Dateien installieren, Medienübergabe verwalten | Nur innerhalb bestätigter Operation |
| Recovery | Extern startbare Diagnose und gezielte Wiederherstellung | Standardmäßig nein; Änderung einzeln bestätigen |

Der normale Ablauf lautet: BIOS startet unseren MBR; dieser lädt den Bootsektor des verborgenen logischen RetroBoot-Volumes. Dessen kleiner Bootstrap lädt Stage 2. Nach Auswahl und erfolgreichen Prüfungen setzt Stage 2 die Systempartitionstypen und das aktive Flag persistent und übergibt an den Original-VBR des gewählten Systems.

Die aktive Systempartition ist also **nicht** der Weg, über den unser MBR RetroBoot findet. Dadurch kann die gewählte OS-Partition während Installation und Betrieb aktiv bleiben.

### 7.1 MBR und Bootstrap

Das Stage-1-Budget beträgt höchstens 440 Byte einschließlich eigener Parameter. Die vier Byte ab Offset 440 bleiben für die Datenträgersignatur erhalten, ebenso die folgenden zwei reservierten Byte. Die 64-Byte-Partitionstabelle ab Offset 446 und die Signatur am Sektorende werden separat behandelt. Kein pauschales Überschreiben aller 446 Anfangsbytes bei einer Reparatur.

Der Installer trägt die Adresse des RetroBoot-VBR in den eigenen Bootcodebereich ein. Der MBR benötigt daher weder einen FAT-Treiber noch einen EBR-Parser. Ein verschobenes RetroBoot-Volume erfordert eine erneute Installation des Zeigers; automatisches Verschieben wird nicht unterstützt.

Für FAT16 bleibt der reservierte Bereich auf dem üblichen einen Sektor. Der kleine Folgelader wird als vom Installer zusammenhängend angelegte Datei `RBBOOT.SYS` gespeichert; der eigene VBR kennt ihren geprüften Bereich. Danach liest der Folgelader `RBSTG2.BIN` über einen begrenzten FAT16-Leser. Die Stage-2-Datei darf fragmentiert sein. Fremde Defragmentierung des Verwaltungsvolumes ist kein unterstützter Vorgang; ein veränderter Bootstrap-Bereich muss durch Recovery neu installiert werden.

Jede Stufe prüft die ihr mögliche Kennung, Länge und Prüfsumme der nächsten. Das schützt vor vielen Beschädigungen, ist aber weder Secure Boot noch eine Garantie, dass beliebig beschädigter bereits ausgeführter Code sicher reagiert.

### 7.2 Speicher und Übergabe

Der MBR normalisiert seine Segmentregister und richtet einen eigenen Stack ein; BIOS-Anfangswerte außer den definierten Bootinformationen werden nicht vorausgesetzt. Vor dem Laden eines weiteren Sektors nach `0000:7C00` muss der dort laufende Code umkopiert sein. IVT, BIOS-Datenbereich und EBDA werden nicht überschrieben.

Für das spätere OS-Handoff gelten als eigene Schnittstellenanforderungen:

- Real Mode; gültiger Stack und definierte Segmentregister; Direction Flag gelöscht.
- Ziel-VBR vollständig und unverändert bei `0000:7C00`, Endsignatur geprüft.
- BIOS-Laufwerksnummer in `DL` weiterhin das ausgewählte Laufwerk `80h`.
- Zeiger `DS:SI` auf eine passende stabile Kopie des ausgewählten MBR-Eintrags.
- BIOS-Interruptzustand wiederhergestellt; kein zurückbleibender Disk-Hook und kein Laufwerkstausch.
- Partitionsanfang im BPB, MBR-Lage und tatsächliche Sektoradresse stimmen überein. Eine Abweichung wird gemeldet, nicht heimlich gepatcht.

Die exakten Linkadressen und Binärheader werden in Phase 2 in gemeinsamen Include-Dateien und Linkerskripten festgeschrieben. Das Freigabekriterium ist ein nachgewiesener, kollisionsfreier Speicherplan mit Größenprüfungen im Build.

## 8. Isolation und Laufwerksbuchstaben

Das Grundverfahren – fremde DOS/Windows-Partitionen verstecken und die Zielpartition chainloaden – ist in einer bestehenden Bootmanager-Dokumentation beschrieben [S13]. RetroBoot implementiert es selbst.

| Inhalt | Sichtbarer Typ | Verborgener Typ | Einsatz |
| --- | --- | --- | --- |
| FAT16 | `06h` | `16h` | DOS, ältere Windows-Profile, RetroBoot |
| FAT16 mit LBA-Kennung | `0Eh` | `1Eh` | Nur spätere passende Profile |
| FAT32 | `0Bh` | `1Bh` | Hauptprofil innerhalb CHS-Reichweite |
| FAT32 mit LBA-Kennung | `0Ch` | `1Ch` | Späteres LBA-Profil |
| NTFS | `07h` | `17h` | Optional, erst nach NT-Abnahme |

Diese Tabelle ist eine explizite Positivliste. Bei unbekannten Typen wird nicht blind ein Bit gesetzt oder gelöscht. Der ursprüngliche sichtbare Typ wird in der Konfiguration gespeichert und mit dem Volume abgeglichen. Das tatsächliche Verhalten jedes Zielsystems gegenüber verborgenen Typen gehört zur Prüfung.

Vor dem Start müssen folgende Bedingungen gemeinsam gelten:

1. Genau eine der verwalteten primären Systempartitionen ist sichtbar und aktiv.
2. Die anderen Systempartitionen sind verborgen und inaktiv.
3. Die erweiterte Partition bleibt inaktiv; normale gemeinsame Daten bleiben erreichbar.
4. RetroBoot bleibt verborgen. Ein Verwaltungszugriff erfolgt durch eigene Werkzeuge.
5. MBR-Startadressen, Längen, CHS-Werte und Slotreihenfolge bleiben beim normalen Wechsel unverändert.

Im festgelegten Ein-Platten-Profil ergibt sich für DOS/9x aus der sichtbaren primären Systempartition die beabsichtigte Zuordnung zu C:. Die historische Buchstabenvergabe ist dokumentiert [S14]. RetroBoot weist den Buchstaben nicht selbst zu. Das erste gemeinsame FAT16-Laufwerk soll D: werden; RAM-Laufwerke, CD-ROM-Treiber und zusätzliche Datenträger können weitere Buchstaben beeinflussen. NT verwendet zusätzlich eigene Zuordnungen; dort wird C: bei Installation und erneut nach jedem Profilwechsel geprüft.

Ein nur im Arbeitsspeicher geänderter MBR genügt nicht: Nach dem Start lesen Betriebssysteme die Partitionstabelle erneut. Der normale Profilwechsel schreibt sie deshalb auf die Platte. Ist Schreiben nicht möglich, darf RetroBoot nur dann unverändert weiterstarten, wenn die vorhandene Sicht bereits exakt zum geprüften Profil passt; andernfalls bleibt es im Menü.

Windows 3.11 und DOS auf demselben Volume sind nicht gegeneinander isoliert. Ein zusätzlicher Menüeintrag allein würde diese Eigenschaft nicht ändern. Ebenso bleiben gemeinsame Dateien bewusst in allen berechtigten Profilen veränderbar. Für den FAT16-Austauschbereich gelten im ersten Profil einfache 8.3-Dateinamen und keine gemeinsamen betriebssystemspezifischen Reparatur-/Defragmentierungsabläufe.

## 9. Sichere Schreibvorgänge und Bestätigung

**Lesen ist der Ausgangszustand.** Unbekannte Geometrie, Überlappungen, beschädigte EBR-Ketten, fremde Metadaten, Prüfsummenfehler oder ein unpassender Datenträger sperren Änderungen.

Der normale Sichtbarkeitswechsel ist keine Formatierung. Sein Zweck und seine dauerhafte Änderung der MBR-Typen/Flags werden bei Einrichtung erklärt und freigegeben. Die spätere Auswahl oder ein eingerichteter Countdown führt nur diesen begrenzten Vorgang aus. Niemals löst ein Countdown Formatieren, Löschen oder Wiederherstellen aus.

Destruktive Operationen erhalten immer eine eigene Bestätigung **vor** dem ersten betroffenen Schreibzugriff. Die Anzeige nennt Disk-ID, BIOS-Laufwerk, Kapazität, Volume, Start/Länge, bisherige Belegung, neue Belegung und Sicherungsstand. Die Bestätigung verlangt eine eindeutige Eingabe, etwa die angezeigte Kennung; ENTER allein akzeptiert nicht versehentlich eine vorausgewählte Löschung.

### 9.1 Wechseltransaktion

1. MBR erneut lesen und mit dem erwarteten Zustand vergleichen.
2. Original und beabsichtigten vollständigen neuen MBR im inaktiven Journalbereich mit Sequenznummer, Disk-ID und Prüfsumme speichern.
3. Journal zurücklesen und prüfen; erst danach den neuen MBR schreiben.
4. MBR zurücklesen und byteweise vergleichen; nur Typ-/Aktivbytes dürfen vom geplanten Ausgangszustand abweichen.
5. Abschlussrecord in einer anderen vorab zugewiesenen Stelle schreiben und prüfen.
6. Erst dann den Ziel-VBR ausführen.

Sind Ziel- und Istzustand identisch, wird kein MBR-Schreibvorgang benötigt. Beim Start nach einer unterbrochenen Transaktion werden Ist-, Alt- und Sollzustand verglichen. Bei Abweichung oder unklarem Journal gibt es keinen automatischen OS-Start und keine automatische Rückschreibung. Recovery zeigt eine begründete Wiederherstellungsoption an.

Ein Sektorschreibvorgang kann bei Stromausfall beschädigt werden. Rücklesen kann aus Caches bedient werden; BIOS bietet keine universelle Haltbarkeitsgarantie. Das Journal reduziert das Risiko, macht einen beschädigten MBR aber nicht selbststartend. **Eine externe Rettungsdiskette oder Rettungs-CD und externe Sicherungen sind deshalb Teil des Designs.**

Formatierung und Dateikopien sind nicht durch dieses kleine MBR-Journal rückgängig zu machen. Sie werden nur auf ausdrücklich bestätigten Zielbereichen ausgeführt. Version 1 bietet kein vorgetäuschtes vollständiges Undo einer Neuinstallation.

## 10. Dateisysteme und Verwaltungsdaten

Die Formatierung richtet sich nach der Microsoft-FAT-Spezifikation [S15]. FAT-Typ und Clusterzahl müssen zusammenpassen; Textkennungen allein reichen nicht. Clustergrößen oberhalb 32 KiB werden ausgeschlossen. Für FAT16 werden ein reservierter Sektor, zwei FATs und 512 Root-Einträge verwendet. Für FAT32 werden FSInfo, Backup-Bootbereich und beide FATs konsistent erzeugt.

Für die rechnerische Referenzprüfung ergeben sich folgende Entwurfswerte; ein späterer Formatter muss sie unabhängig verifizieren:

| Volume | FAT | Sektoren/Cluster | Sektoren je FAT | Datencluster |
| --- | ---: | ---: | ---: | ---: |
| P1 | 16 | 64 | 193 | 49.191 |
| P2 | 32 | 8 | 3.075 | 392.819 |
| P3 | 32 | 8 | 4.079 | 521.088 |
| L1 | 16 | 16 | 255 | 65.226 |
| L2 | 16 | 4 | 126 | 32.043 |
| L3 | 32 | 8 | 3.875 | 495.026 |

Die Prüfung hat nicht formatiert und ersetzt keinen Mount-/Schreibtest. Original-Setup oder das passende originale SYS-/Format-Werkzeug erzeugt die OS-Startdateien und den OS-Bootcode. Ein von RetroBoot erzeugtes leeres FAT-Volume ist noch kein bootfähiges DOS-/Windows-System.

Geplante Dateien auf dem Verwaltungsvolume:

| Datei / Bereich | Bedeutung |
| --- | --- |
| `RBBOOT.SYS` | Zusammenhängend abgelegter kleiner Folgelader |
| `RBSTG2.BIN` | Menü, Diagnose und Chainloader |
| `RBCFG.A`, `RBCFG.B` | Zwei vorab zugewiesene Konfigurationskopien |
| `RBTXN.A`, `RBTXN.B` | Vorab zugewiesene Transaktionsbereiche |
| `RBSTATE.A`, `RBSTATE.B` | Installationszustand, unabhängig von Menükonfiguration |
| `RB.CFG` | Lesbarer Konfigurationsexport; Änderungen werden ausdrücklich importiert und geprüft |
| `BACKUP` | Lokale Ergänzung zu den zwingend externen Sicherungen |

Beim normalen Start werden weder Verzeichnisse erweitert noch Dateien angelegt oder FAT-Ketten verändert. Änderungen erfolgen nur innerhalb vorhandener, geprüfter Verwaltungsdateien. Vor einem Sektorschreibzugriff muss der Sektor nachweislich zur aktuellen, nicht überlappenden Dateizuordnung gehören. Veraltete blockweise Dateizeiger dürfen nicht verwendet werden. Ein zwischenzeitlich fremd verändertes Verwaltungsvolume sperrt den Schreibpfad.

Konfigurationsrecords enthalten mindestens Magic, Formatversion, Gesamtlänge, Generation, Disk-ID, Layout-Fingerabdruck, Nutzdaten und CRC32. Die jeweils letzte vollständig gültige Kopie wird gelesen; bei widersprüchlichen gleichrangigen Kopien wird angehalten. CRC32 ist Beschädigungserkennung, keine Authentifizierung.

Ein Systemeintrag enthält eine stabile Entry-ID, Anzeigename, Primärslot, Start und Länge, sichtbaren Typ, OS-Profil, Installationsstatus und Freigabestatus. Global werden Standard-Entry-ID, Countdown, Sprache und Recovery-Einstellungen gespeichert. Namen sind editierbar, Identitäten unabhängig vom Namen. Unbekannte Konfigurationsversionen werden nicht geraten.

## 11. Menü und Partition Manager

Das Menü verwendet Textmodus, klare Rahmen, einen hervorgehobenen Auswahlbalken und eine kurze Statuszeile. Derselbe Stil wird auch bei NT-/Windows-2000-Einträgen verwendet. Die Originalmenüs der Betriebssystemloader werden nicht grafisch verändert; ein NT-Profil soll möglichst nur seine eigene Installation enthalten.

| Bedienung | Verhalten |
| --- | --- |
| Pfeil hoch / herunter | Freigegebene Einträge wählen |
| ENTER | Ausgewählten Eintrag nach Prüfungen starten |
| ESC | Countdown stoppen; im Menü bleiben |
| F2 | Partitionen und Geometrie lesend anzeigen |
| F8 | Recovery öffnen, zunächst ohne Schreibrechte |
| Countdown | Standard zunächst 10 Sekunden; konfigurierbar, auch abgeschaltet |

Jede Tastaturinteraktion stoppt den laufenden Countdown. Ungültige Standardwahl, offener Installationsvorgang oder ein Fehler sperren den automatischen Start. Timer müssen einen BIOS-Tageswechsel korrekt behandeln. Ohne funktionsfähige Zeitbasis wird gewartet, nicht sofort gestartet.

Der Partition Manager zeigt physische Bereiche, MBR-/EBR-Einträge, Dateisysteme, Namen, sichtbaren/verborgenen Zustand und erwartete Änderungen zusammen an. Phase 5 beginnt mit einer reinen Anzeige. Erstellen, Formatieren und Umbenennen folgen erst mit der jeweiligen Schreibprüfung. Größenänderung belegter Volumes und das Verschieben von Systempartitionen sind nicht Teil von Version 1.

Fachliche Fehlerklassen umfassen Disk-I/O, Geometriewechsel, falsches Medium, ungültigen MBR, EBR-Schleife, Bereichsüberlauf, FAT-Fehler, ungültige Konfiguration, unvollständige Transaktion und nicht startfähiges Ziel. Eine Fehlermeldung nennt Aktion und LBA, soweit bekannt, und lässt Menü/Recovery zu. Sie beendet nicht kommentarlos die Anwendung.

## 12. Installationsarchitektur

Der Installer ist eine eigene BIOS-Anwendung und kann ohne vorhandenes DOS starten. Er erkennt und partitioniert den bestätigten Zielbereich, erzeugt FAT-Strukturen und installiert RetroBoot. Er ist jedoch kein DOS-Kernel: Ein beliebiges originales `SETUP.EXE` lässt sich nicht allein durch einen Sprung aus unserem Bootloader ausführen.

Die Installation eines Betriebssystems erfolgt daher als kontrollierte Übergabe:

1. Datenträger und Geometrie anzeigen; Layout zunächst nur planen.
2. Vor Änderungen externe, überprüfte Sicherung der benötigten Metadaten herstellen. Bei vorhandenen Daten ist zusätzlich ein vollständiges Backup erforderlich; deren Umbau bleibt in Version 1 gesperrt.
3. Bestätigten leeren Zielbereich vorbereiten, Verwaltungsvolume erzeugen, Dateien kopieren und sämtliche geschriebenen Bereiche prüfen.
4. Rettungsmedium erstellen und dessen Startfähigkeit nachweisen, bevor fremde OS-Setups beginnen.
5. Für genau einen Systemplatz das Installationsprofil aktivieren: Ziel sichtbar/aktiv, andere Systeme und RetroBoot verborgen.
6. Während der Installation auch die gemeinsamen Datenvolumes nach dokumentierter, bestätigter Metadatenänderung verbergen. Die vorherige EBR-Sicht wird gesichert und später gezielt wiederhergestellt.
7. Über originales startfähiges Medium neu starten. Bei nicht startfähiger CD wird eine passende originale DOS-/Windows-Startdiskette samt erforderlichem CD-ROM-Zugriff benötigt.
8. Das originale Setup auf dem vorbereiteten Ziel ausführen. Ein eigener optionaler DOS-Helfer darf im bereits gestarteten DOS den angegebenen Setup-Pfad aufrufen; er ersetzt weder DOS noch dessen Treiber.
9. Nach Setup-Neustarts erforderlichenfalls vom externen RetroBoot-Medium starten und den eigenen MBR-Code wiederherstellen.
10. Geometrie, Partitionstabelle, Bootsektor und Sichtbarkeit erneut prüfen; erst nach kontrolliertem OS-Start und Rückkehr zu RetroBoot den Eintrag als abgenommen markieren.

Ein Installer, der die gesamte Platte neu aufteilen will oder die Struktur unerwartet verändert, darf nicht ungeprüft fortgesetzt werden. Versteckte Typen können ein solches Programm nicht technisch daran hindern.

Installationszustände sind `planned`, `prepared`, `media_handoff`, `setup_in_progress`, `verification_required`, `ready` und `recovery_required`. Der Status wird vor Übergaben gespeichert. RetroBoot verändert die Originalmedien nicht, um einen Erfolgskanal einzubauen; deshalb wird ein gelungener Desktop-/DOS-Start zunächst durch den Bediener bestätigt und durch das Testprotokoll belegt. Eine `55 AA`-Signatur allein ist kein Installationsnachweis.

Automatische Erkennung liefert Kandidaten aus Partitionstypen, BPB und passenden Dateien. Unsichere Zuordnungen bleiben als solche sichtbar. Eine NTFS-Installation kann ohne eigenen NTFS-Leser nicht zuverlässig nach Ausgabe/Service Pack inventarisiert werden; dafür bleiben manuelle Benennung und das Installationsprotokoll zulässig.

## 13. Recovery und Schutz der Verwaltung

Es gibt zwei Einstiege: F8 aus einer funktionsfähigen Stage 2 und das unabhängige externe Rettungsmedium. Nur der zweite Weg hilft, wenn MBR, Bootstrap, FAT oder Stage 2 selbst beschädigt sind.

| Fehler | Reparaturprinzip |
| --- | --- |
| Fremdes Setup ersetzt nur den MBR-Code | Eigenen Code und seine Parameter wieder einsetzen; aktuelle Disk-Signatur und geprüfte Tabelle erhalten |
| Tabelle verändert oder beschädigt | Ist/Sicherung anzeigen und Geometrie vergleichen; gezielte Wiederherstellung nach Bestätigung |
| Bootstrap-Zeiger oder Stage 2 beschädigt | Eigenes Volume prüfen, Bootstrap/Dateien aus passendem Release erneuern |
| Eine Konfigurationskopie beschädigt | Gültige zweite Kopie verwenden; Reparatur gesondert anbieten |
| Beide Konfigurationen unbrauchbar | Externe Sicherung importieren oder Kandidaten neu erfassen; keine erfundene alte Zuordnung |
| Falsche Hidden-/Aktiv-Flags | Sicht eines einzelnen bekannten Profils wiederherstellen |
| OS-Startdateien beschädigt | An Originalmedium bzw. OS-Reparatur verweisen; RetroBoot erzeugt keine Microsoft-Dateien |

Sicherungen enthalten den ursprünglichen und zuletzt freigegebenen MBR, alle EBRs, Volume-Bootbereiche einschließlich vorhandener Backup-Bootsektoren, RetroBoot-Konfiguration, Installationsstatus, Geometrie, Kapazität, Disk-ID und Prüfsummen. FAT32-Volume-Bootbereiche werden nicht auf einen einzigen Sektor reduziert. Nutzdaten-Backups bleiben davon getrennt.

Eine Sicherung wird nur auf ein identifiziertes passendes Ziel angewendet. Ein altes vollständiges MBR-Abbild darf nicht pauschal über eine inzwischen geänderte gültige Partitionstabelle geschrieben werden. Erkannte Disk-Overlays, GPT-Signaturen oder unklarer fremder Bootcode führen zur lesenden Diagnose.

Ein Recovery-Befehl zum dauerhaften Einblenden verborgener Systemvolumes ist möglich, benötigt aber Bestätigung und sperrt den gewöhnlichen OS-Start, bis wieder ein konsistentes Einzelprofil gewählt ist. Das Verwaltungsmenü selbst kann verborgene Partitionen anzeigen, ohne ihre Typbytes zu ändern.

**Schutzwirkung:** Verborgenes Volume, keine regelmäßige Einbindung in ein Gast-OS, eingeschränkte eigene Schreibpfade und externe Kopien schützen gegen typische Bedienfehler. Schutz gegen beliebige Rohsektorzugriffe, Hardwaredefekte oder absichtliche Zerstörung kann ein MBR-Bootmanager nicht leisten.

Wechsel zwischen Betriebssystemen erfolgen nach vollständigem Herunterfahren. Hibernate-/Suspend-Wiederaufnahme über zwischenzeitliche Partitionswechsel wird zunächst nicht unterstützt. Ohne Dateisystemkenntnis aller optionalen NT-Volumes behauptet RetroBoot keine lückenlose automatische Erkennung solcher Zustände.

## 14. Quellstruktur und Build-Plan

Diese Struktur wird in Phase 2 angelegt; die genannten Build-Ziele sind Sollschnittstellen, noch keine heute ausführbaren Befehle.

| Pfad im künftigen Repository | Inhalt |
| --- | --- |
| `boot/mbr/` | Stage 1 in NASM |
| `boot/vbr/` | Eigenes FAT16-VBR und Diskettenstart |
| `boot/bootstrap/` | Kleiner Folgelader und FAT16-Leseweg |
| `core/` | Menü, Profile, Chainloader und gemeinsame Abläufe |
| `bios/` | Assembly-Schnittstellen für Disk, Tastatur, Anzeige und Timer |
| `disk/` | MBR-/EBR-Prüfung, Geometrie, Transaktionen |
| `fs/` | FAT12/16/32-Prüfung und begrenzte Formatter |
| `installer/`, `recovery/` | Native Verwaltungsprogramme |
| `dos-helper/` | Optionaler Helfer für bereits laufendes DOS |
| `include/` | Gemeinsame Typen und versionierte On-Disk-Definitionen |
| `tools/` | Image-Erzeugung, Prüfung und Metadatenexport auf dem Build-Host |
| `tests/` | Hosttests, Test-Bootsektoren, Emulatorabläufe und Fehlerfälle |
| `docs/` | Spezifikation, Installation, Wiederherstellung, Kompatibilitätsprotokolle |
| `build/` | Erzeugnisse, nicht als Quellcode einchecken |

NASM erzeugt rohe Bootsektoren bzw. passende Objektmodule [S16]. Für C ist Open Watcom C/16 vorgesehen [S17], mit eigenem Startcode und ohne DOS-Laufzeitaufrufe im nativen Loader. BIOS-Aufrufe bleiben in kleinen Assembly-Wrappers. Der optionale DOS-Helfer ist ein getrenntes Programm mit DOS-Laufzeitumgebung. 16-Bit-C-Größen, Segmentgrenzen und 32-Bit-LBA-Arithmetik werden explizit geprüft.

Make und Python 3 steuern Hostwerkzeuge und Imagebau. Phase 2 fixiert funktionierende Werkzeugversionen, Bezugsquellen und Prüfsummen. C-ABI, Linkerformat, Compiler-Hilfsfunktionen, initialisierte Daten und BSS werden zuerst an einem kleinen Probeprogramm geprüft. Kein GCC-`-m16`-Workaround ohne nachgewiesene passende Laufzeitannahmen.

Geplante Ziele: `make check`, `make boot-test`, `make images`, `make run`, `make release`. Der Standardbuild öffnet ausschließlich reguläre Image-Dateien. Schreiben auf reale Blockgeräte ist kein versteckter Nebeneffekt eines Make-Ziels.

## 15. Auszuliefernde Images

| Ergebnis | Inhalt und Zweck |
| --- | --- |
| `retroboot-floppy.img` | 1.474.560 Byte, FAT12, eigener startfähiger Diagnose-/Recovery-Lader |
| `retroboot.iso` | El-Torito-CD zunächst mit Diskettenemulation derselben Rettungsumgebung |
| `retroboot-hdd.img` | Eigenständig startfähiges RAW-Referenzimage mit RetroBoot und vorbereiteten leeren Systemplätzen |
| Quellarchiv / Git-Tag | Vollständiger eigener Quellcode, Build-Anleitung, Prüfsummen und Testnachweise |

Die CD-Startmethode folgt dem BIOS-El-Torito-Verfahren [S18]; sie benötigt keine UEFI-Komponente. Ein Rechner ohne CD-Boot-Unterstützung bleibt auf die Diskette angewiesen. Die Recovery-CD ist schreibgeschützt; Sicherungsexporte benötigen ein separates beschreibbares Ziel.

Auf das 1,44-MB-Medium müssen alle für die Basiserholung benötigten eigenen Komponenten passen. Diese Größenprüfung erfolgt früh. Falls zusätzliche optionale Werkzeuge nicht hineinpassen, werden sie getrennt angeboten; eine Diskette, die zur MBR-Rettung erst Dateien von der beschädigten Platte benötigt, erfüllt die Anforderung nicht.

Ausgelieferte Images enthalten keine vorinstallierten proprietären Betriebssysteme, ROMs oder Originalmedien. Eigene Test-VBRs erlauben das Prüfen des Chainloaders ohne solche Dateien. Das fertige Multibootsystem mit DOS/Windows entsteht anschließend durch die Installation mit den Medien des Benutzers.

## 16. Teststrategie und Abnahmekriterien

QEMU wird für schnelle, automatisierbare CPU-/BIOS-Tests eingesetzt. Seine dokumentierten Image- und Snapshot-Funktionen helfen bei isolierten Versuchen [S19]. Für Persistenztests werden explizite separate Arbeitskopien mit geeignetem Cachemodus verwendet; ein flüchtiger Snapshot belegt keine Haltbarkeit nach Host-Stromausfall.

86Box ist die erste historische Referenz. BIOS-Image, Maschine, CPU, RAM, Controller, Geometrie und Emulatorversion werden protokolliert. PCem kann als zusätzliche historische Gegenprobe dienen, VirtualBox als weitere VM-Prüfung. Ein Erfolg in einem Emulator wird nicht als Nachweis für alle BIOS-Rechner ausgegeben.

Erste OS-Testmaschine: zeitgenössischer Pentium mit konservativer Taktung, 64 MiB RAM, VGA, IDE und dokumentierter großer-Platten-Übersetzung. Die konkrete 86Box-Maschine wird erst nach Messung ihrer INT-13h-Werte festgelegt. Für NT x64 und gegebenenfalls weitere Ausgaben werden passende getrennte Hardwareprofile erstellt.

### 16.1 Prüfkatalog

| ID | Test | Erfolgsbedingung |
| --- | --- | --- |
| T01 | Reproduzierbarer Build | Zweimaliger sauberer Build erzeugt identische eigene Bootartefakte |
| T02 | Stage-1-Grenzen | Code/Parameter passen in 440 Byte; geschützte MBR-Bereiche bleiben unverändert |
| T03 | Boot ohne OS | MBR, Verwaltungs-VBR und Stage 2 erreichen eine eindeutige sichtbare Meldung |
| T04 | EDD und CHS | Beide Lesewege liefern dieselben Prüfdaten; unzureichende Geometrie wird abgewiesen |
| T05 | Beschädigte Ladewege | Fehlende Datei, falsche Länge, CRC-Fehler und Lesefehler führen zu verständlichem Halt/Recovery |
| T06 | Partitionen | Überlappungen, Überläufe, unzulässige Typen, EBR-Schleifen und fremde Disk-ID werden erkannt |
| T07 | Übergabevertrag | Eigener Test-VBR bestätigt Adresse, Register, Stack und Partitionszeiger |
| T08 | Menü | Pfeile, ENTER, Timeout, ESC, Standardwahl und Tageswechsel funktionieren |
| T09 | Typwechsel | Nur freigegebene MBR-Typ-/Aktivbytes und eigene Verwaltungsdaten ändern sich |
| T10 | Abbruch beim Schreiben | Fehler nach jedem Transaktionsschritt starten kein unklar isoliertes OS; externe Rettung funktioniert |
| T11 | Formatter | Unabhängige Prüfung und Schreib-/Lesetest mit passenden Gastwerkzeugen; Backup-Bereiche konsistent |
| T12 | Original-Setups | DOS 6.22, 95 OSR2 und 98 SE installieren nacheinander, ohne fremde Systemdaten zu verändern |
| T13 | Betriebssystemisolation | Jedes System sieht sein C:, die vorgesehenen Datenvolumes und keine fremden Systemlaufwerke |
| T14 | Unsichtbare Daten | Hashes aller inaktiven Systemvolumes bleiben nach kontrollierten Schreibversuchen im aktiven OS gleich |
| T15 | MBR überschrieben | Original-Setup/geeignetes Testwerkzeug ersetzt Bootcode; externes Recovery stellt RetroBoot korrekt wieder her |
| T16 | FAT-/Konfigurationsausfall | Auch bei unlesbarer Stage 2 ist externe Diagnose möglich; gültige Kopien werden korrekt erkannt |
| T17 | Rettungsmedien | Diskette und ISO starten bei fehlendem/zerstörtem HDD-MBR unabhängig |
| T18 | Weitere OS-Ausgaben | Jede Ausgabe mit Medienstand und Hardwareprofil separat installieren, starten und prüfen |
| T19 | NT-Zusatzfälle | C:, BOOT.INI-Zuordnung, Disk-Signatur, Hidden-Typen, Reboots und Service Packs geprüft |
| T20 | Reale Hardware | Erst nach VM-Freigaben; leere Testplatte, geprüfte externe Sicherung und Rettungsweg |

T14 vergleicht die fremden Systemvolumes, nicht die gemeinsamen Daten oder das Journal: Diese dürfen sich bestimmungsgemäß ändern. Tests mit Raw-Disk-Werkzeugen sind keine Isolationserwartung, sondern demonstrieren gegebenenfalls deren technische Grenze.

Jeder Testdatensatz hält Medienausgabe und Hash, BIOS-Version/Hash, Geometrie, aktivierten I/O-Weg, MBR/EBR-Dumps davor/danach, Schritte, Resultat und offene Fehler fest. Lizenzierte Medien und ROM-Dateien bleiben außerhalb des öffentlichen Repositories.

### 16.2 Phasen und Übergänge

| Phase | Ergebnis | Voraussetzung für nächste Phase |
| --- | --- | --- |
| 1 | Diese Spezifikation, Quellen und rechnerisches Layout | Grenzen und offene Nachweise sind ausdrücklich erfasst |
| 2 | Projektstruktur, Werkzeugfixierung, Hostprüfungen | T01; C-/Assembly-ABI und Größenbudgets nachgewiesen |
| 3 | MBR und minimaler Stage-2-Start | T02–T05 auf Testimages; keinerlei OS-Partitionierung |
| 4 | Eigenes Menü | T08, Fehlerfälle eingeschlossen |
| 5 | Erkennung und zunächst unveränderndes Chainloading | T06–T07, dann ein passend vorbereitetes Originalsystem |
| 6 | Schreibpfad und Isolation | T09–T10; unabhängiges Rettungswerkzeug für diese Tests bereits vorhanden |
| 7 | Installer und FAT-Erzeugung | T11–T12; Abbruch- und Wiederanlauffälle geprüft |
| 8 | Vollständige Recovery-Oberfläche | T15–T17 |
| 9 | Gemeinsame OS-Abnahme | T12–T14; optionale Profile T18–T19 |
| 10 | Reproduzierbares Release mit Images | Keine offenen kritischen Fehler; geprüfte Anleitung und Checksummen |

Die gewünschte Reihenfolge bleibt erhalten. **Eine kleine externe Rückschreib-/Rettungsmöglichkeit muss jedoch vor den ersten Schreibtests aus Phase 6 existieren.** Die vollständige benutzerfreundliche Recovery-Funktion folgt weiterhin in Phase 8. Datenverlustschutz erst nach dem Installer einzuführen wäre zu spät.

## 17. Nachweisstand am Ende dieser Phase

Tatsächlich durchgeführt wurden:

- Prüfung der wesentlichen historischen Grenzen anhand von Microsoft-Dokumenten, BIOS-/Dateisystemspezifikationen und Herstellerdokumentation.
- Rechnerische Prüfung der vier primären Bereiche auf Überschneidung und der logischen Volumes auf vollständige Lage innerhalb P4.
- Prüfung der maximalen LBA gegen die festgelegte 255/63-CHS-Geometrie.
- Berechnung von Volumengrößen, EBR-Positionen, FAT-Kapazitäten und Clusterzahlen für das Referenzlayout; keine Clusterzahl liegt an einer FAT-Typgrenze.

**Nicht durchgeführt:** Assemblierung eines RetroBoot-Bootloaders, Erzeugung oder Start eines bootfähigen Images, Formatierung, Original-OS-Installation, VirtualBox-/86Box-/PCem-Abnahme oder ein Test auf echter Hardware. Es existiert in Phase 1 deshalb noch kein als bootfähig auszulieferndes RetroBoot-Image.

Die wichtigsten noch offenen technischen Nachweise sind die konkrete BIOS-Geometrie, das Verhalten der gemischten EBR-Kette unter allen vorgesehenen Setups, die versteckten Typen in jedem Gast, die C:-Zuordnung und die sichere Wiederherstellung nach unterbrochenen Metadatenänderungen. Diese Punkte haben konkrete Tests und blockieren die jeweilige Freigabe.

Der nächste Implementierungsschritt ist ein kleiner Build mit eigenem MBR, Verwaltungs-VBR und Stage 2, der aus einem neuen VM-Image eine eindeutige Bootmeldung erreicht. Erst nach diesem Nachweis kommt das Menü hinzu.

## 18. Quellen und Einordnung

Abrufstand: 8. November 2026. Historische Microsoft-KB-Texte werden teils auf Archivspiegeln gelesen; Autor der fachlichen Primärquelle ist Microsoft, Betreiber des Spiegels ist nicht Microsoft. Archivierte Texte können redaktionelle und numerische Fehler enthalten. Adressgrenzen in dieser Spezifikation wurden deshalb zusätzlich selbst berechnet. Ein dokumentierter Mechanismus ist kein Nachweis für die konkrete noch nicht implementierte Kombination.

| ID | Primärquelle / Fundstelle | Verwendet für |
| --- | --- | --- |
| S01 | Microsoft: [Basic and Dynamic Disks](https://learn.microsoft.com/en-us/windows/win32/fileio/basic-and-dynamic-disks) | Vier MBR-Slots und erweiterte Partition |
| S02 | Microsoft Q246818: [Windows 95 Does Not Support Hard Disks Larger Than 32 GB](https://jeffpar.github.io/kbarchive/kb/246/Q246818/) – Archivspiegel | Windows-95-Mediengrenze |
| S03 | Microsoft Q73033: [Workarounds for the MS-DOS 1024-Cylinder Limit](https://jeffpar.github.io/kbarchive/kb/073/Q73033/) – Archivspiegel | DOS-/BIOS-Zylindergrenze |
| S04 | Microsoft Q69912: [MS-DOS Partitioning Summary](https://ftp.zx.net.nz/pub/archive/ftp.microsoft.com/MISC/KB/en-us/69/912.HTM) – Archivspiegel | FAT16-Größen und historische Partitionstypen |
| S05 | Microsoft Q126746: [Windows for Workgroups Version History](https://jeffpar.github.io/kbarchive/kb/126/Q126746/) und Q109516: [SETUP.TXT](https://jeffpar.github.io/kbarchive/kb/109/Q109516/) – Archivspiegel | DOS-Unterbau und Setupkonfiguration |
| S06 | Toshiba/Dynabook, Dokument 95030004: [32 Bit Access on greater than 528 MB HDD](https://support.dynabook.com/support/viewContentDetail?contentId=107926) | Konkretes Beispiel treiberabhängigen Windows-3.x-Plattenzugriffs |
| S07 | Microsoft Q154997: [Description of the FAT32 File System](https://www.betaarchive.com/wiki/index.php/Microsoft_KB_Archive/154997) – Archivspiegel; ergänzend [Microsoft-Dateisystemübersicht](https://learn.microsoft.com/en-us/troubleshoot/windows-client/backup-and-storage/fat-hpfs-and-ntfs-file-systems) | FAT32-Verfügbarkeit |
| S08 | Microsoft Q243450: [ScanDisk Errors on IDE Hard Disks Larger Than 32 GB](https://www.betaarchive.com/wiki/index.php?title=Microsoft_KB_Archive%2F243450) – Archivspiegel | Bestimmte Phoenix-Übersetzungen und Windows-98-IDE-Treiber |
| S09 | Microsoft Q151414: [Windows 95/98 Partition Types Not Recognized by Windows NT](https://jeffpar.github.io/kbarchive/kb/151/Q151414/) – Archivspiegel | Grenzen von NT 3.x/4.0 bei FAT32 und LBA-Typen |
| S10 | Microsoft Q224526: [Windows NT 4.0 Supports Maximum of 7.8-GB System Partition](https://jeffpar.github.io/kbarchive/kb/224/Q224526/) – Archivspiegel | Lage früher NT-Startdateien und Startpartitionen |
| S11 | 86Box: [Disk images](https://86box.readthedocs.io/en/latest/hardware/diskimages.html) | Emulierte BIOS-Grenzen und Imageformate |
| S12 | Phoenix: [BIOS Enhanced Disk Drive Specification 3.0, Revision 0.8](https://mbldr.sourceforge.net/specsedd30.pdf) – Originaldokument auf Spiegel; [T13-Dokumentenverzeichnis](https://www.t13.org/docsearch?field_author_value=&field_document_number_value=&field_document_stage_target_id=All&field_document_type_target_id_1=All&order=field_document_number&page=0&sort=asc&title=) | EDD-Prüfung und BIOS-I/O-Schnittstelle; keine Forderung nach EDD 3.0 als Mindestversion |
| S13 | GNU GRUB: [DOS/Windows](https://www.gnu.org/software/grub/manual/grub/html_node/DOS_002fWindows.html) | Referenz für Chainloading und Partitionsverstecken; keine Codeübernahme |
| S14 | Microsoft Q51978: [Order in Which MS-DOS and Windows Assign Drive Letters](https://jeffpar.github.io/kbarchive/kb/051/Q51978/) – Archivspiegel | Historische Buchstabenvergabe |
| S15 | Microsoft: [FAT-Spezifikation 1.03](https://www.isdaman.com/alsos/protocols/fats/fatgen103.pdf) – Originaldokument als PDF-Spiegel; [offizieller Bezug von fatgen103.doc](https://www.microsoft.com/en-us/download/details.aspx?id=53426) | BPB, Clusterzahlen und FAT-Strukturen |
| S16 | NASM: [Output Formats](https://www.nasm.us/doc/nasm09.html) | Binär- und Objektformate |
| S17 | Open Watcom: [C/C++ User's Guide](https://open-watcom.github.io/open-watcom-v2-wikidocs/cguide.html), [C Language Reference](https://open-watcom.github.io/open-watcom-v2-wikidocs/clr.html) | C/16 und Segment-/Zeigermodelle |
| S18 | Phoenix/IBM: [El Torito Bootable CD-ROM Format Specification 1.0](https://www.ardent-tool.com/storage/specscdrom.pdf) – Originaldokument auf Spiegel | BIOS-Start der Rettungs-CD |
| S19 | QEMU: [System invocation](https://www.qemu.org/docs/master/system/invocation.html) | IDE-Images, Arbeitskopien und Snapshot-Verhalten |
| S20 | Microsoft KB895556: [Setup behavior in Windows x64-based editions](https://mskb.pkisolutions.com/kb/895556) und KB896455: [x64 installation and dual-boot guidance](https://mskb.pkisolutions.com/kb/896455) – Archivspiegel | Eigene passende NT-/x64-Loaderdateien je Installation |

Quellen werden verlinkt, nicht als vollständige fremde Dokumente mitgeliefert. Diese Spezifikation beschreibt einen eigenen Entwurf. Eine spätere Freigabe muss sich auf die tatsächlich gebauten Artefakte und die protokollierten Tests beziehen.
