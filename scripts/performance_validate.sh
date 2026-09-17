#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

COUNT="${PM_PERFORMANCE_ROWS:-100000}"
MAX_MS="${PM_PERFORMANCE_MAX_MS:-500}"
ITERATIONS="${PM_PERFORMANCE_ITERATIONS:-20}"
PREFIX="${PM_PERFORMANCE_PREFIX:-PMPERF}"

FILES=(-f compose.yaml -f compose.staging.yaml)
[[ -f .env ]] || { echo '[FAIL] .env fehlt' >&2; exit 1; }

echo "[PromptMaster performance] Seed: ${COUNT} Zeilen je Kernliste"
docker compose "${FILES[@]}" exec -T web \
  python manage.py seed_performance --count "$COUNT" --prefix "$PREFIX"

echo "[PromptMaster performance] Benchmark: p95 <= ${MAX_MS} ms"
docker compose "${FILES[@]}" exec -T web \
  python manage.py performance_smoke \
    --prefix "$PREFIX" \
    --min-rows "$COUNT" \
    --iterations "$ITERATIONS" \
    --max-ms "$MAX_MS"

echo 'PERFORMANCE VALIDATION OK'
