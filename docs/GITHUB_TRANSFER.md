# GitHub Transfer

## Ziel

Privates Monorepo. Empfohlene Branches:

- `main` — freigegebener Stand
- `staging` — Integrations-/Stagingstand
- `feature/*` — Änderungen

## Erstimport

Im Projektordner:

```bash
./scripts/github_prepare.sh
```

Das Script führt den vollständigen statischen Preflight aus, initialisiert bei Bedarf Git, erzeugt den RC13-Commit und legt `main` sowie `staging` an.

Danach auf GitHub ein **privates** leeres Repository erstellen und:

```bash
git remote add origin <PRIVATE_GITHUB_REPOSITORY_URL>
git push -u origin main
git push -u origin staging
```

## Nach dem Push

1. Beide GitHub-Actions-Jobs müssen grün sein (`test`, `browser-smoke`).
2. Erst danach Ubuntu-24.04-Staging klonen.
3. `.env` aus `.env.example` erzeugen; `prepare_env.py`/`bootstrap.sh` generieren sichere Staging-Basiswerte, Provider-Live-Secrets werden niemals erfunden.
4. `./scripts/bootstrap.sh`.
5. `./scripts/runtime_validate.sh`.
6. Externe Gates aus `docs/RELEASE_GATES.md` durchführen.
