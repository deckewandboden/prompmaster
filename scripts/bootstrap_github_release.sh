#!/usr/bin/env bash
# One-time repair of legacy SSH Git origin and dirty tracked source files.
# Source is the PUBLIC deckewandboden/prompmaster repository; no token needed.
# Only runs the repository's existing validated release_from_github.sh.
set -Eeuo pipefail
umask 077

fail() { printf '[PROMPTFINISHER GITHUB BOOTSTRAP BLOCKED] %s\n' "$*" >&2; exit 2; }
log() { printf '[PROMPTFINISHER GITHUB BOOTSTRAP] %s\n' "$*"; }

[[ "$#" -eq 0 ]] || fail 'No arguments supported'
for name in git bash mktemp sha256sum stat flock; do
  command -v "$name" >/dev/null 2>&1 || fail "Required command missing: $name"
done
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || fail 'Remote Docker context forbidden'
ROOT="${PM_GITHUB_RELEASE_ROOT:-/root/projekte/docker/promptmaster}"
[[ "$ROOT" == /* && -d "$ROOT/.git" ]] || fail 'Production repository root missing'
cd "$ROOT"
[[ "$(git rev-parse --show-toplevel 2>/dev/null)" == "$PWD" ]] || fail 'Unexpected Git checkout root'
[[ "$(git branch --show-current)" == main ]] || fail 'Only main can be updated'
[[ -f .env && ! -L .env && "$(stat -c '%a' .env)" == 600 ]] || fail 'Production .env missing, symlinked or not 0600'
state_dir="${PM_DEPLOY_STATE_DIR:-artifacts/deploy-state}"
[[ -s "$state_dir/last-successful-sha" ]] || fail 'No accepted existing deployment marker; initial go-live requires separate approval'
exec 8>"$state_dir/github-bootstrap.lock"
flock -n 8 || fail 'Another GitHub bootstrap is running'

origin="$(git config --get remote.origin.url 2>/dev/null)" || fail 'Git origin unavailable'
case "$origin" in
  git@github.com:deckewandboden/prompmaster|git@github.com:deckewandboden/prompmaster.git|ssh://git@github.com/deckewandboden/prompmaster|ssh://git@github.com/deckewandboden/prompmaster.git|https://github.com/deckewandboden/prompmaster|https://github.com/deckewandboden/prompmaster.git) ;;
  *) fail 'Unexpected Git origin; refusing to switch remote or touch files' ;;
esac
PUBLIC_HTTPS='https://github.com/deckewandboden/prompmaster.git'
before="$(git rev-parse HEAD)"
[[ "$before" =~ ^[0-9a-f]{40}$ ]] || fail 'Invalid local SHA'

# Check public HTTPS GitHub access and fast-forward compatibility BEFORE
# touching the local tracked edits. A missing SSH key cannot block this fetch.
log 'Checking public GitHub via HTTPS (no private key or token required)'
git fetch --no-tags "$PUBLIC_HTTPS" refs/heads/main || fail 'GitHub HTTPS fetch failed; no worktree modifications made'
target="$(git rev-parse FETCH_HEAD)"
[[ "$target" =~ ^[0-9a-f]{40}$ ]] || fail 'Invalid GitHub main SHA'
git merge-base --is-ancestor "$before" "$target" || fail 'Local main diverged; refusing any reset or stash'
log "LOCAL_SHA=$before; GITHUB_MAIN_SHA=$target"

# Tracked edits are the live host's old local branding/customization. Preserve
# ALL of them in both a Git stash and a self-contained Git bundle, plus patch.
# Never include untracked/ignored files (notably production .env).
dirty="$(git status --porcelain --untracked-files=no)"
if [[ -n "$dirty" ]]; then
  rescue_base="${PM_LOCAL_EDIT_RESCUE_DIR:-"$(dirname "$ROOT")/.promptfinisher-local-edit-rescue"}"
  [[ "$rescue_base" == /* ]] || fail 'Rescue location must be absolute'
  mkdir -p "$rescue_base"
  chmod 700 "$rescue_base"
  rescue="$(mktemp -d "$rescue_base/release-XXXXXXXX")"
  chmod 700 "$rescue"
  git status --porcelain --untracked-files=no > "$rescue/modified-tracked-status.txt"
  git diff --binary HEAD > "$rescue/modified-tracked.patch"
  sha256sum "$rescue/modified-tracked.patch" > "$rescue/modified-tracked.sha256"
  printf 'ORIGINAL_HEAD=%s\nORIGINAL_ORIGIN=%s\nTARGET_SHA=%s\n' "$before" "$origin" "$target" > "$rescue/source-info.txt"
  previous_stash="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  log "Preserving modified tracked files in protected backup: $rescue"
  git stash push -m "PROMPTFINISHER_RESCUE_$(date -u +%Y%m%dT%H%M%SZ)" ||
    fail 'Git stash failed; stop without a forced reset'
  stash_sha="$(git rev-parse -q --verify refs/stash 2>/dev/null || true)"
  [[ "$stash_sha" =~ ^[0-9a-f]{40}$ && "$stash_sha" != "$previous_stash" ]] ||
    fail 'No new stash could be verified; do not deploy'
  printf 'STASH_SHA=%s\n' "$stash_sha" >> "$rescue/source-info.txt"
  git bundle create "$rescue/tracked-edits.bundle" HEAD refs/stash ||
    fail 'Unable to create independent Git bundle; stash remains recoverable'
  git bundle verify "$rescue/tracked-edits.bundle" > "$rescue/bundle-verification.txt" 2>&1 ||
    fail 'Independent rescue bundle verification failed; stash remains recoverable'
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] ||
    fail 'Tracked changes remain after protected stash'
  log "RESCUE=PASS; STASH_SHA=$stash_sha; PATCH_SHA256=$(cut -d' ' -f1 "$rescue/modified-tracked.sha256")"
else
  log 'Tracked worktree already clean; no local changes require rescue'
fi

# Three legacy brand assets on the live server were untracked, but are
# now tracked in GitHub main. Protect them before attempting a fast-forward.
# Unexpected collisions and non-regular files are never moved automatically.
approved_collisions=(
  "backend/static/brand/promptfinisher-favicon.svg"
  "backend/static/brand/promptfinisher-mark.png"
  "marketing/public/favicon.png"
)
collisions=()
while IFS= read -r -d '' untracked; do
  if ! git cat-file -e "$target:$untracked" 2>/dev/null; then
    continue
  fi
  approved=NO
  for item in "${approved_collisions[@]}"; do
    if [[ "$item" == "$untracked" ]]; then
      approved=YES
      break
    fi
  done
  [[ "$approved" == YES ]] ||
    fail "Unexpected untracked file collides with GitHub main: $untracked. Nothing was overwritten."
  [[ -f "$untracked" && ! -L "$untracked" ]] ||
    fail "Refusing to relocate symlink, directory or special file: $untracked"
  collisions+=("$untracked")
done < <(git ls-files --others --exclude-standard -z)

if (( ${#collisions[@]} > 0 )); then
  rescue_base="${PM_LOCAL_EDIT_RESCUE_DIR:-"$(dirname "$ROOT")/.promptfinisher-local-edit-rescue"}"
  [[ "$rescue_base" == /* ]] || fail 'Collision rescue directory must be absolute'
  [[ ! -L "$rescue_base" ]] || fail 'Collision rescue directory is a symlink'
  mkdir -p "$rescue_base"
  chmod 700 "$rescue_base"
  rescue="$(mktemp -d "$rescue_base/untracked-XXXXXXXX")"
  chmod 700 "$rescue"
  manifest="$rescue/untracked-sha256.tsv"
  printf 'path\tsha256\tbytes\n' > "$manifest"
  for path in "${collisions[@]}"; do
    backup="$rescue/copied/$path"
    original="$rescue/original/$path"
    mkdir -p "$(dirname "$backup")" "$(dirname "$original")"
    [[ -f "$path" && ! -L "$path" ]] || fail "Collision changed during rescue: $path"
    cp -- "$path" "$backup" || fail "Could not back up untracked asset: $path"
    chmod 600 "$backup"
    cmp -s -- "$path" "$backup" || fail "Untracked asset copy is not byte-identical: $path"
    digest="$(sha256sum "$path" | cut -d' ' -f1)"
    [[ "$digest" == "$(sha256sum "$backup" | cut -d' ' -f1)" ]] ||
      fail "Untracked asset SHA256 mismatch before move: $path"
    bytes="$(stat -c '%s' "$path")"
    mv -- "$path" "$original" || fail "Could not relocate untracked asset: $path"
    [[ "$(sha256sum "$original" | cut -d' ' -f1)" == "$digest" ]] ||
      fail "Relocated asset SHA256 mismatch: $path"
    cmp -s -- "$backup" "$original" ||
      fail "Independent copied and moved asset differ: $path"
    printf '%s\t%s\t%s\n' "$path" "$digest" "$bytes" >> "$manifest"
    log "UNTRACKED_ASSET_RESCUED=$path; SHA256=$digest"
  done
  log "UNTRACKED_RESCUE=PASS; COUNT=${#collisions[@]}; EVIDENCE=$rescue"
else
  log 'No untracked assets collide with GitHub main'
fi

# Public repository is verified in advance. Replace the unauthenticated SSH
# remote with its official HTTPS URL; no credentials are stored in remote URL.
git remote set-url origin "$PUBLIC_HTTPS"
[[ "$(git config --get remote.origin.url)" == "$PUBLIC_HTTPS" ]] || fail 'Failed to establish public HTTPS origin'
git fetch --no-tags origin main || fail 'GitHub HTTPS origin fetch failed'
[[ "$(git rev-parse refs/remotes/origin/main)" == "$target" ]] ||
  fail 'GitHub main moved during bootstrap; rerun after verifying new release'
git merge-base --is-ancestor HEAD "$target" || fail 'Fast-forward precondition changed'
git merge --ff-only refs/remotes/origin/main || fail 'Fast-forward blocked; no hard reset used'
[[ "$(git rev-parse HEAD)" == "$target" ]] || fail 'Checkout does not match fetched GitHub main'
[[ -f scripts/release_from_github.sh ]] || fail 'GitHub release entry point is missing'

log "SOURCE_SYNC=PASS; SHA=$target; ORIGIN=HTTPS"
log 'Starting the existing GitHub-reviewed production deploy with backup and HTTP acceptance'
bash scripts/release_from_github.sh
log "GITHUB_BOOTSTRAP=PASS; RELEASE_SHA=$target"
