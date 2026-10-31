#!/usr/bin/env bash
# GitHub-first, one-command update of an EXISTING PROMPTFINISHER production site.
# Initial/commercial go-live remains subject to scripts/go_live.sh approvals.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail() { printf '[PROMPTFINISHER GITHUB RELEASE BLOCKED] %s\n' "$*" >&2; exit 2; }
log() { printf '[PROMPTFINISHER GITHUB RELEASE] %s\n' "$*"; }

[[ "$#" -eq 0 || ( "$#" -eq 1 && "$1" == '--verify-only' ) ]] || fail 'Usage: bash scripts/release_from_github.sh [--verify-only]'
mode="${1:-deploy}"
for binary in git docker curl flock sha256sum; do
  command -v "$binary" >/dev/null 2>&1 || fail "Required command missing: $binary"
done
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || fail 'Remote Docker daemon/context forbidden'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose plugin unavailable'
[[ "$(git rev-parse --show-toplevel 2>/dev/null)" == "$PWD" ]] || fail 'Not a standalone Git repository root'
[[ "$(git branch --show-current 2>/dev/null)" == main ]] || fail 'Only main may be deployed'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Tracked files changed; refusing to discard local changes'
remote_url="$(git remote get-url origin 2>/dev/null)" || fail 'Git origin unavailable'
case "$remote_url" in
  git@github.com:deckewandboden/prompmaster|git@github.com:deckewandboden/prompmaster.git|https://github.com/deckewandboden/prompmaster|https://github.com/deckewandboden/prompmaster.git|ssh://git@github.com/deckewandboden/prompmaster|ssh://git@github.com/deckewandboden/prompmaster.git) ;;
  *) fail 'Git origin does not point to the approved PROMPTFINISHER GitHub repository' ;;
esac
[[ -f .env && ! -L .env ]] || fail 'Production .env is missing or symlinked'
[[ "$(stat -c '%a' .env)" == 600 ]] || fail 'Production .env must have permission 0600'
state_dir="${PM_DEPLOY_STATE_DIR:-artifacts/deploy-state}"
[[ -s "$state_dir/last-successful-sha" ]] || fail 'No existing accepted deployment; initial go-live must use scripts/go_live.sh and its approval gates'
mkdir -p "$state_dir"
exec 9>"$state_dir/github-release.lock"
flock -n 9 || fail 'Another GitHub release is in progress'

previous="$(git rev-parse HEAD)"
log 'Checking GitHub main (fast-forward only, no reset and no force)'
git fetch --no-tags origin main
target="$(git rev-parse refs/remotes/origin/main)"
[[ "$target" =~ ^[a-f0-9]{40}$ ]] || fail 'Invalid GitHub release SHA'
git merge-base --is-ancestor "$previous" "$target" || fail 'Local main diverged from GitHub; no destructive reset'
# A verification request must never fast-forward the local worktree. The fetch
# above refreshes Git metadata only; no application files or containers change.
if [[ "$mode" == --verify-only ]]; then
  log "LOCAL_SHA=$previous; GITHUB_MAIN_SHA=$target"
  if [[ "$previous" == "$target" ]]; then
    log 'SOURCE_SYNC=PASS; EXISTING_INSTALLATION=PASS; NO_DEPLOY=YES; NO_WORKTREE_WRITE=YES'
  else
    log 'SOURCE_SYNC=PENDING; EXISTING_INSTALLATION=PASS; NO_DEPLOY=YES; NO_WORKTREE_WRITE=YES'
  fi
  exit 0
fi

git merge --ff-only refs/remotes/origin/main
sha="$(git rev-parse HEAD)"
[[ "$sha" == "$target" ]] || fail 'Release SHA not equal to GitHub main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Tracked files changed after Git update'
[[ -f scripts/deploy.sh ]] || fail 'Repository deploy script missing'
log "RELEASE_SHA=$sha"

# Production rollout is performed by the EXISTING backup/migration/health guarded
# deploy script. No --volumes, no reset, no Mollie live-activation commands.
export GIT_SHA="$sha"
bash scripts/deploy.sh
[[ "$(cat "$state_dir/last-successful-sha")" == "$sha" ]] || fail 'Deploy did not record the exact release SHA'

