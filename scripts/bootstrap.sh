#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fail(){ echo "[FEHLER] $*" >&2; exit 1; }
log(){ echo "[PromptMaster] $*"; }

command -v docker >/dev/null 2>&1 || fail "Docker fehlt"
docker compose version >/dev/null 2>&1 || fail "Docker Compose Plugin fehlt"

log "Sauberer Repository-/Marketing-Preflight ohne Host-Python/Node-Abhängigkeit"
bash scripts/run_repo_preflight.sh staging --prepare-env

set -a
source .env
set +a

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

[[ ${DJANGO_SECRET_KEY:-} != CHANGE_ME && ${#DJANGO_SECRET_KEY} -ge 40 ]] || fail "DJANGO_SECRET_KEY sicher setzen (>=40 Zeichen)"
[[ ${POSTGRES_PASSWORD:-} != CHANGE_ME && ${#POSTGRES_PASSWORD} -ge 20 ]] || fail "POSTGRES_PASSWORD sicher setzen"
[[ ${APP_ENCRYPTION_KEY:-} != GENERATE_WITH_FERNET && -n ${APP_ENCRYPTION_KEY:-} ]] || fail "APP_ENCRYPTION_KEY setzen"
[[ ${INITIAL_ADMIN_PASSWORD:-} != CHANGE_ME && ${#INITIAL_ADMIN_PASSWORD} -ge 12 ]] || fail "INITIAL_ADMIN_PASSWORD setzen"

F=(-f compose.yaml -f compose.staging.yaml)
log "Compose-Konfiguration"; docker compose "${F[@]}" config >/dev/null
log "Build"; docker compose "${F[@]}" build
log "Datenservices"; docker compose "${F[@]}" up -d postgres redis mailpit
log "Django Checks vor Migration"; docker compose "${F[@]}" run --rm web python manage.py check
log "Migrationen prüfen"; docker compose "${F[@]}" run --rm web python manage.py makemigrations --check --dry-run
log "Migrationen"; docker compose "${F[@]}" run --rm web python manage.py migrate --noinput
log "Defaults"; docker compose "${F[@]}" run --rm web python manage.py seed_defaults; docker compose "${F[@]}" run --rm web python manage.py seed_prompt_catalog; docker compose "${F[@]}" run --rm web python manage.py seed_faqs; docker compose "${F[@]}" run --rm web python manage.py validate_prompt_runtime; docker compose "${F[@]}" run --rm web python manage.py bootstrap_admin
log "Static"; docker compose "${F[@]}" run --rm web python manage.py collectstatic --noinput
log "Stack"; docker compose "${F[@]}" up -d
log "Tests"; docker compose "${F[@]}" exec -T web python manage.py test
log "Check deploy"; docker compose "${F[@]}" exec -T web python manage.py check --deploy
log "Django Ready"; docker compose "${F[@]}" exec -T web curl -fsS http://127.0.0.1:8000/health/ready/ >/dev/null
log "Marketing-Artefakte im Caddy-Container"; docker compose "${F[@]}" exec -T caddy sh -c 'test -s /srv/marketing/index.html && test -s /srv/marketing/models/head.glb && test -s /srv/marketing/models/night-landscape.png && test -s /srv/marketing/integration-patch.js'
log "Containerstatus"; docker compose "${F[@]}" ps
log "Fertig: Marketing https://${CADDY_DOMAIN}/ · Portal https://${CADDY_DOMAIN}/portal/dashboard/ · Admin https://${CADDY_DOMAIN}/ns-admin/"
