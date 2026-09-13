# GitHub Ready Status — RC14 Full Repository

Stand: 2026-09-13

## Lokal grün nachgewiesen

- Marketing-Source + deploybarer Dist-Stand vorhanden
- Marketing Node-Test-Suite 11/11 grün
- Marketing-/Caddy-Integrationsvalidator grün
- Headless-Chromium-Marketing-Smoke grün (Preis, 34-App-Brücke, 20 FAQ, Partikelkopf-Canvas)
- Python-Syntax: 214 Dateien (Stand vor finalem Manifest-Generator; tatsächliche Zahl wird im Preflight ausgegeben)
- Free/Pro Golden-Master-Hashes korrekt
- deterministische Pro-Runtime korrekt
- PromptDomain: 34 Apps / 194 PM20-Tasks / 16 Free-Legacy-Verträge
- Composer-Smoke: 194/194 ohne ungelöste Platzhalter
- Runtime-Katalog-Guard: zentraler Serverkatalog aktiv
- statische Repository-Validierung
- Secret-Guard
- Shell-Syntax aller Betriebs-/Backupskripte
- YAML-Syntax Compose + GitHub Actions
- Headless-Chromium-Smoke:
  - 34 eindeutige Apps sichtbar
  - zentraler Katalog ersetzt historische 16-App-Darstellung
  - PM20-001 sendet Pflichtfelder an Server-Compose
  - Serverergebnis wird angezeigt
  - Rating 1–5 funktioniert
  - optionales Feedback erscheint nur für 1–3 Sterne und wird gesendet

## In GitHub CI vorgesehen

- PostgreSQL 18 + Redis
- Migration Drift
- Migrationen
- Defaults / Prompt-Katalog / FAQ Seeds
- `validate_prompt_runtime`
- vollständige Django-Tests
- `collectstatic`
- Compose-Konfiguration
- Backend-Docker-Build
- Caddy-/Marketing-Multistage-Docker-Build
- separater Playwright/Chromium-Browser-Smoke

## Noch nicht lokal beweisbar in dieser Build-Umgebung

Hier stehen weder Docker noch Django/psycopg/Celery zur Verfügung. Deshalb bleibt die tatsächliche Runtime-Abnahme bis zum ersten grünen GitHub-Actions-Lauf bzw. Ubuntu-24.04-Staging-Lauf offen.

## Staging-Abnahme

Nach grünem CI:

```bash
cp .env.example .env
./scripts/bootstrap.sh
./scripts/runtime_validate.sh
```

Der Runtime-Validator startet zusätzlich das lokale Staging-Restic-Repository, erzeugt ein PostgreSQL-Backup und verlangt einen erfolgreichen Restore-Test. Das ersetzt nicht den späteren externen S3-Produktionsdrill.

## Bekannte externe Go-Live-Gates

- Mollie Sandbox E2E inklusive Refund/Chargeback
- Microsoft Graph Mail E2E
- externer S3/restic Backup-/Restore-Drill
- Tenant/IDOR/Auth/2FA/Device E2E
- 100k DataGrid Performance
- responsive Browserabnahme
- Rechtstexte / Steuerprüfung
- formale Freigabe des integrierten vollständigen 06.09.-Marketing-Sources oder Wiederbeschaffung des exakten V15-Archivs
