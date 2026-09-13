# PromptMaster Commercial Platform — Phase 2 V0.1

This repository is generated from `SPEC.md` and provides the first deployable Django/Docker implementation baseline.

## Architecture

- Caddy reverse proxy / TLS
- Django 5.2 LTS compatible app
- PostgreSQL 18
- Redis
- Celery Worker + Beat
- Mailpit in staging
- Prometheus + Node Exporter + cAdvisor + PostgreSQL Exporter
- Operations API (`ops.read`) for future Techniker-Dashboard connector
- netstyle Admin frontend
- Customer portal frontend

## First staging bootstrap

1. Install Docker Engine + Docker Compose plugin on Ubuntu.
2. Copy this repository to the server.
3. `cp .env.example .env`
4. Fill domain and secrets.
5. Generate an encryption key:
   `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   If cryptography is not installed on the host, generate the key on a workstation or via a temporary Python container.
6. Run: `./scripts/bootstrap.sh`

The bootstrap builds services, migrates DB, seeds roles/products/templates, creates the initial superadmin, collects static files and starts staging.

## Important migration note

The generated Phase-2 baseline deliberately lets the **first staging bootstrap** create initial migrations because this environment cannot install Django packages to generate migration files offline. Immediately after the first successful staging bootstrap, commit the generated `backend/apps/*/migrations/*.py` files. After that, `deploy.sh` enforces `makemigrations --check --dry-run`; production must never generate schema migrations dynamically.

## URLs

- `/portal/dashboard/` customer portal
- `/ns-admin/` netstyle backend
- `/django-admin/` technical fallback admin
- `/api/v1/ops/*` operations API
- `/api/webhooks/mollie/` Mollie webhook
- `/health/live/`, `/health/ready/`, `/metrics/`

## Security defaults

- only 80/443 published by Caddy
- database, Redis and monitoring networks not published
- 2FA model included
- role/permission matrix included
- encrypted integration secret storage supported using `APP_ENCRYPTION_KEY`
- audit event model included
- customer portal / admin routes separated

## Current implementation status

Implemented baseline:
- domain models and services
- license 365-day/idempotent creation logic
- device limit service
- reminder scheduler tasks
- Mollie client/webhook baseline
- admin/customer routing and server-side grids
- Ops API and system metrics baseline
- role/product seeding
- Docker/monitoring/deploy scripts
- core tests

Still requires staging validation before being called production-ready:
- generated initial migrations committed
- complete 2FA UX including QR rendering/recovery management polish
- live Mollie sandbox credentials and checkout views
- Microsoft Graph production mail adapter
- real external S3/restic target
- legal texts
- full E2E suite and 100k seed performance run
- Codex full repository review + human review

Do not deploy to production before the gates in `SPEC.md` pass.
