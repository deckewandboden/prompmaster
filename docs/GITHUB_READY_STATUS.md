# GitHub Ready Status — konsolidierter Release-Stand

Stand: 2026-09-23

## Automatisiert grün nachgewiesen

Der aktuelle konsolidierte Release-Stand wurde auf einem realen GitHub-Actions-Runner vollständig ausgeführt und ist intern grün:

- Shell-Syntax aller Betriebs-/Backupskripte
- vollständiger Python-Dependency-Audit
- vollständiger Marketing-Dependency-Audit
- PostgreSQL + Redis
- Migration Drift + Migrationen
- Defaults / Prompt-Katalog / FAQ Seeds
- Prompt Runtime: **34 Apps / 194 PM20-Tasks / 194 Prompt-Smokes**
- Free: 16 Legacy-Verträge erhalten; V2 unter `/free/`
- Pro: 34/194 serverseitiger Katalog; V2 unter `/pro/app/`
- Legacy-/Rollback-Routen: `/free-old/` und `/pro-old/`
- **292 Django-Tests**, davon 6 absichtliche Skips für das separat ausgeführte 100k-Performance-Gate
- separates **100.000-Zeilen-DataGrid-Acceptance-Gate**
- Compose-Konfiguration
- Backend-/Caddy-/Backup-Docker-Build
- Chromium-/Firefox-/WebKit-Browser-Smoke
- Compose/Rating/Feedback über die Server-API
- Clean Bootstrap
- idempotenter zweiter Bootstrap
- Production-Filesystemrestriktionen
- Runtime Validation
- HTTP-Lasttest
- Backup-Restore-Fehlerfall und Recovery
- External-Caddy-Rehearsal

Die Free-/Pro-Golden-Master bleiben hash-geschützt und unverändert; die V2-Integration ist additiv.

## Produktiv noch extern abzunehmen

Die folgenden Gates können nicht durch normale CI ersetzt werden und bleiben bis zur realen Provider-/Infrastrukturabnahme offen:

- Deployment auf dem tatsächlichen Zielhost inklusive öffentlicher Domain/DNS/TLS
- Microsoft Graph Mail E2E inklusive Exchange Application-RBAC-Scope-Nachweis
- Mollie Sandbox E2E über den öffentlichen Webhook, inklusive Refund/Chargeback
- externer S3/restic Backup-/Restore-Drill
- reale Monitoring-/Alert-Empfänger und dokumentierter Notfallzugang
- cAdvisor-Host-Trust-Boundary bewusst akzeptieren oder nach realem Staging-Test technisch ersetzen
- Rechtstexte / Steuerprüfung
- menschliche Produktionsfreigabe
- bewusste Freigabe des integrierten 06.09.-Marketing-Sources; die historische V15-Provenienz bleibt separat dokumentiert

Verbindliche Schritte und Evidenz: `docs/RELEASE_GATES.md` und `docs/PRODUCTION_ACCEPTANCE.md`.

## Deployment

Staging:

```bash
cp .env.example .env
./scripts/bootstrap.sh
./scripts/runtime_validate.sh
```

Produktion:

```bash
./scripts/deploy.sh
```

In Produktion bleibt `INITIAL_ADMIN_PASSWORD` in `.env` leer bzw. `DISABLED`. Der erste Superadmin wird einmalig mit temporären Prozessvariablen gemäß `README.md` angelegt.
