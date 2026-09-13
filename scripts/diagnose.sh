#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
docker compose ps
docker compose logs --tail=100 web worker beat postgres redis caddy
