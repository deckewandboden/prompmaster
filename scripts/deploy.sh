#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

F=(-f compose.yaml -f compose.production.yaml)
STATE_DIR="${PM_DEPLOY_STATE_DIR:-artifacts/deploy-state}"
mkdir -p "$STATE_DIR"

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

CURRENT_SHA="$GIT_SHA"
LAST_SUCCESS_FILE="$STATE_DIR/last-successful-sha"
PREVIOUS_SHA=""
[[ -f "$LAST_SUCCESS_FILE" ]] && PREVIOUS_SHA="$(tr -d '[:space:]' < "$LAST_SUCCESS_FILE")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_STATUS_FILE="$STATE_DIR/pre-deploy-backup-${STAMP}.json"

log(){ printf '[PromptMaster deploy] %s\n' "$*"; }

rollback_help(){
  local line="${1:-unknown}"
  printf '\n[PromptMaster deploy] FEHLER in Zeile %s. Deployment NICHT freigegeben.\n' "$line" >&2
  printf '[PromptMaster deploy] Datenbankmigrationen werden NICHT automatisch rückwärts ausgeführt.\n' >&2
  if [[ -n "$PREVIOUS_SHA" && "$PREVIOUS_SHA" != "source-archive" ]]; then
    printf '[PromptMaster deploy] Last-known-good Git SHA: %s\n' "$PREVIOUS_SHA" >&2
    printf '[PromptMaster deploy] Code-Rollback nach Ursachenprüfung:\n' >&2
    printf '  git checkout %s\n' "$PREVIOUS_SHA" >&2
    printf '  docker compose -f compose.yaml -f compose.production.yaml build\n' >&2
    printf '  docker compose -f compose.yaml -f compose.production.yaml up -d --remove-orphans\n' >&2
  else
    printf '[PromptMaster deploy] Kein verwendbarer last-known-good Git SHA protokolliert; vorherigen freigegebenen Release-Tag/Commit verwenden.\n' >&2
  fi
  if [[ -s "$BACKUP_STATUS_FILE" ]]; then
    printf '[PromptMaster deploy] Pre-Deploy-Backupstatus: %s\n' "$BACKUP_STATUS_FILE" >&2
    printf '[PromptMaster deploy] Falls ein DB-Restore erforderlich ist: erst Anwendung stoppen, Backup verifizieren und den dokumentierten Restore-Prozess verwenden.\n' >&2
  else
    printf '[PromptMaster deploy] Kein verifizierter Pre-Deploy-Backupstatus protokolliert. Keine destruktiven Rollback-Schritte ausführen.\n' >&2
  fi
}
trap 'rollback_help "$LINENO"' ERR

wait_web_ready(){
  local i
  for i in $(seq 1 45); do
    if docker compose "${F[@]}" exec -T web curl -fsS http://127.0.0.1:8000/health/ready/ >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_worker(){
  local i reply
  for i in $(seq 1 20); do
    reply="$(docker compose "${F[@]}" exec -T web celery -A config inspect ping --timeout 3 2>&1 || true)"
    if [[ "$reply" == *pong* ]]; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_beat(){
  local i ok
  for i in $(seq 1 30); do
    ok="$(docker compose "${F[@]}" exec -T web python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from apps.ops.models import BeatHeartbeat; h=BeatHeartbeat.objects.filter(name='default').first(); print('1' if h and h.last_seen_at >= timezone.now()-timedelta(minutes=3) else '0')" 2>/dev/null | tail -n1 | tr -d '\r' || true)"
    if [[ "$ok" == "1" ]]; then
      return 0
    fi
    sleep 4
  done
  return 1
}

bash scripts/run_repo_preflight.sh production
log "Deploy ${CURRENT_SHA} · bisheriger last-known-good: ${PREVIOUS_SHA:-keiner}"
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
docker compose "${F[@]}" run --rm --no-deps web sh -c 'cat /var/run/promptmaster-backup/last-backup.json' > "$BACKUP_STATUS_FILE"
python3 - "$BACKUP_STATUS_FILE" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text(encoding='utf-8'))
if data.get('status') != 'ok':
    raise SystemExit(f"Pre-Deploy-Backup ist nicht OK: {data.get('status')}")
print(f"Pre-Deploy-Backup OK: {data.get('timestamp', 'unknown')}")
PY
log "Migrationen anwenden"
docker compose "${F[@]}" run --rm web python manage.py migrate --noinput
log "Defaults und zentralen Prompt-Katalog aktualisieren"
docker compose "${F[@]}" run --rm web python manage.py seed_defaults
docker compose "${F[@]}" run --rm web python manage.py seed_prompt_catalog
docker compose "${F[@]}" run --rm web python manage.py seed_faqs
docker compose "${F[@]}" run --rm web python manage.py validate_prompt_runtime
log "Static Assets sammeln"
docker compose "${F[@]}" run --rm web python manage.py collectstatic --noinput
log "Stack kontrolliert starten"
docker compose "${F[@]}" up -d --remove-orphans
log "Production Security Check"
docker compose "${F[@]}" exec -T web python manage.py check --deploy
log "Django Readiness abwarten"
wait_web_ready
log "Celery Worker prüfen"
wait_worker
log "Celery Beat prüfen"
wait_beat
log "Caddy-Konfiguration prüfen"
docker compose "${F[@]}" exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null
log "Containerstatus"
docker compose "${F[@]}" ps
printf '%s\n' "$CURRENT_SHA" > "$LAST_SUCCESS_FILE.tmp"
mv "$LAST_SUCCESS_FILE.tmp" "$LAST_SUCCESS_FILE"
printf '{"git_sha":"%s","deployed_at":"%s","backup_status_file":"%s"}\n' "$CURRENT_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$BACKUP_STATUS_FILE" > "$STATE_DIR/last-successful-deploy.json"
trap - ERR
log "Deployment abgeschlossen und als last-known-good markiert: ${CURRENT_SHA}"
