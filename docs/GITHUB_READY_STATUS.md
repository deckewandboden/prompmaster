# GitHub Ready Status — konsolidierter Release-Stand

Stand: 2026-10-01

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
- **vollständige Django-Testsuite**, davon 6 absichtliche Skips für das separat ausgeführte 100k-Performance-Gate
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

## Bereits produktiv nachgewiesen

- Zielhost und öffentliche Domain/DNS/TLS über den externen Caddy-Pfad
- SMTP1 über IONOS mit realer externer Gmail-Zustellung
- SPF/DKIM/DMARC jeweils PASS und TLS aktiv
- sender-domain Message-ID im real zugestellten Header
- Google Postmaster Tools für `decke-wand-boden.de` verifiziert

## Produktiv noch extern abzunehmen

Die folgenden Gates können nicht durch normale CI ersetzt werden und bleiben offen:

- Mollie Sandbox E2E über den öffentlichen Webhook, inklusive Refund/Chargeback
- Graph-E2E/Application-RBAC nur falls Graph im finalen Routing tatsächlich aktiviert wird
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
