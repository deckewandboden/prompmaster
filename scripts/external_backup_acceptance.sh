#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

confirm="${PM_EXTERNAL_BACKUP_ACCEPTANCE:-}"
if [[ "$confirm" != "RUN_EXTERNAL_S3_RESTORE" ]]; then
  echo "Refusing external backup drill. Set PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE." >&2
  exit 2
fi

F=(-f compose.yaml -f compose.production.yaml)

snapshot_id() {
  docker compose "${F[@]}" run --rm --no-deps --entrypoint /bin/sh backup -ec '
    if [ -z "${AWS_DEFAULT_REGION:-}" ] && [ -n "${S3_REGION:-}" ]; then
      export AWS_DEFAULT_REGION="$S3_REGION"
    fi
    restic snapshots --json --tag promptmaster-db 2>/dev/null \
      | grep -Eo '"'"'"id"'"'[[:space:]]*:[[:space:]]*"'"'"'[^"'"'"']*'"'"'"' \
      | tail -n 1 \
      | cut -d '"'"'"'"'"' -f 4
  ' 2>/dev/null | tail -n 1
}

docker compose "${F[@]}" run --rm --no-deps --entrypoint /bin/sh backup -ec '
  if [ -z "${AWS_DEFAULT_REGION:-}" ] && [ -n "${S3_REGION:-}" ]; then
    export AWS_DEFAULT_REGION="$S3_REGION"
  fi
  case "$RESTIC_REPOSITORY" in
    s3:*) ;;
    *)
      echo "RESTIC_REPOSITORY must be an external s3: target for this acceptance gate." >&2
      exit 3
      ;;
  esac
  test -n "$RESTIC_PASSWORD"
  test -n "$AWS_ACCESS_KEY_ID"
  test -n "$AWS_SECRET_ACCESS_KEY"
  echo "External restic repository configuration present."
'

before_snapshot="$(snapshot_id || true)"

docker compose "${F[@]}" run --rm --no-deps \
  -e BACKUP_ONCE=1 \
  -e RESTORE_TEST_INTERVAL_SECONDS=0 \
  -e PRUNE_INTERVAL_SECONDS=9999999999 \
  backup

after_snapshot="$(snapshot_id)"
if [[ -z "$after_snapshot" ]]; then
  echo "External restic backup returned no promptmaster-db snapshot id." >&2
  exit 4
fi
if [[ -n "$before_snapshot" && "$after_snapshot" == "$before_snapshot" ]]; then
  echo "External restic acceptance did not create a new snapshot." >&2
  exit 5
fi

docker compose "${F[@]}" run --rm --no-deps --entrypoint /bin/sh backup -ec '
  if [ -z "${AWS_DEFAULT_REGION:-}" ] && [ -n "${S3_REGION:-}" ]; then
    export AWS_DEFAULT_REGION="$S3_REGION"
  fi
  grep -q "\"status\":\"ok\"" /status/last-backup.json
  grep -q "\"status\":\"ok\"" /status/last-restore.json
  grep -Eq '"'"'"backup_ref"'"'[[:space:]]*:[[:space:]]*"'"'"'[^"'"'"']+'"'"'"' /status/last-restore.json
  restic snapshots --json --tag promptmaster-db >/tmp/external-snapshots.json
  grep -Eq '"'"'"id"'"'[[:space:]]*:' /tmp/external-snapshots.json
'
echo "external_snapshot_id=$after_snapshot"
echo "EXTERNAL S3/RESTIC BACKUP + ISOLATED POSTGRES RESTORE OK"
