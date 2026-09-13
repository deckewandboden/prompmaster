#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T backup sh -c 'kill -ALRM 1' || docker compose restart backup
