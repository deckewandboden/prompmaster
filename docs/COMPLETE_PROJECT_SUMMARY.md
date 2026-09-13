# PromptMaster Commercial — Gesamtkonsolidierung RC14

Stand: 2026-09-13

## Vollständigkeitsnachweis

Der aktuelle Repository-Inhalt wird maschinenlesbar durch `FILE_MANIFEST.tsv` und `MANIFEST.json` inventarisiert. Nach Bereinigung temporärer Python-/Node-Artefakte umfasst der konsolidierte Stand **524 inventarisierte Dateien mit 43.332.956 Byte** (die drei Manifest-/Inventardateien selbst sind bewusst nicht in ihrer eigenen Prüfsumme enthalten). Die beiden neu gelieferten Original-ZIP-Pakete liegen zusätzlich bytegenau unter `archive/source-packages/`, sodass sowohl die extrahierten Arbeitsstände als auch die unveränderten Eingangsarchive erhalten bleiben.

## Ziel dieses Repositorys

Dieses Repository führt die bis jetzt physisch wiedergefundenen und rekonstruierten PromptMaster-Quellen zu einem einzigen Git-/Docker-fähigen Monorepo zusammen. Aktive Produktquellen und historische Wiederherstellungsartefakte sind bewusst getrennt, damit alte Prototypen oder Dokumentationshüllen nicht versehentlich als produktiver Code ausgeführt werden.

## Aktive Laufzeitbereiche

### Marketing / Vertrieb

- `marketing/` — wiedergefundener vollständiger Marketing-Source-Snapshot aus der Sicherung vom 06.09.2026
- Three.js-Partikelkopf mit lokalem `head.glb`
- Nachtlandschaft / Brand-Assets
- Free-/Pro-Karten, Funktionen, Preise, Vergleich, FAQ, Unternehmens-/Rechts-Routen
- Build: Vite / Vanilla JS / Three.js
- Deployment: statisch aus dem Caddy-Image
- Live-Produktdaten: `/catalog.json` aus Django, damit Preis und aktueller 34-App-Katalog nicht mehr ausschließlich aus einem alten Browser-Snapshot stammen
- Kompatibilitätsrouten: `/login/` -> `/auth/login/`, `/checkout/` -> `/portal/licenses/buy/`, `/app/pro/` -> `/pro/`

Der aktuell integrierte Marketing-Source ist der **neueste physisch vollständig vorhandene Marketing-Quellbaum**. Er wird nicht fälschlich als bytegenaues V15 bezeichnet. Die belegte V13/V14/V15-Provenienz bleibt unter `docs/SOURCE_OF_TRUTH.md` dokumentiert.

### PromptMaster Free

- exakter Golden Master unter `product/golden_masters/promptmaster_free.html`
- SHA256: `aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8`
- öffentlich ohne Login über `/free/`
- 16 Free-Legacy-Verträge sind serverseitig als Referenz gesichert

### PromptMaster Pro

- exakter Golden Master unter `product/golden_masters/promptmaster_pro.html`
- SHA256: `aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf`
- Login + aktive Lizenz + gültiges Gerät serverseitig erforderlich
- abgeleitete Runtime nutzt die zentrale PromptDomain
- 34 Anwendungen / 194 PM20-Aufgaben
- serverseitiger Composer
- 1–5-Sterne-Rating und optionales Feedback bei 1–3 Sternen

### Commercial Backend

- Django / PostgreSQL / Redis / Celery Worker + Beat
- Firmen-/Privatkunden
- Benutzer, Einladungen, 2FA, Recovery Codes
- generisches RBAC
- Produkt-/Preisversionierung
- individuelle 365-Tage-Lizenzen
- Zuweisung/Freigabe/Verlängerung
- 2-Geräte-Regel
- Mitarbeiter-Pro-Anfragen und Lizenz-Zuordnungslinks
- Mollie Checkout/Webhook/Refund/Chargeback
- Reminder T-60 / T-30 / T-7
- Supporthistorie
- Legal/Audit/Datenschutzexport
- Operations/Monitoring/Backup/Restore-Test
- Operations API

### Zentrale Prompt-Plattform

