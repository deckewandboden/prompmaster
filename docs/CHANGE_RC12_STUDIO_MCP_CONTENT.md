# PM-CHG-2026-09-12-002 — Prompt Studio, Qualität, MCP, zentrale Inhalte

Status: Code materialisiert, Django/Docker-Runtime-Abnahme über CI/Staging offen.

## Ergänzt

- Prompt-Testfälle
- Lifecycle DRAFT → TEST → REVIEW → APPROVED → PUBLISHED → ARCHIVED
- No-Code Prompt Studio
- getrennte Publish-Berechtigung
- 1–5-Sterne-Ratings; Feedback nur 1–3
- Qualitätsrichtlinie, Snapshots, Drop-Erkennung, Celery-Auswertung
- MCP Streamable-HTTP-kompatibler JSON-RPC-Endpunkt
- MCP Tools read/draft/test; explizit kein publish/delete
- MCP `/health`
- zentrale FAQ-Domain/API/Admin
- Supporthistorie
- Datenschutzexport
- Pro-Upgrade-Anfrage
- gehashter tenant-/usergebundener Lizenz-Zuordnungslink

## Security

- Prompt Studio serverseitig RBAC-geschützt
- Publish benötigt `prompts.publish`
- MCP ausschließlich Service-Account-Scopes
- MCP Draft/Test erzwingt Human-in-the-loop; kein Publish/Delete-Tool
- Zuordnungslinks speichern nur SHA256-Tokenhash und sind einmalig/ablaufend
- Datenschutzexport liefert keine Secrets/Tokenhashes/fremden Benutzerdaten
