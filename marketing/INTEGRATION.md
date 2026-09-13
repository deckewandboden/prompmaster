# Marketing-Integration in PromptMaster Commercial

Dieser Ordner stammt aus der vollständigen Marketing-Sicherung vom 06.09.2026 und ist der aktuell vollständig physisch vorhandene Marketing-Source-Tree.

## Laufzeit

- Build über `Dockerfile.caddy`
- `npm ci`
- `npm test`
- `npm run build`
- Ausgabe `dist/` wird in das Caddy-Image kopiert

## Backend-Brücke

`/catalog.json` wird im integrierten Stack nicht aus der statischen Fallback-Datei, sondern aus Django geliefert. Damit bleiben Preis und Pro-Anwendungszahl serverseitig synchron.

`public/integration-patch.js` aktualisiert den historischen sichtbaren „10 zusätzliche Apps“-Stand auf den aktuellen zentralen 34-App-Katalog (28 zusätzliche Anwendungen gegenüber Free), sobald der Live-Katalog verfügbar ist.

## Routing

- `/free/` -> Django/Free Golden Master
- `/pro/` -> geschützter Pro-Zugang
- `/login/` -> `/auth/login/`
- `/checkout/` -> `/portal/licenses/buy/`
- `/portal/` -> `/portal/dashboard/`

## Provenienz

Dieser Stand ist nicht als bytegenaues V15 ausgegeben. V13/V14/V15-Commit-/Archivinformationen stehen in `../docs/SOURCE_OF_TRUTH.md`. Der exakte V13-Exporter liegt unter `../tools/recovery/v13-exact-exporter/`.
