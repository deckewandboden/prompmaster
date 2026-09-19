#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

NETWORK="\${PM_EXTERNAL_CADDY_TEST_NETWORK:-promptmaster_ci_external_proxy}"
ALIAS="\${PM_EXTERNAL_CADDY_ALIAS:-promptmaster-caddy-edge}"
F=(-f compose.yaml -f compose.staging.yaml -f compose.external-caddy.yaml)

log(){ printf '[PromptMaster external-caddy test] %s\n' "$*"; }

cleanup(){
  PM_EXTERNAL_CADDY_NETWORK="$NETWORK" PM_EXTERNAL_CADDY_ALIAS="$ALIAS" \
    docker compose "\${F[@]}" down --remove-orphans >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f compose.yaml -f compose.staging.yaml down --remove-orphans

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
export PM_EXTERNAL_CADDY_NETWORK="$NETWORK"
export PM_EXTERNAL_CADDY_ALIAS="$ALIAS"

log "Compose-Konfiguration im External-Caddy-Modus prüfen"
docker compose "\${F[@]}" config >/dev/null
log "External-Caddy-Stack starten"
docker compose "\${F[@]}" up -d

cid="$(docker compose "\${F[@]}" ps -q caddy)"
[[ -n "$cid" ]] || { echo "Caddy container missing" >&2; exit 1; }

for _ in $(seq 1 60); do
  if docker compose "\${F[@]}" exec -T caddy wget -qO- http://127.0.0.1:8081/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose "\${F[@]}" exec -T caddy wget -qO- http://127.0.0.1:8081/healthz >/dev/null

bindings="$(
  docker inspect "$cid" --format '{{range $port, $bindings := .NetworkSettings.Ports}}{{if $bindings}}{{range $bindings}}{{println $port .HostIp .HostPort}}{{end}}{{end}}{{end}}' |
    awk '$1=="80/tcp" || $1=="443/tcp"'
)"
[[ -z "$bindings" ]] || {
  echo "External-Caddy mode unexpectedly publishes host 80/443: $bindings" >&2
  exit 1
}

domain="$(awk -F= '$1=="CADDY_DOMAIN"{sub(/^[^=]*=/,""); print $0}' .env | tail -n1 | tr -d '\r"')"
[[ -n "$domain" ]] || domain=localhost

log "Login-Upstream über externes Proxy-Netz testen"
login="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -fsS -H "Host: $domain" "http://$ALIAS/auth/login/"
)"
grep -qiE 'anmelden|login' <<<"$login" || {
  echo "Login response through external Caddy is unexpected" >&2
  exit 1
}

log "Katalog-Upstream über externes Proxy-Netz testen"
catalog="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -fsS -H "Host: $domain" "http://$ALIAS/catalog.json"
)"
python3 - "$catalog" <<'PY'
import json, sys
payload=json.loads(sys.argv[1])
if payload.get('application_count') != 34 or payload.get('task_count') != 194:
    raise SystemExit(f"catalog contract drift via external Caddy: {payload}")
PY

log "External-Caddy-Rehearsal OK"
