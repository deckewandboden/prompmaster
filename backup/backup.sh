#!/usr/bin/env bash
set -Eeuo pipefail

# Legacy compatibility: older PromptMaster deployments used S3_REGION.
# Restic itself reads AWS_DEFAULT_REGION, so normalize once for every
# production backup/restore operation, not only in the acceptance harness.
if [[ -z "${AWS_DEFAULT_REGION:-}" && -n "${S3_REGION:-}" ]]; then
  export AWS_DEFAULT_REGION="$S3_REGION"
fi

status_dir=/status
work_dir=/tmp/pmbackup
mkdir -p "$status_dir" "$work_dir"

backup_interval="${BACKUP_INTERVAL_SECONDS:-21600}"
prune_interval="${PRUNE_INTERVAL_SECONDS:-86400}"
restore_interval="${RESTORE_TEST_INTERVAL_SECONDS:-2592000}"
backup_once="${BACKUP_ONCE:-0}"

# restic's S3 backend uses AWS_DEFAULT_REGION. Keep the historical S3_REGION
# variable as a compatibility alias so existing deployments do not silently
# fall back to us-east-1 on S3-compatible endpoints.
if [[ -z "${AWS_DEFAULT_REGION:-}" && -n "${S3_REGION:-}" ]]; then
  export AWS_DEFAULT_REGION="${S3_REGION}"
fi

json_status() {
  local file="$1" status="$2" ts="$3" size="${4:-0}" detail="${5:-}"
  printf '{"status":"%s","timestamp":"%s","size_bytes":%s,"detail":"%s"}\n' \
    "$status" "$ts" "$size" "${detail//\"/\\\"}" > "$file.tmp"
  mv "$file.tmp" "$file"
}

ensure_repository() {
  if restic cat config >/dev/null 2>&1; then
    return 0
  fi
  echo "Restic-Repository nicht initialisiert; Initialisierung wird versucht." >&2
  restic init
}

stamp_due() {
  local file="$1" interval="$2" now last=0
  now="$(date +%s)"
  [[ -f "$file" ]] && read -r last < "$file" || true
  [[ "$last" =~ ^[0-9]+$ ]] || last=0
  (( now - last >= interval ))
}

write_stamp() {
  date +%s > "$1.tmp"
  mv "$1.tmp" "$1"
}

run_restore_test() (
  # A subshell scopes EXIT cleanup to this restore, including error exits.
  local started finished root restore_target dump="" pgdata sock port=55432 count status=failed detail=""
  started="$(date -u +%Y%m%dT%H%M%SZ)"
  root="$(mktemp -d /tmp/pm-restore.XXXXXX)"
  chown root:postgres "$root"
  chmod 0750 "$root"
  restore_target="$root/restore"
  pgdata="$root/pgdata"
  sock="$root/socket"
  mkdir -p "$restore_target" "$pgdata" "$sock"
  chown -R postgres:postgres "$pgdata" "$sock"
  chmod 0700 "$restore_target" "$pgdata" "$sock"

  cleanup_restore() {
    su-exec postgres pg_ctl -D "$pgdata" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$root"
  }
  trap cleanup_restore EXIT

  if ! restic restore latest --tag promptmaster-db --target "$restore_target" >/dev/null; then
    detail="restic_restore_failed"
  else
    dump="$(find "$restore_target" -type f -name '*.dump' -print -quit)"
    if [[ -z "$dump" ]]; then
      detail="dump_missing"
    elif ! su-exec postgres initdb -D "$pgdata" -A trust --no-locale >/dev/null; then
      detail="initdb_failed"
    elif ! su-exec postgres pg_ctl -D "$pgdata" -o "-k $sock -p $port -h ''" -w start >/dev/null; then
      detail="postgres_start_failed"
    elif ! createdb -h "$sock" -p "$port" -U postgres restoretest; then
      detail="createdb_failed"
    elif ! pg_restore -h "$sock" -p "$port" -U postgres -d restoretest --exit-on-error --single-transaction --no-owner --no-acl "$dump"; then
      detail="pg_restore_failed"
    else
      count="$(psql -h "$sock" -p "$port" -U postgres -d restoretest -Atc 'select count(*) from django_migrations;' 2>/dev/null || true)"
      if [[ "$count" =~ ^[1-9][0-9]*$ ]]; then
        status=ok
        detail="migrations=$count;backup=$(basename "$dump")"
      else
        detail="integrity_check_failed"
      fi
    fi
  fi

  finished="$(date -u +%Y%m%dT%H%M%SZ)"
  printf '{"status":"%s","started_at":"%s","finished_at":"%s","backup_ref":"%s","detail":"%s"}\n' \
    "$status" "$started" "$finished" "${dump:+$(basename "$dump")}" "${detail//\"/\\\"}" \
    > "$status_dir/last-restore.json.tmp"
  mv "$status_dir/last-restore.json.tmp" "$status_dir/last-restore.json"

  [[ "$status" == ok ]]
)

ensure_repository

while true; do
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  dump="$work_dir/promptmaster-${ts}.dump"

  if pg_dump -Fc -f "$dump"; then
    size="$(stat -c '%s' "$dump" 2>/dev/null || echo 0)"
    if restic backup "$dump" --tag promptmaster-db; then
      json_status "$status_dir/last-backup.json" verifying "$ts" "$size" "$(basename "$dump")"
      if stamp_due "$status_dir/last-prune-at" "$prune_interval"; then
        if restic forget --prune --tag promptmaster-db --keep-daily 14 --keep-weekly 8 --keep-monthly 6; then
          write_stamp "$status_dir/last-prune-at"
        else
          echo "WARNUNG: Restic-Retention/Prune fehlgeschlagen; Backup selbst war erfolgreich." >&2
        fi
      fi
      if stamp_due "$status_dir/last-restore-at" "$restore_interval"; then
        if run_restore_test; then
          write_stamp "$status_dir/last-restore-at"
        else
          echo "FEHLER: automatischer Restore-Test fehlgeschlagen." >&2
          json_status "$status_dir/last-backup.json" restore_failed "$ts" "$size" "restore_test_failed"
          exit 1
        fi
      fi
      json_status "$status_dir/last-backup.json" ok "$ts" "$size" "$(basename "$dump")"
    else
      json_status "$status_dir/last-backup.json" restic_failed "$ts" "$size" "restic_backup_failed"
    fi
  else
    json_status "$status_dir/last-backup.json" pg_dump_failed "$ts" 0 "pg_dump_failed"
  fi

  rm -f "$dump"
  if [[ "$backup_once" == "1" ]]; then
    [[ -f "$status_dir/last-backup.json" ]] || exit 1
    grep -q '"status":"ok"' "$status_dir/last-backup.json" || exit 1
    exit 0
  fi
  sleep "$backup_interval"
done
