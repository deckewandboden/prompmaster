# PM-CHG-2026-09-12-001 — Zentrale Prompt-Domain + serverseitiger Composer

**Status:** implementiert in RC11, Runtime-Abnahme offen  
**Basis:** Master-Spezifikation V1.0 + spätere belegte Anforderungen aus Prompt-System-Zweig `6aa43192...`

## Änderung

Der bisherige RC10-Zustand lieferte PromptMaster Pro nach Lizenz-/Geräteprüfung als private statische Golden-Master-Datei aus. Die eigentliche Promptlogik war nicht als zentrale Server-Domain materialisiert.

RC11 ergänzt additiv:

- zentrale, versionierte Prompt-Domain;
- PM20-Katalog 34 Apps / 194 Tasks als Datenbank-/Seed-Struktur;
- versionierte globale Prompt-Policies;
- Pflicht-/Optionalfelder und Auswahloptionen;
- getrenntes Microsoft-Tier-/Capability-Modell;
- Produktentitlements pro App/Task;
- stateless serverseitigen Composer;
- Prompt API;
- 16 Free-Legacy-Verträge als explizit noch nicht gemappte Provenienz.

## Betroffene Anforderungen

- PROMPT-044 — PromptDefinition/PromptVersion
- PROMPT-045 — serverseitige Komposition
- PROMPT-050 — 16 Free-Kernaufgaben erhalten
- PROMPT-052 — Prozentanzeige
- PROMPT-053 — Quellen-/Kontextmodus
- PROMPT-054 — task-spezifische Ausgabeformate
- PROMPT-055 — Schwerpunkte/Empfohlen
- PGEN-003 — zentraler Katalog
- PGEN-004/PGEN-005 — Microsoft-Tier getrennt vom PromptMaster-Entitlement
- PGEN-006/PGEN-007 — task-spezifische Felder und Prompt-Metadaten
- PGEN-010/PGEN-011 — Qualitätsregeln / ausformulierte Prompts

Prompt Studio, Ratings/Qualitätsanalyse und MCP sind **nicht Bestandteil dieser Change-Implementierung** und bleiben separate Folgeschritte.

## Datenbank / Migration

Neue Django-App `apps.prompts` mit `prompts/0001_initial.py`.

Neue Kernmodelle:

- MicrosoftTier
- PromptApplication
- PromptDefinition
- PromptPolicySet
- PromptVersion
- PromptField
- PromptOption
- MicrosoftCapability
- PromptLegacyContract

## UI-Auswirkung

Keine Änderung der bytegenauen Free-/Pro-Golden-Master. RC11 stellt zunächst eine zentrale API/Domain bereit. Die spätere Umstellung der Produktoberflächen auf diese API benötigt einen eigenen Browser-/Parity-Gate.

## Security / Privacy

- Pro-API: Login + aktive Pro-Lizenz + registriertes Gerät.
- Entitlement und Microsoft-Tier serverseitig geprüft.
- Composer speichert keine Prompteingaben und keinen erzeugten Prompt.
- API-Antworten `Cache-Control: no-store`.
- Der frühere kundensichtbare „lokal im Browser“-Datenschutztext ist vor produktiver Aktivierung des Server-Composers anzupassen; Statelessness macht den Request nicht zu einer lokalen Browser-Verarbeitung.

## Testauswirkung

Neue Gates:

- exakter Golden-Master-Extraktionsvergleich;
- 34/194 Katalogintegrität;
- 16 Free-Legacy-Verträge;
- 194/194 pure Composer-Smokes;
- Pflichtfeld-/Choice-/Tierprüfung;
- maxChars;
- kein Feldverlust bei Tasks ohne `TASK_CONTEXT_SPEC`;
- DB-Seed-/Entitlement-/API-Tests im Django-Testlauf.

## Freigabegrenze

Statisch/pure Python kann RC11 in dieser Arbeitsumgebung validiert werden. Django/PostgreSQL/Redis/Celery müssen über `scripts/runtime_validate.sh` auf dem Ubuntu/Docker-Testserver bestätigt werden, bevor dieser Change als runtime-grün gilt.
