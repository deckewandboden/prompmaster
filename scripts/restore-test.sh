#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY fehlt}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD fehlt}"

tmp="$(mktemp -d)"
container="pm-restore-test-$$-${RANDOM}"
cleanup(){
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

restic restore latest --tag promptmaster-db --target "$tmp"
# -print -quit avoids a find|head pipeline that can fail with SIGPIPE under
# `set -o pipefail` when more than one matching dump exists.
dump="$(find "$tmp" -name '*.dump' -type f -print -quit)"
[[ -n "$dump" ]] || { echo 'Kein Dump im Backup' >&2; exit 1; }

docker run --rm -d \
  --name "$container" \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=restoretest \
  postgres:18-alpine >/dev/null

ready=0
for _ in {1..30}; do
  if docker exec "$container" pg_isready -U postgres -d restoretest >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'Restore-Test-PostgreSQL wurde nicht rechtzeitig bereit.' >&2; exit 1; }

docker cp "$dump" "$container":/tmp/db.dump
docker exec "$container" pg_restore -U postgres -d restoretest --no-owner --no-acl /tmp/db.dump
docker exec "$container" psql -U postgres -d restoretest -Atc 'select count(*) from django_migrations;' | grep -Eq '^[1-9][0-9]*$'
echo 'RESTORE TEST OK'
