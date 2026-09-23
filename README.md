# PromptMaster Commercial Platform — konsolidierter Release-Stand

Konsolidierter Gesamtstand der belegbaren PromptMaster-Entwicklung mit Marketing-/Vertriebsfrontend, Free/Pro V2, Commercial Backend und erhaltener historischer Transfer-/Designprovenienz.

> **Status 23.09.2026:** Der konsolidierte `main`-Stand hat die internen automatisierten Release-Gates vollständig bestanden: Shell-/Dependency-Security, 292 Django-Tests (6 absichtliche Performance-Skips), separates 100k-DataGrid-Gate, 34 Apps / 194 Tasks / 194 Prompt-Smokes, Chromium/Firefox/WebKit Browser-Smoke sowie Full-Stack-Bootstrap, Idempotenz, HTTP-Lasttest, Backup-Restore-Recovery und External-Caddy-Rehearsal. Eine echte Produktionsfreigabe erfordert zusätzlich die provider-/infrastrukturabhängigen Gates und die menschliche Freigabe aus `docs/RELEASE_GATES.md` und `docs/PRODUCTION_ACCEPTANCE.md`.

Der vollständige Dateiindex liegt in `docs/COMPLETE_FILE_INVENTORY.md`; `FILE_MANIFEST.tsv` und `MANIFEST.json` sichern Pfad, Größe, SHA256 und Rolle jeder inventarisierten Repository-Datei. Die Original-Recovery-ZIPs der beiden zuletzt gelieferten Quellen sind unverändert unter `archive/source-packages/` enthalten.

## Verbindliche Dokumente

- `docs/SOURCE_OF_TRUTH.md`
- `SPEC.md`
- `docs/REQUIREMENTS_STATUS_V3.md`
- `docs/PROJECT_CHAT_FORENSICS_V3.md`
- `docs/PRIVACY_DATA_FLOW.md`
- `docs/RELEASE_GATES.md`
- `docs/GITHUB_TRANSFER.md`
- `docs/GITHUB_READY_STATUS.md`

## Enthaltene Hauptbereiche

- Marketing-/Vertriebsfrontend mit Three.js-Partikelkopf, Nachtlandschaft, Preis-/Vergleichs-/FAQ-Bereichen
- Caddy-Integration: öffentliche Marketingseite + serverseitige Produkt-/Auth-/Portal-Routen
- Django Commercial Backend
- PostgreSQL / Redis / Celery Worker + Beat
- Kundenportal
- separates netstyle Admin
- Auth / 2FA / Tenant / generisches RBAC
- Produkte / Preisversionen / individuelle 365-Tage-Lizenzen
- Seats / Zuweisung / Freigabe / Gerätebindung
- Mitarbeiter-Pro-Anfrage und Admin-Entscheidung
- gehashter, tenant-/usergebundener Einmal-Zuordnungslink
- Mollie / idempotente Webhooks / Refund / Chargeback
- Legal / Audit / Datenschutzexport
- Supporthistorie
- Operations / Backup / Restore-Test / Worker / Beat
- zentrale Prompt-Domain mit 34 Apps / 194 PM20 Tasks
- 16 Free-Kernaufgaben als Legacy-Verträge
- Microsoft Tier / Capabilities getrennt von PromptMaster-Entitlements
- stateless serverseitiger Prompt Composer
- Prompt Studio / Testfälle / Versionen / Lifecycle
- 1–5-Sterne-Ratings / Qualitätsanalyse / Drop-Erkennung
- internes MCP für read/draft/test; **kein Publish/Delete**
- zentrale FAQ-Verwaltung/API
- GitHub CI und Betriebs-/Validierungsskripte

## Monorepo-Struktur

- `marketing/` — aktives Marketing-/Vertriebsfrontend, Build in `Dockerfile.caddy`
- `backend/` — Django Commercial Platform
- `product/` — Free-/Pro-Golden-Master und abgeleitete Runtime
- `archive/` — vollständige historische Chat-Transfer-/UI-/Designreferenzen, nicht produktiv
- `tools/recovery/` — Wiederherstellungswerkzeuge, u. a. exakter V13-Git-Exporter
- `docs/recovery/` — forensische und historische Recovery-Dokumentation

Die vollständige Zusammenfassung steht in `docs/COMPLETE_PROJECT_SUMMARY.md`; die Merge-Provenienz in `docs/MERGE_PROVENANCE.md`.

## Golden Master

Die exakten aktuellen Free-/Pro-Dateien liegen unter `product/golden_masters/` und werden per SHA256 geschützt.

- Free: `aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8`
- Pro: `aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf`

Der aktuelle Pro-Golden-Master ist PM20 mit **34 Apps / 194 Tasks**. PM11-160 bleibt historische Provenienz und wird nicht als aktuelle Produktdatei rekonstruiert. Die produktive Pro-Runtime ist eine deterministische, hash-geschützte Ableitung des unveränderten Golden Masters und lädt ihren sichtbaren 34/194-Katalog aus der veröffentlichten serverseitigen PromptDomain.

## Zentrale Endpunkte

