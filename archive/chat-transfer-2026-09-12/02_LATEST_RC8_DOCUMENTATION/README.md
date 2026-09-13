# PromptMaster Commercial Platform — Release Candidate 1

Verbindliche Grundlage: `SPEC.md`.

## Staging

1. Ubuntu 24.04 LTS mit Docker Engine + Compose Plugin bereitstellen.
2. Repository kopieren oder aus privatem Git-Repository klonen.
3. `cp .env.example .env` und alle `CHANGE_ME`-Werte ersetzen.
4. Fernet-Key erzeugen: `docker run --rm python:3.13-slim python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
5. `./scripts/bootstrap.sh`

## URLs
- Kundenportal: `/portal/dashboard/`
- netstyle Backend: `/ns-admin/`
- Operations API: `/api/v1/ops/*`
- Mollie Webhook: `/api/webhooks/mollie/`
- Mailpit Staging: `http://127.0.0.1:8025`

## Validierung
- `python3 scripts/validate_static.py`
- `./scripts/runtime_validate.sh` auf einem Docker-fähigen Host

## Branding
`backend/static/brand/promptmaster-logo-reference.png` wurde pixelgenau aus der im Projekt vorhandenen visuellen PromptMaster-Referenz übernommen; es wird nicht durch CSS nachgezeichnet.

## Produktionsfreigabe
Erst nach erfolgreichem Runtime-Validation-Lauf, Mollie-Sandbox-E2E, externem Restic-Backup/Restore-Test und Codex-Review.
