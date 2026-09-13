#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
./scripts/deploy.sh
