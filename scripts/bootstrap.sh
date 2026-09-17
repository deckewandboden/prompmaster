#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
fail(){ echo "[FEHLER] $*" >&2; exit 1; }
log(){ echo "[PromptMaster] $*"; }

os="$(uname -s 2>/dev/null || true)"
arch="$(uname -m 2>/dev/null || true)"
[[ "$os" == "Linux" ]] || fail "Nicht unterstütztes Host-System: ${os:-unbekannt}. V1 erwartet Linux/Ubuntu 24.04 LTS."
case "$arch" in
  x86_64|amd64|aarch64|arm64) ;;
  *) fail "Nicht unterstützte Architektur: ${arch:-unbekannt}" ;;
esac
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  log "Host: ${PRETTY_NAME:-$ID} · Architektur: $arch"
else
  log "Host: Linux · Architektur: $arch"
fi

command -v docker >/dev/null 2>&1 || fail "Docker fehlt"
docker compose version >/dev/null 2>&1 || fail "Docker Compose Plugin fehlt"

wait_healthy(){
  local service="$1" timeout="${2:-240}" elapsed=0 cid status
  while (( elapsed < timeout )); do
    cid="$(docker compose "${F[@]}" ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      case "$status" in
        healthy|running) return 0 ;;
        unhealthy|exited|dead) fail "Service $service meldet Status $status" ;;
      esac
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  fail "Service $service wurde innerhalb von ${timeout}s nicht healthy"
}

log "Sauberer Repository-/Marketing-Preflight ohne Host-Python/Node-Abhängigkeit"
bash scripts/run_repo_preflight.sh staging --prepare-env

# .env ist Docker-Env-Syntax und darf nicht als Shell-Skript ausgeführt werden.
# Der Validator hat alle sicherheitsrelevanten Werte bereits geprüft. Für die
# Abschlussmeldung lesen wir ausschließlich die Domain als Datenwert ein.
CADDY_DOMAIN="$(awk -F= '$1 == "CADDY_DOMAIN" {sub(/^[^=]*=/, ""); value=$0} END {print value}' .env | tr -d '\r')"
CADDY_DOMAIN="${CADDY_DOMAIN#\"}"
CADDY_DOMAIN="${CADDY_DOMAIN%\"}"
[[ -n "$CADDY_DOMAIN" ]] || fail "CADDY_DOMAIN fehlt nach Environment-Vorbereitung"

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

F=(-f compose.yaml -f compose.staging.yaml)
log "Compose-Konfiguration"; docker compose "${F[@]}" config >/dev/null
log "Build"; docker compose "${F[@]}" build
log "Datenservices"; docker compose "${F[@]}" up -d postgres redis mailpit
wait_healthy postgres 180
wait_healthy redis 180
log "Django Checks vor Migration"; docker compose "${F[@]}" run --rm web python manage.py check
log "Migrationen prüfen"; docker compose "${F[@]}" run --rm web python manage.py makemigrations --check --dry-run
log "Migrationen"; docker compose "${F[@]}" run --rm web python manage.py migrate --noinput
log "Defaults"; docker compose "${F[@]}" run --rm web python manage.py seed_defaults; docker compose "${F[@]}" run --rm web python manage.py seed_prompt_catalog; docker compose "${F[@]}" run --rm web python manage.py seed_faqs; docker compose "${F[@]}" run --rm web python manage.py validate_prompt_runtime; docker compose "${F[@]}" run --rm web python manage.py bootstrap_admin
log "Static"; docker compose "${F[@]}" run --rm web python manage.py collectstatic --noinput
log "Stack"; docker compose "${F[@]}" up -d
log "Tests"; docker compose "${F[@]}" exec -T web python manage.py test
log "Check deploy"; docker compose "${F[@]}" exec -T web python manage.py check --deploy
log "Kritische Services abwarten"
wait_healthy web 240
wait_healthy worker 240
wait_healthy beat 300
wait_healthy caddy 180
wait_healthy backup 360
log "Django Ready"; docker compose "${F[@]}" exec -T web curl -fsS http://127.0.0.1:8000/health/ready/ >/dev/null
log "Marketing-Artefakte im Caddy-Container"; docker compose "${F[@]}" exec -T caddy sh -c 'test -s /srv/marketing/index.html && test -s /srv/marketing/models/head.glb && test -s /srv/marketing/models/night-landscape.png && test -s /srv/marketing/integration-patch.js'
log "Containerstatus"; docker compose "${F[@]}" ps
log "Fertig: Marketing https://${CADDY_DOMAIN}/ · Portal https://${CADDY_DOMAIN}/portal/dashboard/ · Admin https://${CADDY_DOMAIN}/ns-admin/"
