# RC13 — zentraler Runtime-Katalog und GitHub-Preflight

Stand: 2026-09-13

## Behobener Architekturbruch

Der Pro-Golden-Master enthält 34 Apps / 194 PM20-Tasks, rendert in seiner historischen Browserlogik jedoch nur 16 App-Kacheln. Gleichzeitig existiert seit RC11 eine zentrale versionierte PromptDomain.

RC13 macht die PromptDomain zur Laufzeit zur einzigen Katalogquelle für PromptMaster Pro:

- `GET /api/v1/prompts/?product=PRO` liefert den vollständigen veröffentlichten Runtime-Vertrag einschließlich Pflicht-/Optionalfeldern, Audience, Focus, Output und Source.
- Die abgeleitete Pro-Runtime lädt diesen Katalog beim Start und arbeitet fail-closed, solange er nicht verfügbar ist.
- Das eingebettete APP-Objekt des unveränderten Golden Masters wird zur Laufzeit vollständig durch die Serverdaten ersetzt.
- App-/Task-Microsoft-Tier-Regeln werden aus `MicrosoftCapability` übernommen.
- Produktentitlements werden serverseitig berücksichtigt.
- Dynamische Gruppen ersetzen die alte hartcodierte 16-App-Darstellung.
- Änderungen, die im Prompt Studio veröffentlicht werden, erreichen dadurch die Produkt-Runtime ohne Umbau des Golden Masters.

## Gefundener und behobener UI-Fehler

Der Rating-Bridge-Code suchte fälschlich `.prompt-actions`; die aktuelle Pro-Oberfläche verwendet `.actions`. Dadurch erschien die Rating-Funktion trotz erfolgreicher Komposition nicht. Der Selektor wurde korrigiert und im Browser-Smoke verifiziert.

## Zusätzliche Gates

- `scripts/validate_runtime_catalog.py`
- `scripts/github_preflight.py`
- `scripts/browser_runtime_smoke.py` (optional/Browserhost)
- `.dockerignore`
- `scripts/github_prepare.sh`
- CI verwendet den zentralen Preflight und validiert Compose-Konfiguration.

## Validierter Browserpfad

Headless Chromium wurde lokal ohne Netzwerkzugriff gegen eine deterministische API-Simulation ausgeführt:

- 34 eindeutige Apps sichtbar
- Power Automate und GitHub Copilot sichtbar
- Copilot Chat zeigt 5 Tasks
- PM20-001 sendet Pflichtfeld an Server-Compose
- Serverergebnis wird angezeigt
- 2-Sterne-Bewertung aktiviert optionales Feedback
- Feedback wird über Rating-Endpunkt gesendet
