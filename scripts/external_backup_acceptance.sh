#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

confirm="${PM_EXTERNAL_BACKUP_ACCEPTANCE:-}"
if [[ "$confirm" != "RUN_EXTERNAL_S3_RESTORE" ]]; then
  echo "Refusing external backup drill. Set PM_EXTERNAL_BACKUP_ACCEPTANCE=RUN_EXTERNAL_S3_RESTORE." >&2
  exit 2
fi

F=(-f compose.yaml -f compose.production.yaml)

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

docker compose "${F[@]}" run --rm --no-deps   -e BACKUP_ONCE=1   -e RESTORE_TEST_INTERVAL_SECONDS=0   -e PRUNE_INTERVAL_SECONDS=9999999999   backup

docker compose "${F[@]}" run --rm --no-deps --entrypoint /bin/sh backup -ec '
  if [ -z "${AWS_DEFAULT_REGION:-}" ] && [ -n "${S3_REGION:-}" ]; then
    export AWS_DEFAULT_REGION="$S3_REGION"
  fi
  grep -q "\"status\":\"ok\"" /status/last-backup.json
  grep -q "\"status\":\"ok\"" /status/last-restore.json
  restic snapshots --tag promptmaster-db >/tmp/external-snapshots.txt
  test -s /tmp/external-snapshots.txt
  echo "EXTERNAL S3/RESTIC BACKUP + ISOLATED POSTGRES RESTORE OK"
'
