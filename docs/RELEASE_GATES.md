# Release Gates

Ein GitHub-Upload bedeutet **nicht** automatisch Produktionsfreigabe.

## Gate 0 — Repository / Static

Muss grün sein:

```bash
python scripts/validate_python_syntax.py
python scripts/validate_prompt_assets.py
python scripts/validate_prompt_domain.py
python scripts/validate_static.py
python scripts/validate_repo.py
for f in scripts/*.sh backup/*.sh; do bash -n "$f"; done
```

## Gate 1 — GitHub CI

Workflow `.github/workflows/ci.yml` muss grün sein:

- Python-Abhängigkeiten
- PostgreSQL 18 / Redis
- Migration Drift
- Migrationen
- Seed Defaults / PM20 / FAQ
- 194 Prompt-Smoke-Tests
- MCP-/FAQ-Runtime-Sanity
- Django Check/Test Suite
- Backend-Docker-Build
- Marketing/Caddy-Docker-Build
- Marketing Node Tests/Lint/Build

## Gate 2 — Ubuntu 24.04 Staging

```bash
cp .env.example .env
# sichere Werte setzen
./scripts/bootstrap.sh
./scripts/runtime_validate.sh
```

Erst `RUNTIME VALIDATION OK` gilt als lokaler Stack-Nachweis.

## Gate 3 — Externe Integrationen

- Mollie Sandbox Kauf / Webhook / Refund / Chargeback
- Microsoft Graph Produktions-Mailadapter
- externer S3/restic Backup-Zieltest
- Restore-Drill

## Gate 4 — Browser / Security / Performance

- 360/390, 768, 1440, 1920 px
- Chrome/Edge, Firefox, relevante Safari-Varianten
- Tenant/IDOR/Permission-Negativtests
- 2FA/Auth/Invite/Device/Deep-Link
- 100k DataGrid Seed / p95 Ziele

## Gate 5 — Human Review / Produktion

- Rechtstexte freigegeben
- Production Domain/DNS
- Live Provider-Secrets
- Monitoring/Alert-Empfänger
- Backup/Notfallzugang dokumentiert
- Human Review der CI-/Security-Ergebnisse

## GitHub-RC14 Zusatzgates — Pro-Runtime und Marketing

Vor GitHub-Import zusätzlich:

```bash
python scripts/validate_runtime_catalog.py
```

Optional bei installiertem Chromium + Playwright:

```bash
python scripts/browser_runtime_smoke.py
python scripts/browser_marketing_smoke.py
```

Der Pro-Browser-Smoke muss 34 eindeutige App-Kacheln rendern und Compose sowie Rating/Feedback über die Server-API ausführen. Der Marketing-Smoke prüft öffentliche Free/Pro-Karten, 2,99-EUR-Anzeige, 34-App-/28-Zusatz-App-Synchronisierung, 20 FAQ und das Partikelkopf-Canvas. Der unveränderte Pro-Golden-Master bleibt Referenz; die abgeleitete Runtime lädt den veröffentlichten PromptDomain-Katalog serverseitig.