domain="$(awk -F= '$1=="CADDY_DOMAIN" {sub(/^[^=]*=/, ""); v=$0} END {print v}' .env | tr -d '\r"')"
[[ "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ && "$domain" == *.* ]] || fail 'Invalid production CADDY_DOMAIN; refusing public verification'
base="https://$domain"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fetch() {
  local path="$1" file="$2" status
  status="$(curl -sS -L --connect-timeout 10 --max-time 45 --retry 2 --retry-delay 2 -o "$file" -w '%{http_code}' "$base$path")" || fail "TLS/HTTP request failed: $path"
  [[ "$status" == 200 ]] || fail "Unexpected HTTP $status for $path"
}
log 'Checking real public HTTPS responses (strict TLS, no -k)'
fetch / "$tmp/home"
fetch /free/ "$tmp/free"
fetch /auth/login/ "$tmp/login"
fetch /health/ready/ "$tmp/ready"
fetch /static/js/promptfinisher_product_i18n.20261011.js "$tmp/i18n"
# A 200 response or translated labels are not evidence of the CURRENT release.
# Compare the served bytes with the exact checked-out, approved GitHub asset.
asset_source="backend/static/js/promptfinisher_product_i18n.20261011.js"
[[ -f "$asset_source" ]] || fail 'Source product locale asset missing'
asset_source_sha="$(sha256sum "$asset_source" | awk '{print $1}')"
asset_live_sha="$(sha256sum "$tmp/i18n" | awk '{print $1}')"
log "PUBLIC_I18N_SOURCE_SHA256=$asset_source_sha; PUBLIC_I18N_LIVE_SHA256=$asset_live_sha"
[[ "$asset_live_sha" == "$asset_source_sha" ]] || fail 'PUBLIC_I18N_ASSET_PARITY=FAIL; live static is stale; release must not be accepted'
log 'PUBLIC_I18N_ASSET_PARITY=PASS'
grep -Fq 'PROMPTFINISHER' "$tmp/i18n" || fail 'Public i18n script has unexpected content'
for language in de en es pt tr ru pl fr it nl; do
  grep -Fq "\"$language\":" "$tmp/i18n" || fail "Public i18n catalog missing $language"
done
grep -Fq 'promptfinisher_product_i18n.20261011.js' "$tmp/free" || fail 'Free page does not load the language bundle'
# Validate the raw HTTP language before JavaScript starts.  A successful i18n
# bundle download alone does not prove that the Free document has the right
# language metadata (caught by the operator's R5 live acceptance).
for language in de en es pt tr ru pl fr it nl; do
  status="$(curl -sS -L --connect-timeout 10 --max-time 45 --retry 2 --retry-delay 2 \
    -H "Cookie: promptfinisher_language=$language" \
    -o "$tmp/free-$language" -w '%{http_code}' "$base/free/")" || fail "Free language request failed: $language"
  [[ "$status" == 200 ]] || fail "Free language $language returned HTTP $status"
  grep -Fq "<html lang=\"$language\">" "$tmp/free-$language" || fail "Free raw HTML lang mismatch: $language"
done
# Pro requires authentication; HTTP must resolve to either Pro or a login page.
fetch /pro/app/ "$tmp/pro"
[[ -s "$tmp/pro" ]] || fail 'Pro route returned an empty document'
# The public asset must remain mutable (otherwise users can see stale languages).
headers="$(curl -sS -I --connect-timeout 10 --max-time 30 "$base/static/js/promptfinisher_product_i18n.20261011.js")" || fail 'Public asset header check failed'
printf '%s\n' "$headers" | tr -d '\r' | grep -Eiq '^cache-control:.*no-cache' || fail 'Language asset is served with stale-cache policy'

receipt="$state_dir/github-release-verified-$sha.txt"
printf 'RELEASE_SHA=%s\nLIVE_HTTPS=PASS\nLANGUAGES=de,en,es,pt,tr,ru,pl,fr,it,nl\nCHECKOUT_ACTIVATION=NOT_PERFORMED\n' "$sha" > "$receipt"
chmod 600 "$receipt"
log "DEPLOY=PASS; PUBLIC_HTTPS=PASS; LANGUAGES=10; RELEASE_SHA=$sha"
log "EVIDENCE=$receipt"
