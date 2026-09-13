# PromptMaster – Forensischer File-Library-/Archiv-Scan

Datum: 2026-09-12
Ziel: Verlustfreie Rekonstruktion aller greifbaren PromptMaster-Quellen als Grundlage für einen vollständigen lauffähigen Integrationsstand.

## 1. Physisch materialisierte Archive vollständig gelesen

Der rekursive Archivscanner hat alle in `/mnt/data` greifbaren PromptMaster-Archive geöffnet, verschachtelte Archive ebenfalls entpackt und alle eindeutigen Text-/Code-Dateien zeilenweise gelesen. Binärdateien wurden inventarisiert und gehasht.

- Archiv-Records inkl. verschachtelter/duplizierter Archive: **18**
- Datei-Records über alle Archive: **4.341**
- eindeutige Datei-Hashes: **1.036**
- eindeutige Text-/Code-Dateien: **625**
- gelesene Textzeilen: **85.345**
- relevante Trefferzeilen im Vollscan: **13.969**
- Extraktionsfehler: **0**

## 2. Geöffnete/rekursiv geprüfte Hauptarchive

- `PromptMaster_FORENSIC_RECOVERY_AND_SOURCE_INDEX_2026-09-12(1).zip`
- `PromptMaster_PROJECT_TRANSFER_RC10_2026-09-12.zip`
- `PromptMaster_MASTER_PROJECT_RECONSTRUCTION_PREMERGE_2026-09-12.zip`
- darin: `PromptMaster_PROJECT_TRANSFER_FINAL_FROM_ORIGINAL_CHAT_2026-09-12.zip`
- darin: `PromptMaster-Commercial-Sicherung-2026-09-06.zip`
- darin: `PromptMaster_PROJECT_TRANSFER_GOLDEN_INTEGRATED_2026-09-12.zip`
- darin: `PromptMaster_PROJECT_TRANSFER_FULL_2026-09-12.zip`
- darin: `PromptMaster_PROJECT_TRANSFER_CHAT_6aa43192_FINAL_2026-09-12.zip`
- darin: `PromptMaster_UI_Prototype_V1_1.zip`
- darin: `PromptMaster_UI_Prototype_V1_1_FIXED.zip`
- `PromptMaster_CHAT_RECOVERY_ALL_AVAILABLE_2026-09-12(1).zip`
- `PromptMaster_COMPLETE_PROJECT_TRANSFER_2026-09-12(1).zip`

Duplikate wurden anhand SHA256 erkannt und nicht fälschlich als neue Quellen gewertet.

## 3. Wichtigste technische Rekonstruktionsbefunde

### Materialisiert und belastbar

- RC10 ist der vollständigste physisch materialisierte Commercial-/Django-Baum.
- Aktuelle Free-/Pro-Golden-Master sind bytegenau vorhanden und gehasht.
- Aktueller Pro-Katalog: 34 Apps / 194 Tasks.
- Free-Kernumfang: 16 Free-Tasks; historische Free-/Pro-Stände sind zusätzlich erhalten.
- Marketing-Source-Snapshot vom 06.09. ist vollständig erhalten und entspricht bytegenau der verschachtelten Sicherung `PromptMaster-Commercial-Sicherung-2026-09-06.zip`.
- Marketing-Worklog enthält die Commit-/Archiv-Provenienz für V13/V14/V15.
- Master Spec V1.0 mit 162 Requirement-Records, 92er Branch-Matrix und zusätzlichen Cross-Chat-Anforderungen sind erhalten.

### Nicht im materialisierten Sourcecode gefunden

Der Volltextscan über **alle 85.345 Zeilen** ergab keinen realen Django-/Python-Implementierungsfund für:

- `class PromptDefinition`
- `class PromptVersion`
- `PromptComposer`
- `MicrosoftTier`
- `MicrosoftCapability`
- eine konkrete `PromptRating`-Modelimplementierung
- einen realen MCP-Sourcebaum hinter `/api/v1/mcp/`
- einen realen Prompt-API-Sourcebaum hinter `/api/v1/prompts/`
- einen vollständigen `UpgradeRequest`-Workflow
- einen vollständigen kundenbezogenen `DataExport`-Workflow

Die Begriffe erscheinen in Requirements, Transfer-/Gap-Dokumenten und dem späteren RC1-README, nicht aber als physisch vorhandener Backend-Code in den materialisierten Archiven.

## 4. File-Library-Rekonstruktion

