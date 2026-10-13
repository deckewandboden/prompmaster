#!/usr/bin/env bash
# Fail-closed launcher for an already reviewed and merged production release.
# Does not fetch, check out, modify databases or remove Docker volumes.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail(){ printf '[PROMPTFINISHER GO-LIVE BLOCKED] %s\n' "$*" >&2; exit 2; }
log(){ printf '[PROMPTFINISHER GO-LIVE] %s\n' "$*"; }

[[ "${PM_RELEASE_SHA:-}" =~ ^[a-f0-9]{40}$ ]] || fail 'PM_RELEASE_SHA muss die volle 40-stellige Release-SHA sein.'
[[ "${PM_GO_LIVE_CONFIRM:-}" == "$PM_RELEASE_SHA" ]] || fail 'PM_GO_LIVE_CONFIRM muss exakt der Release-SHA entsprechen.'
[[ "${PM_STAGING_ACCEPTED_SHA:-}" == "$PM_RELEASE_SHA" ]] || fail 'Staging-Abnahme für diese Release-SHA fehlt.'
for flag in PM_LEGAL_APPROVED PM_TRANSLATION_APPROVED PM_VISUAL_APPROVED PM_PAYMENT_TEST_APPROVED; do
  [[ "${!flag:-}" == YES ]] || fail "Freigabe $flag=YES fehlt."
done
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || fail 'Remote-Docker-Kontext nicht freigegeben.'
command -v git >/dev/null 2>&1 || fail 'git fehlt.'
command -v docker >/dev/null 2>&1 || fail 'docker fehlt.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose fehlt.'
[[ "$(git rev-parse --show-toplevel 2>/dev/null)" == "$PWD" ]] || fail 'Kein eigenständiges Repository-Root.'
[[ "$(git branch --show-current 2>/dev/null)" == main ]] || fail 'Produktivdeployment ist ausschließlich aus main zulässig.'
[[ "$(git rev-parse HEAD 2>/dev/null)" == "$PM_RELEASE_SHA" ]] || fail 'HEAD entspricht nicht der freigegebenen Release-SHA.'
[[ "$(git rev-parse refs/remotes/origin/main 2>/dev/null)" == "$PM_RELEASE_SHA" ]] || fail 'origin/main weicht ab; vorher git fetch origin main und SHA prüfen.'
[[ -z "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]] || fail 'Getrackte Dateien sind lokal verändert.'
[[ -f .env && ! -L .env ]] || fail 'Produktive .env fehlt oder ist ein Symlink.'
[[ "$(stat -c '%a' .env 2>/dev/null)" == 600 ]] || fail 'Die Rechte von .env müssen 0600 sein.'
log 'Produktive Umgebung und externes Restic-Backup prüfen.'
python3 scripts/validate_env.py --environment production --require-go-live || fail 'Go-Live-Environment-Gate nicht bestanden.'
if [[ "${1:-}" == --verify-only ]]; then
  log "PRE_DEPLOY_GATES=PASS; RELEASE_SHA=$PM_RELEASE_SHA; NO_DEPLOY=YES"
  exit 0
fi
[[ "$#" -eq 0 ]] || fail 'Unbekanntes Argument (zulässig: --verify-only).'
[[ "${PM_EXECUTE_GO_LIVE:-}" == YES ]] || fail 'Für tatsächliches Deployment PM_EXECUTE_GO_LIVE=YES erforderlich.'
log "Gesichertes Produktivdeployment $PM_RELEASE_SHA starten."
# deploy.sh also accepts GIT_SHA from the environment. Never let an inherited
# stale value mislabel the deployed release or its last-known-good marker.
export GIT_SHA="$PM_RELEASE_SHA"
bash scripts/deploy.sh
log 'DEPLOY_SCRIPT_COMPLETED=PASS; LIVE_HTTP_ACCEPTANCE_STILL_REQUIRED=YES'
