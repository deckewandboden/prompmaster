# AGENTS.md — PromptMaster Commercial Reviewer Contract

1. `SPEC.md` plus versionierte Change-Dokumente unter `docs/` sind bindend.
2. Free-/Pro-Golden-Master niemals stillschweigend verändern. Hash-Abweichung ist Release-Blocker.
3. PM20 34/194 ist aktuelle Pro-Basis; PM11-160 ist Legacy-Provenienz.
4. Lizenzregeln unverändert: neue Lizenz 365 Tage; Verlängerung vor Ablauf `valid_until + 365`; nach Ablauf Neustart ab bestätigter Zahlung.
5. PromptMaster-Entitlement und Microsoft-Tier sind getrennte Dimensionen.
6. Der Server-Composer ist stateless: keine Persistenz von Prompt-Eingaben/Prompttext durch den Compose-Pfad.
7. Prompt Studio Lifecycle: DRAFT → TEST → REVIEW → APPROVED → PUBLISHED → ARCHIVED. Publish nur mit `prompts.publish` und grünen Tests.
8. MCP ist intern: read/draft/test; **kein Publish/Delete**. Human-in-the-loop bleibt Pflicht.
9. Tenant- und Permission-Checks serverseitig; niemals IDs/Clientzustand vertrauen.
10. Service Account Tokens, Device Keys, Invite-/Deep-Link-Tokens nur gehasht speichern.
11. High-Risk-Aktionen auditieren; keine Secrets/Promptinhalte in Logs/Audit.
12. DataGrid-Listen serverseitig paginieren/sortieren/filtern; URL-State erhalten.
13. Vor Änderungen mindestens prüfen:
    - `python scripts/validate_python_syntax.py`
    - `python scripts/validate_prompt_assets.py`
    - `python scripts/validate_prompt_domain.py`
    - `python scripts/validate_static.py`
    - `python scripts/validate_repo.py`
    - Django migration drift/check/tests wenn Runtime verfügbar
14. Production erst nach `docs/RELEASE_GATES.md`.
15. Keine Produktionssecrets in Git. Nur 80/443 dürfen öffentlich sein; PostgreSQL/Redis/Prometheus/Exporter bleiben intern.
16. Marketing V15 nur als „exakt V15“ bezeichnen, wenn Commit/Archivhash belegt und Source tatsächlich vorliegt.
17. Human Review vor Production Merge/Deploy.
