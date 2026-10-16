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

printf '[PROMPTFINISHER validator] Build reproduzierbares Validator-Image\n'
docker build -q -f Dockerfile.validator -t "$IMAGE" . >/dev/null

uid="$(id -u)"
gid="$(id -g)"

# Docker --rm normally destroys npm's error logs. Keep any failure diagnostics
# outside the container in a private folder within Git metadata (or /tmp for
# source-archive installations); never copy them into marketing/dist or git.
if [[ -d "$ROOT/.git" && ! -L "$ROOT/.git" ]]; then
  npm_diag_parent="$ROOT/.git/PROMPTFINISHER_NPM_DIAGNOSTICS"
  mkdir -p "$npm_diag_parent"
  chmod 700 "$npm_diag_parent"
else
  npm_diag_parent="\${TMPDIR:-/tmp}"
fi
npm_diag="$(mktemp -d "$npm_diag_parent/validator-XXXXXXXX")"
chmod 700 "$npm_diag"
umask 077

cleanup() {
  local status=$?
  rm -rf -- "$ROOT/marketing/node_modules" || true
  if [[ "$status" -eq 0 ]]; then
    rm -rf -- "$npm_diag"
  else
    printf '[PROMPTFINISHER validator] NPM_DIAGNOSTICS=%s\n' "$npm_diag" >&2
    printf '[PROMPTFINISHER validator] Diagnostics retained; contains npm logs, handle as private.\n' >&2
  fi
}
trap cleanup EXIT

common=(
  --rm
  --user "$uid:$gid"
  -e HOME=/tmp
  -e "PM_DOMAIN=\${PM_DOMAIN:-}"
  -e "PM_ADMIN_EMAIL=\${PM_ADMIN_EMAIL:-}"
  -v "$ROOT:/repo"
  -v "$npm_diag:/npm-diagnostics"
)

if [[ "$PREPARE" == "--prepare-env" ]]; then
  printf '[PROMPTFINISHER validator] Staging-Umgebung vorbereiten\n'
  docker run "\${common[@]}" -w /repo "$IMAGE" python scripts/prepare_env.py
elif [[ -n "$PREPARE" ]]; then
  echo "[FEHLER] Unbekannte Option: $PREPARE" >&2
  exit 2
fi

[[ -f .env ]] || { echo "[FEHLER] .env fehlt" >&2; exit 1; }

npm_install() {
  local attempt="$1"
  local logfile="$npm_diag/npm-ci-attempt-\${attempt}.log"
  if docker run "\${common[@]}" \
    -e "npm_config_cache=/npm-diagnostics/cache-\${attempt}" \
    -w /repo/marketing "$IMAGE" sh -lc \
    'umask 077; npm ci --no-audit --no-fund' >"$logfile" 2>&1; then
    cat "$logfile"
    return 0
  fi
  cat "$logfile" >&2
  return 1
}

printf '[PROMPTFINISHER validator] Marketing aus sauberem npm ci bauen und testen\n'
if npm_install 1; then
  :
elif grep -Fq 'Exit handler never called!' "$npm_diag/npm-ci-attempt-1.log"; then
  printf '[PROMPTFINISHER validator] npm-interner Exit-handler-Fehler; genau ein kontrollierter Versuch mit neuem Cache.\n'
  npm_install 2 || { echo "[FEHLER] npm ci nach kontrolliertem Wiederholungsversuch fehlgeschlagen." >&2; exit 1; }
else
  echo "[FEHLER] npm ci fehlgeschlagen (kein bekanntes npm-internes Exit-handler-Problem); keine automatische Wiederholung." >&2
  exit 1
fi

marketing_log="$npm_diag/marketing-tests-and-build.log"
if docker run "\${common[@]}" -w /repo/marketing "$IMAGE" sh -lc \
  'umask 077; npm test && npm run build' >"$marketing_log" 2>&1; then
  cat "$marketing_log"
else
  cat "$marketing_log" >&2
  echo "[FEHLER] Marketing-Tests oder -Build fehlgeschlagen; kein automatischer Retry." >&2
  exit 1
fi

printf '[PROMPTFINISHER validator] Repository-Preflight\n'
docker run "\${common[@]}" -w /repo "$IMAGE" python scripts/github_preflight.py

printf '[PROMPTFINISHER validator] Environment-Validierung (%s)\n' "$ENVIRONMENT"
docker run "\${common[@]}" -w /repo "$IMAGE" python scripts/validate_env.py --environment "$ENVIRONMENT"

printf '[PROMPTFINISHER validator] OK\n'