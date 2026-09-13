# Zentrale Prompt-Domain und serverseitiger Composer — RC11

## Herkunft / Source of Truth

Der Prompt-Kern wurde aus dem **aktuellen, hash-geschützten Pro-Golden-Master** materialisiert. Er umfasst 34 Anwendungen und 194 eindeutige PM20-Tasks. Die Golden-Master-Datei selbst wird nicht verändert.

- Pro SHA256: `aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf`
- Free SHA256: `aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8`
- PM20-Extrakt: `backend/apps/prompts/data/pm20_golden_logic.json`
- Free-Provenienz: `backend/apps/prompts/data/free_legacy_tasks.json`

## Domainmodell

`apps.prompts` führt die zuvor im Client verteilte Promptlogik zentral zusammen:

- `PromptApplication` — Anwendung/App einschließlich Produktmetadaten und App-Regel.
- `PromptDefinition` — stabile zentrale Task-ID (`PM20-...`).
- `PromptPolicySet` — versionierte globale Quellen-, Methoden-, Qualitäts-, Ton- und Detailregeln.
- `PromptVersion` — versionierter Task-Inhalt mit Lifecycle `DRAFT → TEST → REVIEW → APPROVED → PUBLISHED → ARCHIVED`; jede Version ist an ein Policy-Set und an einen App-Regel-Snapshot gebunden.
- `PromptField` — Pflicht-/Optionalfelder.
- `PromptOption` — Source/Output/Focus/Audience.
- `MicrosoftTier` / `MicrosoftCapability` — Microsoft-Lizenz-/Capability-Schicht unabhängig vom PromptMaster-Produktentitlement.
- `PromptLegacyContract` — revisionssichere historische Free-/PM11-Verträge ohne stilles ID-Umschreiben.

Pro PromptDefinition darf die Datenbank höchstens eine `PUBLISHED` Version gleichzeitig enthalten. Prompt-Versionen pinnen ihr Policy-Set; spätere globale Regeländerungen verändern daher bereits veröffentlichte Versionen nicht rückwirkend.

## Entitlements

PromptMaster-Produktrecht und Microsoft-Tier werden getrennt geprüft:

1. `ProductEntitlement(prompt.task.<PM20-ID>)` muss für das gewählte PromptMaster-Produkt aktiv sein.
2. Microsoft-Tier muss mindestens den App-/Task-Capability-Rang erfüllen.

Seed-Tiers aus dem Golden Master:

- `chatbasic` = 0 — Copilot Chat
- `m365basic` = 1 — M365 Copilot (Basic)
- `premium` = 2 — Microsoft 365 Copilot Business

## Composer

`apps.prompts.composer_core` ist reines Python ohne Django-Abhängigkeit. Der Service ist **stateless**:

- validiert Pflichtfelder;
- validiert Audience, Focus, Output, Source, Tone und Detail gegen die veröffentlichte Task-Version;
- erzwingt Microsoft-Tier;
- übernimmt task-spezifische Pflicht-/Optionalfelder;
- verwendet die Golden-Master-Methode und Qualitätsregel der jeweiligen Task-Familie;
- übernimmt Quellenstrategie, Zielgruppe, Fokus, Ausgabeformat, Detailtiefe, Tonalität und App-Regel;
- fügt die verbindliche No-Fabrication-Regel an;
- respektiert `maxChars`;
- berechnet den bekannten Prompt-Fortschritt;
- speichert weder Benutzereingaben noch den erzeugten Prompt.

### Kontext-Parität

Der aktuelle Pro-Golden-Master enthält 80 handgeschriebene `TASK_CONTEXT_SPEC`-Vorlagen bei 194 Tasks. Für diese 80 Aufgaben wird die Formulierung semantisch 1:1 übernommen.

114 spätere PM20-Tasks besitzen zwar konkrete Pflicht-/Optionalfelder, aber keine solche Kontextvorlage. Der Browser-Golden-Master würde deren eingegebene Feldwerte beim Komponieren sonst verlieren. RC11 verhindert diesen Datenverlust mit einem deterministischen Fallback:

`Berücksichtige dabei diese konkreten Angaben: Feld: „Wert“; ... .`

Dieser Fallback erfindet keine Inhalte und ist durch den 194/194-Kompositionstest abgesichert. Er ist bewusst dokumentiert und kein stiller Golden-Master-Umbau.

## API

### Katalog

`GET /api/v1/prompts/?product=PRO`

### Task

`GET /api/v1/prompts/PM20-001/?product=PRO`

### Compose

`POST /api/v1/prompts/compose/`

Beispiel:

```json
{
  "product": "PRO",
  "task_id": "PM20-001",
  "microsoft_tier": "chatbasic",
  "input": {
    "fields": {
      "Fragestellung": "Wie verbessern wir den Support?",
      "Kontext": "B2B-Systemhaus"
    },
    "audience": "Management",
    "focus": ["Primärquellen", "Aktualität"],
    "output": "Fundierte Antwort",
    "source": "webwork",
    "tone": "professional",
    "detail": "standard"
  }
}
```

Antwort enthält unter anderem `prompt`, `progress_percent`, `policy_version`, `prompt_version` und explizit `persisted: false`.

## Security / Privacy

- Pro-Endpunkte: Login + aktive Pro-Lizenz + registriertes Gerät.
- Server prüft Produktentitlement und Microsoft-Tier; Clientangaben allein autorisieren nichts.
- `Cache-Control: no-store` für Prompt-API-Antworten.
- keine Prompt-/Input-Persistenz im Composer.
- Free bleibt unverändert standalone, bis das Legacy→PM20-Mapping geprüft ist.

Der frühere kundensichtbare Datenschutztext „alles lokal im Browser“ muss vor Aktivierung der serverseitigen Komposition gegenüber Endkunden an den tatsächlichen Datenfluss angepasst werden. Die technische Architektur minimiert diesen Datenfluss durch Statelessness und fehlende Promptpersistenz, macht ihn aber nicht „lokal-only“.

## Seed / Reproduzierbarkeit

`python manage.py seed_prompt_catalog`

Der Seed:

1. prüft den Pro-Golden-Master-Hash;
2. importiert 34 Apps / 194 PM20-Tasks;
3. importiert Felder/Optionen/Policies;
4. setzt Microsoft-Tiers/Capabilities;
5. erzeugt PRO-Task/App-Entitlements;
6. erhält 16 Free-Legacy-Verträge als `unmapped`;
7. überschreibt keine Version mit abweichendem Source-Hash;
8. reaktiviert bei später existierender freigegebener Version nicht stillschweigend V1.

## Tests

Statisch/pure Python:

`python scripts/validate_prompt_domain.py`

Django/DB:

`python manage.py test apps.prompts`

Der Runtime-Validator führt Migration, Seed, Tests und einen Count-Smoke (`34/194/16`) auf dem Docker-Host aus.