- PromptMaster Free V2: `/free/`
- PromptMaster Pro V2: `/pro/app/`
- Free Legacy/Rollback: `/free-old/`
- Pro Legacy/Rollback: `/pro-old/`
- Kundenportal: `/portal/dashboard/`
- Pro-Zugang/Entitlement-Einstieg: `/pro/`
- netstyle Backend: `/ns-admin/`
- Prompt Studio: `/ns-admin/prompt-studio/`
- FAQ-Pflege: `/ns-admin/content/faqs/`
- Prompt API: `/api/v1/prompts/`
- Rating API: `/api/v1/prompts/<task_id>/rating/`
- Content API: `/api/v1/content/faqs/`
- interner MCP: `/api/v1/mcp/`
- MCP Health: `/api/v1/mcp/health/`
- Operations API: `/api/v1/ops/`
- Mollie Webhook: `/api/webhooks/mollie/`
- Datenschutzexport: `/portal/privacy/export/`

## Statische Validierung

```bash
python scripts/validate_python_syntax.py
python scripts/validate_prompt_assets.py
python scripts/validate_prompt_domain.py
python scripts/validate_runtime_catalog.py
python scripts/validate_marketing.py
python scripts/validate_static.py
python scripts/validate_repo.py
for f in scripts/*.sh backup/*.sh; do bash -n "$f"; done
```

## Staging Bootstrap

Voraussetzung: Ubuntu 24.04 LTS / amd64, Docker Engine + Docker Compose Plugin.

```bash
cp .env.example .env
# sichere CHANGE_ME-Werte setzen
./scripts/bootstrap.sh
```

Der Bootstrap migriert, seedet Rollen/Produkte, **34/194 PromptDomain**, **194 Smoke-Tests**, zentrale FAQ, legt den initialen Admin an, startet Stack und führt die Django-Test-Suite aus. Bei automatisch erzeugtem Staging-Admin stehen die aktuell gültigen Zugangsdaten ausschließlich in `.bootstrap-credentials` (0600); die Datei ist Git-ignoriert.

## Produktion: einmaliger Erstadmin

In Produktion bleibt `INITIAL_ADMIN_PASSWORD` in `.env` leer bzw. `DISABLED`. Ein dauerhaftes Bootstrap-Passwort in der Produktionskonfiguration ist ausdrücklich nicht vorgesehen. Nach dem ersten erfolgreichen `./scripts/deploy.sh` wird der erste Superadmin einmalig aus temporären Prozessvariablen angelegt:

```bash
read -r -p 'Initiale Admin-E-Mail: ' INITIAL_ADMIN_EMAIL
read -r -s -p 'Initiales Admin-Passwort: ' INITIAL_ADMIN_PASSWORD
echo
export INITIAL_ADMIN_EMAIL INITIAL_ADMIN_PASSWORD

docker compose -f compose.yaml -f compose.production.yaml run --rm \
  -e INITIAL_ADMIN_EMAIL -e INITIAL_ADMIN_PASSWORD \
  web python manage.py bootstrap_admin

unset INITIAL_ADMIN_PASSWORD INITIAL_ADMIN_EMAIL
```

Das Passwort wird dabei **nicht** in `.env`, Git oder ein Repository-Artefakt geschrieben. Der neu angelegte Superadmin muss beim ersten Login 2FA einrichten. Für spätere Deployments wird `bootstrap_admin` nicht benötigt.

## Runtime Acceptance

```bash
./scripts/runtime_validate.sh
```

Der Runtime-Validator prüft u. a. Migration Drift, Migrationen, Seeds, 194 Prompt-Smokes, MCP/FAQ, Test-Suite, `check --deploy`, Django Ready, Worker-Ping, Beat-Heartbeat und Golden-Master-Hash.

## GitHub

Ein-Kommando-Preflight/Initialisierung:

```bash
./scripts/github_prepare.sh
```

Siehe `docs/GITHUB_TRANSFER.md`. Das Repository ist für einen privaten GitHub-Erstimport vorbereitet; `.env`, `.bootstrap-credentials`, Secrets, DB-/Backup-Artefakte und lokale Runtime-Daten gehören nicht ins Repository.

## Noch extern zu bestätigen

Die GitHub-/Docker-/Browser-/Security-/100k-Gates sind für den konsolidierten Release-Stand automatisiert grün nachgewiesen. **Nicht durch CI ersetzbar** und deshalb vor einem echten Go-Live weiterhin extern abzunehmen sind:

- Deployment auf dem tatsächlichen Zielhost inklusive öffentlicher Domain/DNS/TLS
- Mollie Sandbox E2E über den echten öffentlichen Webhook, einschließlich Refund/Chargeback
- Microsoft Graph Mail E2E inklusive Exchange Application-RBAC-Scope-Nachweis
- externer S3/restic Backup-/Restore-Drill
- reale Monitoring-/Alert-Empfänger und dokumentierter Notfallzugang
- Rechtstexte/Steuerprüfung und menschliche Produktionsfreigabe
- bewusste Marketing-Freigabe des integrierten 06.09.-Source-Stands; die historische V15-Provenienz bleibt davon getrennt dokumentiert

Details und verbindliche Evidenz stehen in `docs/PRODUCTION_ACCEPTANCE.md` und `docs/RELEASE_GATES.md`.
