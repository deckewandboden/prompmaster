# Release Gates

Ein GitHub-Upload bedeutet **nicht** automatisch Produktionsfreigabe.

Diese Gates sind verbindlich für den Completion-Stand. Ein Gate darf nur als grün gelten, wenn es tatsächlich ausgeführt wurde; ein Workflow ohne Runner/Steps ist weder grün noch rot, sondern **nicht ausgeführt**.

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

Zusätzlich dürfen `git diff --check` und die Repository-Manifest-/Preflight-Prüfungen keine Fehler melden.

## Gate 1 — GitHub CI / PostgreSQL

Workflow `.github/workflows/ci.yml` muss mit real zugewiesenem Runner vollständig grün sein:

- Python-Abhängigkeiten / `pip check`
- PostgreSQL 18 / Redis
- Migration Drift (`makemigrations --check --dry-run`)
- Migrationen
- Seed Defaults / PM20 / FAQ
- 194 Prompt-Smoke-Tests
- MCP-/FAQ-Runtime-Sanity
- Django Check/Test Suite
- Completion-Security-/Concurrency-Regressionen
  - RBAC + Staff-Step-up
  - Refund-Retry/Idempotency/Tenant-Sperre
  - Notification-Capability/Empfängerbindung
  - Backup-/Restore-Status-Fail-safe
  - paralleler Prompt-Publish
  - parallele Quality-Policy-Erstellung
- 100k DataGrid Acceptance
- Backend-/Caddy-/Backup-Docker-Build
- Marketing Node Tests/Lint/Build

Die separaten Security-Workflows müssen ebenfalls mit realem Runner grün sein:

- Python Dependency Audit
- vollständiger Marketing Dependency Audit
- Shell-Syntax

## Gate 2 — Ubuntu 24.04 Staging / Full Stack

```bash
cp .env.example .env
# sichere Staging-Werte setzen
./scripts/bootstrap.sh
./scripts/runtime_validate.sh
./scripts/test_backup_restore.sh
```

Erst `RUNTIME VALIDATION OK` plus erfolgreicher Backup-/Restore-Test gilt als lokaler Stack-Nachweis. Produktions-Filesystemrestriktionen (`compose.production.yaml`, read-only App-Container) müssen dabei aktiv geprüft werden.

## Gate 3 — Externe Integrationen

Die ausführbaren Abnahmeschritte stehen in `docs/PRODUCTION_ACCEPTANCE.md`.

- Mollie Sandbox: echter Portal-Kauf / Webhook / Refund / Chargeback / Chargeback-Reversal über `external_mollie_acceptance`
- Microsoft Graph: realer Sendetest und realer Provider-Fehlerpfad über `external_graph_acceptance`
- externer S3/restic Backup-Zieltest plus isolierter PostgreSQL-Restore über `scripts/external_backup_acceptance.sh`

Provider-Gates dürfen nicht ausschließlich gemockt sein. Die Acceptance-Harnesses verweigern Mollie-Live-Keys beziehungsweise externe Aktionen ohne expliziten Bestätigungswert.

## Gate 4 — Browser / Security / Performance

- 360/390, 768, 1440, 1920 px
- Chrome/Edge, Firefox, relevante Safari-Varianten
- Tenant/IDOR/Permission-Negativtests
- 2FA/Auth/Invite/Device/Deep-Link
- zentrale Staff-Step-up-Aktionen
- Pro-Runtime Compose + Rating/Feedback
- Marketing-Smoke
- 100k DataGrid / p95 Ziele

Automatisierte Browser-Smokes:

```bash
python scripts/browser_runtime_smoke.py
python scripts/browser_marketing_smoke.py
```

## Gate 5 — Monitoring-Trust-Boundary

cAdvisor läuft bewusst als hostnaher Monitoring-Agent mit `privileged: true` und read-only Host-/Docker-Mounts. Diese Konfiguration ist **kein normaler Anwendungscontainer** und wird als explizite Host-Trust-Boundary behandelt.

Vor Produktion muss bestätigt sein:

- cAdvisor besitzt **keinen veröffentlichten Host-Port**;
- cAdvisor ist ausschließlich im internen Docker-Netz `monitor` erreichbar;
- Prometheus ist ebenfalls nicht öffentlich veröffentlicht;
- Host-/Docker-Mounts bleiben read-only, soweit cAdvisor dies unterstützt;
- das cAdvisor-Image bleibt versionsgepinnt und wird im Dependency-/Image-Review berücksichtigt;
- der Host selbst gilt als vertrauenswürdige Administrationszone;
- eine Kompromittierung von cAdvisor wird als möglicher Host-Impact behandelt und in Incident-/Backup-Planung berücksichtigt.

Eine spätere Reduktion von `privileged` oder Host-Mounts darf erst nach einem realen Staging-Test erfolgen, der Container-/Host-Metriken und Prometheus-Scrapes nachweist. Keine ungetestete „Härtung“ in Produktion.

## Gate 6 — Human Review / Produktion

- Rechtstexte freigegeben
- Production Domain/DNS
- Live Provider-Secrets
- Monitoring/Alert-Empfänger
- Backup/Notfallzugang dokumentiert
- cAdvisor-Host-Risiko explizit akzeptiert oder technisch ersetzt
- externe Gates nachgewiesen
- Human Review der CI-/Security-Ergebnisse
- keine offenen P0/P1-Befunde aus `COMPLETION_MASTER_AUDIT_2026-09-17.md`

## Pro-Runtime und Marketing

Vor Release zusätzlich:

```bash
python scripts/validate_runtime_catalog.py
```

Der Pro-Browser-Smoke muss 34 eindeutige App-Kacheln rendern und Compose sowie Rating/Feedback über die Server-API ausführen. Der Marketing-Smoke prüft öffentliche Free/Pro-Karten, 2,99-EUR-Anzeige, 34-App-/28-Zusatz-App-Synchronisierung, 20 FAQ und das Partikelkopf-Canvas. Der unveränderte Pro-Golden-Master bleibt Referenz; die abgeleitete Runtime lädt den veröffentlichten PromptDomain-Katalog serverseitig.

## Runner-Regel

Ein GitHub-Actions-Job mit `runner_id: 0`, leeren Steps oder Abbruch vor Checkout ist ein **Infrastrukturblocker**. Er darf weder als Anwendungstestfehler noch als bestandener Test gewertet werden. Produktionsfreigabe bleibt blockiert, bis die betroffenen Gates auf einem realen Runner ausgeführt wurden.
