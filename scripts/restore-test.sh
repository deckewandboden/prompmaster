#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY fehlt}"; : "${RESTIC_PASSWORD:?RESTIC_PASSWORD fehlt}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
restic restore latest --tag promptmaster-db --target "$tmp"
dump="$(find "$tmp" -name '*.dump' -type f | head -1)"; [[ -n "$dump" ]] || { echo 'Kein Dump im Backup'; exit 1; }
docker run --rm -d --name pm-restore-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=restoretest postgres:18-alpine >/dev/null
trap 'docker rm -f pm-restore-test >/dev/null 2>&1 || true; rm -rf "$tmp"' EXIT
for i in {1..30}; do docker exec pm-restore-test pg_isready -U postgres -d restoretest >/dev/null 2>&1 && break; sleep 1; done
docker cp "$dump" pm-restore-test:/tmp/db.dump
docker exec pm-restore-test pg_restore -U postgres -d restoretest --no-owner --no-acl /tmp/db.dump
docker exec pm-restore-test psql -U postgres -d restoretest -Atc 'select count(*) from django_migrations;' | grep -Eq '^[1-9][0-9]*$'
echo 'RESTORE TEST OK'
