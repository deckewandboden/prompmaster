#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fail(){ echo "[FEHLER] $*" >&2; exit 1; }; log(){ echo "[PromptMaster] $*"; }
command -v docker >/dev/null || fail "Docker fehlt"
docker compose version >/dev/null 2>&1 || fail "Docker Compose Plugin fehlt"
python3 scripts/prepare_env.py
set -a; source .env; set +a
[[ ${DJANGO_SECRET_KEY:-} != CHANGE_ME && ${#DJANGO_SECRET_KEY} -ge 40 ]] || fail "DJANGO_SECRET_KEY sicher setzen (>=40 Zeichen)"
[[ ${POSTGRES_PASSWORD:-} != CHANGE_ME && ${#POSTGRES_PASSWORD} -ge 20 ]] || fail "POSTGRES_PASSWORD sicher setzen"
[[ ${APP_ENCRYPTION_KEY:-} != GENERATE_WITH_FERNET && -n ${APP_ENCRYPTION_KEY:-} ]] || fail "APP_ENCRYPTION_KEY setzen"
[[ ${INITIAL_ADMIN_PASSWORD:-} != CHANGE_ME && ${#INITIAL_ADMIN_PASSWORD} -ge 12 ]] || fail "INITIAL_ADMIN_PASSWORD setzen"
python3 scripts/github_preflight.py
python3 scripts/validate_env.py --environment staging
F=(-f compose.yaml -f compose.staging.yaml)
log "Compose-Konfiguration"; docker compose "${F[@]}" config >/dev/null
log "Build"; docker compose "${F[@]}" build
log "Datenservices"; docker compose "${F[@]}" up -d postgres redis mailpit
log "Django Checks vor Migration"; docker compose "${F[@]}" run --rm web python manage.py check
log "Migrationen"; docker compose "${F[@]}" run --rm web python manage.py migrate --noinput
log "Defaults"; docker compose "${F[@]}" run --rm web python manage.py seed_defaults; docker compose "${F[@]}" run --rm web python manage.py seed_prompt_catalog; docker compose "${F[@]}" run --rm web python manage.py seed_faqs; docker compose "${F[@]}" run --rm web python manage.py validate_prompt_runtime; docker compose "${F[@]}" run --rm web python manage.py bootstrap_admin
log "Static"; docker compose "${F[@]}" run --rm web python manage.py collectstatic --noinput
log "Stack"; docker compose "${F[@]}" up -d
log "Tests"; docker compose "${F[@]}" exec -T web python manage.py test
log "Check deploy"; docker compose "${F[@]}" exec -T web python manage.py check --deploy
log "Fertig: Marketing https://${CADDY_DOMAIN}/ · Portal https://${CADDY_DOMAIN}/portal/dashboard/ · Admin https://${CADDY_DOMAIN}/ns-admin/"