- `PromptApplication`
- `PromptDefinition`
- `PromptPolicySet`
- `PromptVersion`
- `PromptField`
- `PromptOption`
- `MicrosoftTier`
- `MicrosoftCapability`
- `PromptLegacyContract`
- Prompt Studio
- Lifecycle DRAFT -> TEST -> REVIEW -> APPROVED -> PUBLISHED -> ARCHIVED
- Testfälle
- Qualitätsanalyse
- internes MCP Read/Draft/Test ohne Publish/Delete
- zentrale FAQ-Verwaltung/API

## Historische / forensische Quellen

`archive/chat-transfer-2026-09-12/` enthält den **kompletten extrahierten Inhalt** von `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12(2).zip`, inklusive:

- Master-Spezifikation
- RC8-Dokumentationshülle
- tatsächlich damaliger Phase-2-Baseline
- UI-Prototypen
- 10 Design-/UI-Referenzbilder
- Original-Manifest und SHA256-Liste

Diese Dateien sind Provenienz/Abnahmehilfe und **nicht** die aktive Runtime.

`docs/recovery/marketing-2026-09-06/` enthält die drei zusätzlichen Dokumente aus der Marketing-Sicherung, während deren `frontend/` als aktives `marketing/` übernommen wurde.

`tools/recovery/v13-exact-exporter/` enthält den wiedergefundenen Exporter für den dokumentierten V13-Git-Commit. Falls der ursprüngliche Windows/Codex-Git-Objektbestand noch vorhanden ist, kann damit V13 byte-/commitgenau erneut exportiert werden.

## Zusammengeführte Quellpakete

| Quelle | Größe | SHA256 | Verwendung |
|---|---:|---|---|
| `PromptMaster_GITHUB_RC13_READY_2026-09-13.zip` | 635.773 B | `e3d514cc405136078f67271b6aabca0f18bffc525d74d84558f374cbf935ee70` | aktive Backend-/Produktbasis |
| `PromptMaster-Commercial-Sicherung-2026-09-06(1).zip` | 5.168.035 B | `196220ab78971cf86b9e391c3abcd3ebcfa761bd24b1408cfb0d3c7e7d715b3d` | aktives Marketing + Recovery-Dokumente |
| `PromptMaster_CHAT_TRANSFER_LATEST_2026-09-12(2).zip` | 14.411.033 B | `fcf33456e75fb9064ff9fdd01b7ae8307675717f5d57391c7b2981d8c8ee710d` | vollständig als historische Referenz archiviert |
| `PromptMaster_v13_EXAKT_Exporter_v2(1).zip` | 3.760 B | `9ddee1b7652156f64eb5b3596a43379f61617b34bc59077451de4e8d2e75e3cc` | Recovery-Werkzeug |

## Deployment-Topologie

Caddy ist jetzt ein eigenes Build-Image (`Dockerfile.caddy`):

1. Node 22 baut `marketing/` und führt Marketing-Tests aus.
2. Das fertige `marketing/dist` wird in das Caddy-Image nach `/srv/marketing` kopiert.
3. Caddy liefert die öffentliche Marketing-/Vertriebsseite aus.
4. Geschützte Routen (`/auth`, `/free`, `/pro`, `/portal`, `/ns-admin`, `/api`, `/health`, `/legal`) werden an Django weitergeleitet.
5. `/catalog.json` kommt aus Django und synchronisiert Browserpreis sowie aktuellen Anwendungskatalog.

Damit liegen Marketing, Free, Pro und Commercial Backend im selben Repository und werden von einem gemeinsamen Compose-Stack betrieben.

## Aktuelle statische Nachweise

Lokal erfolgreich:

- Python-Syntax
- Golden-Master-/Runtime-Hashes
- 34 Apps / 194 PM20-Tasks
- Composer 194/194 ohne ungelöste Platzhalter
- zentrale Runtime-Katalogprüfung
- Marketing-Struktur-/Integrationsprüfung
- Repository-/Secret-Guard
- Shell-Syntax
- Marketing Node-Test-Suite: 11/11
- Pro Headless-Chromium-Smoke
- Marketing Headless-Chromium-DOM-Smoke

Nicht in dieser Umgebung beweisbar:

- Docker Compose Runtime
- echte PostgreSQL/Redis/Celery-Runtime
- GitHub Actions Lauf
- Mollie Sandbox E2E
- Microsoft Graph Mail E2E
- externer S3/restic Drill
- vollständige Browser-/Security-/100k-Performance-Abnahme

Diese Punkte bleiben Release-Gates und werden nicht als grün behauptet, bevor sie tatsächlich gelaufen sind.
