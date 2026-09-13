#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
log(){ printf '\n\033[1;36m[PromptMaster]\033[0m %s\n' "$*"; }
fail(){ printf '\n\033[1;31m[FEHLER]\033[0m %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null || fail "Docker fehlt. Bitte Docker Engine installieren."
docker compose version >/dev/null 2>&1 || fail "Docker Compose Plugin fehlt."
[[ -f .env ]] || { cp .env.example .env; fail ".env wurde aus .env.example erzeugt. Bitte sichere Secrets/Domain eintragen und erneut starten."; }
set -a; source .env; set +a
[[ "${DJANGO_SECRET_KEY:-}" != "CHANGE_ME" ]] || fail "DJANGO_SECRET_KEY ändern."
[[ "${POSTGRES_PASSWORD:-}" != "CHANGE_ME" ]] || fail "POSTGRES_PASSWORD ändern."
if [[ -z "${APP_ENCRYPTION_KEY:-}" || "${APP_ENCRYPTION_KEY}" == "GENERATE_WITH_FERNET" ]]; then
  fail "APP_ENCRYPTION_KEY fehlt. Erzeugen: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
fi
log "Build und Start der Datenservices"
docker compose -f compose.yaml -f compose.staging.yaml build
docker compose -f compose.yaml -f compose.staging.yaml up -d postgres redis mailpit
log "Django Migrationen erzeugen/prüfen"
# Initialer Generator für den ersten Staging-Build. Nach dem ersten erfolgreichen Bootstrap müssen Migrationen committed werden.
docker compose -f compose.yaml -f compose.staging.yaml run --rm web python manage.py makemigrations --noinput
docker compose -f compose.yaml -f compose.staging.yaml run --rm web python manage.py migrate --noinput
log "Defaults und initialer Superadmin"
docker compose -f compose.yaml -f compose.staging.yaml run --rm web python manage.py seed_defaults
docker compose -f compose.yaml -f compose.staging.yaml run --rm web python manage.py bootstrap_admin
log "Static Files"
docker compose -f compose.yaml -f compose.staging.yaml run --rm web python manage.py collectstatic --noinput
log "Gesamten Staging-Stack starten"
docker compose -f compose.yaml -f compose.staging.yaml up -d
log "Healthcheck"
for i in {1..30}; do
  if docker compose -f compose.yaml -f compose.staging.yaml exec -T web curl -fsS http://localhost:8000/health/ready/ >/dev/null 2>&1; then break; fi
  sleep 2
  [[ $i -eq 30 ]] && fail "Web-Healthcheck fehlgeschlagen. docker compose logs web prüfen."
done
log "Django System Check"
docker compose -f compose.yaml -f compose.staging.yaml exec -T web python manage.py check
log "FERTIG"
echo "Portal: https://${CADDY_DOMAIN}/portal/dashboard/"
echo "netstyle Backend: https://${CADDY_DOMAIN}/ns-admin/"
echo "Mailpit lokal: http://127.0.0.1:8025"
echo "WICHTIG: Nach erstem erfolgreichen Bootstrap die erzeugten backend/apps/*/migrations/*.py in Git committen."
