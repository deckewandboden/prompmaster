# Requirements Status V3 — konsolidierter Release-Stand

Stand 01.10.2026: SMTP1/SMTP2/Graph-Routing und sender-domain Message-ID sind code-seitig integriert; der finale Provider wird nach realem Routing abgenommen.

## Code-materialisiert

- Commercial Django Backend aus RC10-Härtung
- Auth / 2FA / Tenant / generisches RBAC
- Kundenportal / netstyle Admin
- Produkte / Preisversionen / individuelle 365-Tage-Lizenzen
- Seat-Zuweisung / Freigabe / Gerätebindung
- Mitarbeitenden-Pro-Anfrage + Company-Admin-Entscheidung
- gehashter, tenant- und benutzergebundener Einmal-Zuordnungslink
- Mollie-Modelle / idempotenter Webhook / Refund / Chargeback
- Supporthistorie im Kundenportal
- Datenschutz-JSON-Export
- Operations / Worker-Ping / Beat-Heartbeat / Backup-/Restore-Modelle
- zentrale Prompt-Domain 34/194
- Microsoft Tier / Capability
- serverseitiger stateless Composer
- Prompt Studio / Tests / Lifecycle
- Ratings / Qualitätsanalyse
- MCP read/draft/test + health
- zentrale FAQ-Verwaltung/API
- CI-/Repo-/Runtime-Validatoren
- dedizierte netstyle-Präsentationsdemo `DEMO-NETSTYLE` mit 12 aktiven Benutzern, 10 PRO-Lizenzen (9 zugewiesen/1 frei), 3 Free-Benutzern und 1 offener PRO-Anfrage; keine Provideraktionen
- vereinheitlichter `support_reply`-Template-Vertrag und produktionsfähige SMTP1/SMTP2/Graph-Routingvalidierung

## Golden-Master-Status

- Free/Pro bytegenau hash-geschützt
- 16 Free-Legacy-Verträge bewahrt
- Free→PM20-Mapping bleibt absichtlich fail-closed, bis fachlich freigegeben

## Automatisierter Runtime-Status

Intern automatisiert grün nachgewiesen:

- vollständiger Docker-/Compose-Full-Stack auf GitHub Runner
- PostgreSQL/Redis/Celery Runtime
- 379 Django-Tests
- separate 100k DataGrid Acceptance
- Browser-Smoke in Chromium, Firefox und WebKit
- Security-/Tenant-Regressionen einschließlich explizitem Kunden-/User-Scope für E-Mail-Historien und tenant-spezifischem Audit-Scope
- 34 Apps / 194 Tasks / 194 Prompt-Smokes
- Clean + idempotenter Bootstrap
- Runtime Validation, HTTP Load, Backup-Restore-Recovery und External-Caddy-Rehearsal

## Bereits produktiv nachgewiesen

- Zielhost und öffentliche Domain/DNS/TLS über den externen Caddy-Pfad
- realer SMTP1-Versand über IONOS mit externer Gmail-Zustellung
- SPF, DKIM und DMARC jeweils PASS; TLS aktiv
- sender-domain Message-ID statt Container-/Docker-Hostname
- Google Postmaster Tools für `decke-wand-boden.de` verifiziert

## Extern/produktiv noch zu bestätigen

- Mollie Sandbox E2E über öffentlichen Webhook
- Graph-E2E/Application-RBAC nur wenn Graph im finalen Routing tatsächlich aktiviert wird
- externer S3/restic Backup-/Restore-Drill
- reale Monitoring-/Alert-Empfänger und Notfallzugang
- Rechtstexte / Steuerprüfung / menschliche Go-Live-Freigabe
- exakte Marketing-V15-Provenienz bleibt historisch; für Go-Live ist die bewusste Freigabe des integrierten Marketing-Sources erforderlich
