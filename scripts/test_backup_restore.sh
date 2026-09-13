#!/usr/bin/env bash
# Destructive failure injection is confined to an ephemeral CI container.
# No snapshots or volumes are removed by this test.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ "${GITHUB_ACTIONS:-}" == true ]] || { echo 'Only run in isolated GitHub Actions staging.' >&2; exit 1; }
F=(-f compose.yaml -f compose.staging.yaml -f compose.production.yaml)
docker compose "${F[@]}" stop backup
if docker compose "${F[@]}" run --rm --no-deps -e BACKUP_ONCE=1 -e RESTORE_TEST_INTERVAL_SECONDS=0 --entrypoint /bin/sh backup -c '
  mkdir /tmp/fail-restore
  printf "#!/bin/sh\nexit 77\n" > /tmp/fail-restore/pg_restore
  chmod 0755 /tmp/fail-restore/pg_restore
  export PATH=/tmp/fail-restore:$PATH
  exec /usr/local/bin/backup.sh
'; then
  echo 'Injected pg_restore failure returned success' >&2
  exit 1
fi
docker compose "${F[@]}" exec -T web python -c "import json; from pathlib import Path; p=Path('/var/run/promptmaster-backup'); assert json.loads((p/'last-backup.json').read_text())['status']=='restore_failed'; r=json.loads((p/'last-restore.json').read_text()); assert r['status']=='failed' and r['detail']=='pg_restore_failed'"
docker compose "${F[@]}" run --rm --no-deps -e BACKUP_ONCE=1 -e RESTORE_TEST_INTERVAL_SECONDS=0 backup
docker compose "${F[@]}" exec -T web python -c "import json; from pathlib import Path; p=Path('/var/run/promptmaster-backup'); assert all(json.loads((p/name).read_text())['status']=='ok' for name in ('last-backup.json','last-restore.json'))"
echo 'BACKUP RESTORE FAILURE/RECOVERY OK'
