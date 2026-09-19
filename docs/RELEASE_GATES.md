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

Die ausführbaren Abnahmeschritte stehen in `docs/PRODUCTION_ACCEPTANCE.md`. Diese Gates werden **nicht** in der normalen CI mit realen Secrets ausgeführt; sie müssen gegen denselben Release-Commit in der realen Staging-/Provider-Umgebung nachgewiesen werden.

- Mollie Sandbox über `external_mollie_acceptance`:
  - echter Portal-Kauf ausschließlich mit `test_`-API-Key,
  - Mollie muss den Providerdatensatz selbst mit `mode=test` zurückliefern,
  - `metadata.order_id` und öffentliche `webhookUrl` müssen zum lokalen PromptMaster-Kauf passen,
  - echter Webhook / Paid-Aktivierung,
  - Refund über den produktiven Refund-Service,
  - Chargeback über die separate Mollie-Chargeback-Ressource (`reversedAt=null`) und – sofern die verwendete Mollie-Testumgebung ihn anbietet – Chargeback-Reversal über denselben Chargeback mit gesetztem `reversedAt`.
- Microsoft Graph über `external_graph_acceptance`:
  - Exchange-Application-RBAC für `Application Mail.Send`,
  - positiver `InScope`-Nachweis für `GRAPH_SENDER` und negativer Kontrollpostfach-Nachweis,
  - kein paralleler unbeschränkter Entra-`Mail.Send`-Grant,
  - echter Versand über den produktiven `EmailMessage`-/Taskpfad,
  - echter Provider-Fehler mit persistiertem Failed-/Retry-Zustand sowie tatsächlicher Empfang der Erfolgsnachricht.
- Externes S3/restic über `PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE ./scripts/external_backup_acceptance.sh`:
  - ausschließlich externes TLS-geschütztes S3-Ziel,
  - regulärer Backupdienst während des Drills angehalten, damit kein paralleler Snapshot die Evidence verfälscht,
  - neuer externer Snapshot,
  - echter isolierter PostgreSQL-Restore mit Integritätsprüfung.

Provider-Gates dürfen nicht ausschließlich gemockt sein. Die Acceptance-Harnesses verweigern Mollie-Live-Keys, unsichere/Platzhalter-S3-Ziele beziehungsweise externe Aktionen ohne expliziten Bestätigungswert.

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
for engine in chromium firefox webkit; do
  PM_BROWSER_ENGINE="$engine" python scripts/browser_marketing_smoke.py
done
```

Der Marketing-Smoke muss den Kopf sowohl mit WebGL als auch mit erzwungenem
WebGL-Ausfall validieren. Ohne WebGL muss automatisch Canvas2D übernehmen;
Kamera-/Webcam-Zugriff ist im Marketing-Runtime nicht zulässig. Der
Preisrechner wird zusätzlich gegen eine absichtlich falsche HTML-Antwort auf
`/catalog.json` geprüft und muss mit dem eingebetteten Anzeigekatalog
weiterarbeiten.

## Gate 5 — Monitoring-Trust-Boundary

cAdvisor läuft bewusst als hostnaher Monitoring-Agent mit `privileged: true` und read-only Host-/Docker-Mounts. Diese Konfiguration ist **kein normaler Anwendungscontainer** und wird als explizite Host-Trust-Boundary behandelt.

Vor Produktion muss bestätigt sein:

- cAdvisor besitzt **keinen veröffentlichten Host-Port**;
- cAdvisor ist ausschließlich im internen Docker-Netz `monitor` erreichbar;
- Prometheus ist ebenfalls nicht öffentlich veröffentlicht;
- Host-/Docker-Mounts bleiben read-only, soweit cAdvisor dies unterstützt;
- das cAdvisor-Image bleibt versionsgepinnt und wird im Dependency-/Image-Review berücksichtigt;
- `scripts/validate_static.py` erzwingt: keine Host-Ports für Prometheus/cAdvisor, ausschließlich internes `monitor`-Netz und unveränderte read-only Host-Mounts;
- `scripts/runtime_validate.sh` verlangt im realen Stack die Prometheus-Targets `node`, `postgres`, `cadvisor` und `django` mit Zustand `UP` **und** prüft zur Laufzeit: keine veröffentlichten Host-Ports für Prometheus/cAdvisor, jeweils ausschließlich das interne `monitor`-Netz, `cAdvisor privileged=true` und keine schreibbaren cAdvisor-Host-Mounts;
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

Der Pro-Browser-Smoke muss 34 eindeutige App-Kacheln rendern und Compose sowie Rating/Feedback über die Server-API ausführen. Der Marketing-Smoke prüft in Chromium, Firefox und WebKit öffentliche Free/Pro-Karten, den funktionierenden Preisrechner, 2,99-EUR-Anzeige, 34-App-/28-Zusatz-App-Synchronisierung, 20 FAQ und den WebGL-/Canvas2D-Partikelkopf. Der unveränderte Pro-Golden-Master bleibt Referenz; die abgeleitete Runtime lädt den veröffentlichten PromptDomain-Katalog serverseitig.

## Runner-Regel

Ein GitHub-Actions-Job mit `runner_id: 0`, leeren Steps oder Abbruch vor Checkout ist ein **Infrastrukturblocker**. Er darf weder als Anwendungstestfehler noch als bestandener Test gewertet werden. Produktionsfreigabe bleibt blockiert, bis die betroffenen Gates auf einem realen Runner ausgeführt wurden.