Die File Library wurde mit Datums-, Namens- und Inhaltsabfragen über den relevanten PromptMaster-Zeitraum durchsucht. Zusätzlich wurden lange HTML-/Textquellen per Vollansicht geöffnet, soweit das File-Library-System sie ausliefert.

Wesentliche wiedergefundene Produktquellen:

- `netstyle_CopilotPromptMaster_PRO_1.1.html` – Legacy-Stand mit 160 Szenarien
- `netstyle_CopilotPromptMaster_PRO_3.3_PROMPTS_APP_SPEZIFISCH.html`
- `netstyle_CopilotPromptMaster_Free_V1.2.1_KORRIGIERT.html`
- `netstyle_CopilotPromptMaster_Free_V1.2.4_PROMPTS_AUSFORMULIERT.html`
- `DOC-20260905-WA0007.html`
- `netstyle_PromptMaster_Expanded_Apps_Demo.html`
- historische V7/V8/V9/V10/V11/V15/V19/V20 usw.
- Marketing-Worklogs `markdown.md eingefügt`
- `PromptMaster Commercial.txt`
- `SPEC.md`, `bootstrap.sh`, `compose.yaml`, UI-Prototypen und weitere Phase-2-Artefakte

### Wichtiger RC1-Fund

Ein späteres `README.md` mit Titel **„PromptMaster Commercial Platform — GitHub Release Candidate 1“** ist vorhanden. Es behauptet einen bereits konsolidierten RC1 mit:

- zentraler Prompt-Domain
- 34 Apps / 194 Tasks
- Microsoft Tier/Capabilities
- serverseitigem Composer
- Prompt Studio/Lifecycle/Ratings/Quality
- internem MCP
- FAQ-API
- erweiterten Validatoren

Der dazugehörige vollständige Sourcebaum bzw. ein verifiziertes RC1-Archiv konnte trotz gezielter Suche nach Quell-Signaturen, Endpoints, Dokumentnamen und Archiven **nicht wiederbeschafft werden**. Damit darf das README nicht als Ersatz für fehlenden Code verwendet werden.

## 5. Marketing-Provenienz

- V13 Commit: `d36033bdfc87ee5dbacd8459c8cca919ec2f2b45`
- V14 Commit: `7f6e3bb95290096f421163e691931e398a4a326d`
- V15 Commit: `2f78921327346233c3f31053eeb670fc372ca1fb`
- V15 Archiv SHA256: `ae5035e4ec45ce107fbac502453ce8894960c61386c2a83dc5a60be77a1fa0e7`
- V15 Archivgröße: 3.297.280 Byte
- V15 Dateizahl: 28

Das exakte V15-Archiv ist derzeit nicht physisch im Runtime-Dateisystem vorhanden. Der 06.09-Source-Snapshot ist deshalb als Rekonstruktionsbasis, nicht als umetikettiertes V15, zu behandeln.

## 6. Konsequenz für die lauffähige Gesamtversion

Da der behauptete spätere RC1-Code nicht physisch wiederhergestellt werden konnte, ist die belastbare Vorgehensweise:

1. RC10 unverändert als Backend-Basis sichern.
2. Aktuelle Free-/Pro-Golden-Master als Regression-Referenzen unverändert behalten.
3. Prompt-Katalogdaten aus den wiedergefundenen aktuellen CSV-/HTML-Quellen verlustfrei zentralisieren.
4. Fehlende PromptDomain / MicrosoftTier / Composer / Studio / Rating / Quality / MCP anhand der verbindlichen Requirements neu auf RC10 implementieren.
5. Branch-spezifische Restlücken (Deep-Link, Upgrade-Anfrage, Datenexport usw.) ergänzen.
6. Marketing aus dem erhaltenen 06.09-Source-Snapshot plus nachweisbaren V13–V15-Diffs rekonstruieren.
7. Danach statische, Django-, Runtime-, Security-, Browser-, Visual-, Mollie-, Mail-, Backup-/Restore- und Performance-Gates ausführen.

## 7. Grenze der File-Library-API

Die File-Library-Suche kann den bereitgestellten UI-Collection-Link nicht als Ordner-Iterator öffnen und liefert keine garantierte vollständige Liste aller unsichtbaren Collection-Einträge. Deshalb wird nicht behauptet, dass ein im UI eventuell verborgenes und von der Suche nie ausgeliefertes Objekt physisch gelesen wurde. Alle **von der File Library ausgelieferten PromptMaster-relevanten Quellen** wurden jedoch gezielt ausgewertet; alle **im Runtime-Dateisystem vorhandenen Archive** wurden vollständig rekursiv geöffnet und zeilenweise bzw. binär-forensisch verarbeitet.
