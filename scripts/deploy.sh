#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
F=(-f compose.yaml -f compose.production.yaml)
log(){ printf '[PromptMaster deploy] %s\n' "$*"; }

if [[ -z "${GIT_SHA:-}" ]]; then
  if command -v git >/dev/null 2>&1 && git rev-parse HEAD >/dev/null 2>&1; then
    export GIT_SHA="$(git rev-parse HEAD)"
  else
    export GIT_SHA="source-archive"
  fi
fi
if [[ -z "${APP_VERSION:-}" || "${APP_VERSION}" == "development" ]]; then
  if command -v git >/dev/null 2>&1 && git describe --tags --always >/dev/null 2>&1; then
    export APP_VERSION="$(git describe --tags --always)"
  else
    export APP_VERSION="${GIT_SHA:0:12}"
  fi
fi
export DEPLOYED_AT="${DEPLOYED_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

bash scripts/run_repo_preflight.sh production
log "Compose-Konfiguration prüfen"
docker compose "${F[@]}" config >/dev/null
log "Images bauen"
docker compose "${F[@]}" build
log "Datenservices starten"
docker compose "${F[@]}" up -d postgres redis
log "Django Systemcheck"
docker compose "${F[@]}" run --rm web python manage.py check
log "Uncommitted migrations ausschließen"
docker compose "${F[@]}" run --rm web python manage.py makemigrations --check --dry-run
log "Tests ausführen"
docker compose "${F[@]}" run --rm web python manage.py test
log "Pre-Migration-Backup erstellen"
docker compose "${F[@]}" stop backup >/dev/null 2>&1 || true
docker compose "${F[@]}" run --rm -e BACKUP_ONCE=1 backup
log "Migrationen anwenden"
docker compose "${F[@]}" run --rm web python manage.py migrate --noinput
log "Defaults und zentralen Prompt-Katalog aktualisieren"
docker compose "${F[@]}" run --rm web python manage.py seed_defaults
docker compose "${F[@]}" run --rm web python manage.py seed_prompt_catalog
docker compose "${F[@]}" run --rm web python manage.py seed_faqs
docker compose "${F[@]}" run --rm web python manage.py validate_prompt_runtime
log "Static Assets sammeln"
docker compose "${F[@]}" run --rm web python manage.py collectstatic --noinput
log "Stack starten"
docker compose "${F[@]}" up -d
log "Production Security Check"
docker compose "${F[@]}" exec -T web python manage.py check --deploy
log "Healthcheck"
docker compose "${F[@]}" exec -T web python manage.py check
log "Deployment abgeschlossen"
