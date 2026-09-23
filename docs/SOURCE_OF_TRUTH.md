# PromptMaster Commercial — Source of Truth

Stand: 2026-09-23

## Priorität

1. `SPEC.md` (Commercial Master-Spezifikation V1.0)
2. dokumentierte spätere Change-Entscheidungen in `docs/`
3. aktueller materialisierter Quellcode dieses Repositories
4. unveränderte Free-/Pro-Golden-Master als Produkt-/Regression-Referenz
5. historische Chat-/RC-/Marketing-Artefakte nur als Provenienz

## Aktiver Release-Stand

Maßgeblich für Betrieb und weitere Entwicklung ist der aktuelle `main`-Stand des Repositories. Historische RC-/Marketing-Bezeichnungen bleiben ausschließlich Provenienz und dürfen nicht als aktiver Release-Zweig interpretiert werden.

Aktive Produktoberflächen:

- Free V2: `/free/`
- Pro V2: `/pro/app/`
- Free Legacy/Rollback: `/free-old/`
- Pro Legacy/Rollback: `/pro-old/`
- Commercial Portal/Admin/API bleiben serverseitig in Django integriert

Der aktive Release-Stand hat am 23.09.2026 die internen automatisierten Release-Gates vollständig bestanden: 292 Django-Tests, separates 100k-DataGrid-Gate, 34 Apps / 194 Tasks / 194 Prompt-Smokes, Chromium/Firefox/WebKit Browser-Smoke, Full-Stack-Bootstrap/Idempotenz, HTTP-Lasttest, Backup-Restore-Recovery, External-Caddy-Rehearsal sowie Dependency-/Shell-Security.

Provider-/Infrastruktur- und Human-Gates aus `docs/PRODUCTION_ACCEPTANCE.md` und `docs/RELEASE_GATES.md` bleiben davon getrennt und müssen vor einem echten Produktions-Go-Live nachgewiesen werden.

## Produkt-Golden-Master

- Free SHA256: `aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8`
- Pro SHA256: `aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf`
- aktueller Pro-Katalog: 34 Apps / 194 PM20-Tasks
- PM11-160: historische Legacy-Produktgeneration, kein Downgrade-Ziel

## Zentrale Prompt-Plattform

Der aktuelle Code materialisiert die später rekonstruierten Prompt-Anforderungen:

- `PromptDefinition` / `PromptVersion`
- Microsoft Tier / Capability getrennt von PromptMaster-Entitlements
- serverseitiger stateless Composer
- No-Code Prompt Studio
- Testfälle und Lifecycle
- Ratings / Qualitätsanalyse
- interner MCP Read/Draft/Test ohne Publish/Delete
- zentrale FAQ-Domain/API

## Marketing-Provenienz

Belegt sind V13/V14/V15 und die V15-Provenienz. Das exakte V15-Archiv ist in diesem Repository nicht enthalten und darf nicht durch eine frei rekonstruierte Version als „exakt V15“ ersetzt werden:

- V13: `d36033bdfc87ee5dbacd8459c8cca919ec2f2b45`
- V14: `7f6e3bb95290096f421163e691931e398a4a326d`
- V15: `2f78921327346233c3f31053eeb670fc372ca1fb`
- V15 Archiv SHA256: `ae5035e4ec45ce107fbac502453ce8894960c61386c2a83dc5a60be77a1fa0e7`
- V15 sediment file id: `file_000000005dc481f4a88de894f21b587e`

Der vollständig wiedergefundene Marketing-Source-Snapshot vom 06.09.2026 ist in RC14 unter `marketing/` integriert und lauffähig an die aktuelle Plattform angebunden. Er ist **nicht** als bytegenaues V15 etikettiert. Historische V15-Provenienz und aktiver integrierter Source werden damit bewusst getrennt.

Marketing, Free, Pro und Backend können im gemeinsamen Compose-Stack betrieben und geprüft werden.
