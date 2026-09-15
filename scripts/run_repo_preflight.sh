#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENVIRONMENT="${1:-}"
PREPARE="${2:-}"
IMAGE="${PM_VALIDATOR_IMAGE:-promptmaster-repo-validator:local}"

if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
  echo "Usage: $0 <staging|production> [--prepare-env]" >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || { echo "[FEHLER] Docker fehlt" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "[FEHLER] Docker Compose Plugin fehlt" >&2; exit 1; }

printf '[PromptMaster validator] Build reproduzierbares Validator-Image\n'
docker build -q -f Dockerfile.validator -t "$IMAGE" . >/dev/null

uid="$(id -u)"
gid="$(id -g)"
common=(
  --rm
  --user "$uid:$gid"
  -e HOME=/tmp
  -e npm_config_cache=/tmp/npm-cache
  -e "PM_DOMAIN=${PM_DOMAIN:-}"
  -e "PM_ADMIN_EMAIL=${PM_ADMIN_EMAIL:-}"
  -v "$ROOT:/repo"
)

cleanup() {
  rm -rf "$ROOT/marketing/node_modules"
}
trap cleanup EXIT

if [[ "$PREPARE" == "--prepare-env" ]]; then
  printf '[PromptMaster validator] Staging-Umgebung vorbereiten\n'
  docker run "${common[@]}" -w /repo "$IMAGE" python scripts/prepare_env.py
elif [[ -n "$PREPARE" ]]; then
  echo "[FEHLER] Unbekannte Option: $PREPARE" >&2
  exit 2
fi

[[ -f .env ]] || { echo "[FEHLER] .env fehlt" >&2; exit 1; }

printf '[PromptMaster validator] Marketing aus sauberem npm ci bauen und testen\n'
docker run "${common[@]}" -w /repo/marketing "$IMAGE" sh -lc \
  'npm ci --no-audit --no-fund && npm test && npm run build'

printf '[PromptMaster validator] Repository-Preflight\n'
docker run "${common[@]}" -w /repo "$IMAGE" python scripts/github_preflight.py

printf '[PromptMaster validator] Environment-Validierung (%s)\n' "$ENVIRONMENT"
docker run "${common[@]}" -w /repo "$IMAGE" python scripts/validate_env.py --environment "$ENVIRONMENT"

printf '[PromptMaster validator] OK\n'
