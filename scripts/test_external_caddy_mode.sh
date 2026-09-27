#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

NETWORK="${PM_EXTERNAL_CADDY_TEST_NETWORK:-promptmaster_ci_external_proxy}"
ALIAS="${PM_EXTERNAL_CADDY_ALIAS:-promptmaster-caddy-edge}"
F=(-f compose.yaml -f compose.staging.yaml -f compose.external-caddy.yaml)

log(){ printf '[PromptMaster external-caddy test] %s\n' "$*"; }

cleanup(){
  PM_EXTERNAL_CADDY_NETWORK="$NETWORK" PM_EXTERNAL_CADDY_ALIAS="$ALIAS" \
    docker compose "${F[@]}" down --remove-orphans >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f compose.yaml -f compose.staging.yaml down --remove-orphans

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
export PM_EXTERNAL_CADDY_NETWORK="$NETWORK"
export PM_EXTERNAL_CADDY_ALIAS="$ALIAS"

log "Compose-Konfiguration im External-Caddy-Modus prüfen"
docker compose "${F[@]}" config >/dev/null
log "External-Caddy-Stack starten"
docker compose "${F[@]}" up -d

cid="$(docker compose "${F[@]}" ps -q caddy)"
[[ -n "$cid" ]] || { echo "Caddy container missing" >&2; exit 1; }

for _ in $(seq 1 60); do
  if docker compose "${F[@]}" exec -T caddy wget -qO- http://127.0.0.1:8081/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose "${F[@]}" exec -T caddy wget -qO- http://127.0.0.1:8081/healthz >/dev/null

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

log "Marketing und Original-Kopf über externes Proxy-Netz testen"
home="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1     -fsS -H "Host: $domain" "http://$ALIAS/"
)"
grep -qi 'PROMPTMASTER' <<<"$home" || {
  echo "Marketing response through external Caddy is unexpected" >&2
  exit 1
}
head_size="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1     -fsS -H "Host: $domain" "http://$ALIAS/models/head.glb" | wc -c
)"
[[ "$head_size" -gt 100000 ]] || {
  echo "Original head.glb is missing or unexpectedly small via external Caddy: $head_size bytes" >&2
  exit 1
}

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
products={
    item.get('id'): item
    for item in payload.get('products', [])
    if isinstance(item, dict) and item.get('id')
}
pro=products.get('PROMPTMASTER_PRO') or {}
names=payload.get('proApplicationNames') or []
contract_ok=(
    payload.get('currency') == 'EUR'
    and payload.get('priceBasis') == 'gross'
    and payload.get('taxBasisPoints') == 1900
    and payload.get('market') == 'DE'
    and payload.get('maxQuantity') == 500
    and payload.get('checkoutEnabled') is True
    and payload.get('loginEnabled') is True
    and payload.get('proApplicationCount') == 34
    and len(names) == 34
    and len(set(names)) == 34
    and pro.get('monthlyGrossCents') == 299
    and pro.get('annualGrossCents') == 3588
    and pro.get('termMonths') == 12
    and pro.get('active') is True
    and pro.get('purchasable') is True
)
if not contract_ok:
    raise SystemExit(f"catalog contract drift via external Caddy: {payload}")
PY

log "Öffentlichen Checkout-API-Pfad und CSRF-Schutz über externes Proxy-Netz testen"
csrf_headers="$(mktemp)"
csrf_body="$(mktemp)"
trap 'rm -f "$csrf_headers" "$csrf_body"; cleanup' EXIT

docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
  -fsS -D - -H "Host: $domain" "http://$ALIAS/api/v1/checkout/csrf/" \
  >"$csrf_headers"

csrf_json="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -fsS -H "Host: $domain" "http://$ALIAS/api/v1/checkout/csrf/"
)"
csrf_token="$(python3 - "$csrf_json" <<'PY'
import json, sys
payload=json.loads(sys.argv[1])
print(payload.get('csrfToken') or '')
PY
)"
[[ -n "$csrf_token" ]] || {
  echo "Checkout CSRF endpoint returned no token through external Caddy" >&2
  exit 1
}

csrf_cookie="$(
  awk 'BEGIN{IGNORECASE=1}
       /^set-cookie: csrftoken=/{
         sub(/^set-cookie: csrftoken=/,"",$0);
         sub(/;.*/,"",$0);
         gsub(/\r/,"",$0);
         print $0;
         exit
       }' "$csrf_headers"
)"
# Some curl/Caddy combinations normalize header casing but preserve the same
# cookie contract. Fetch one deterministic header response if the first token
# request above did not expose it to awk.
if [[ -z "$csrf_cookie" ]]; then
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -sS -D "$csrf_headers" -o "$csrf_body" -H "Host: $domain" \
    "http://$ALIAS/api/v1/checkout/csrf/" >/dev/null
  csrf_cookie="$(
    sed -nE 's/^[Ss]et-[Cc]ookie: csrftoken=([^;]+).*/\1/p' "$csrf_headers" |
      tr -d '\r' | head -n1
  )"
fi
[[ -n "$csrf_cookie" ]] || {
  echo "Checkout CSRF cookie missing through external Caddy" >&2
  exit 1
}

without_csrf="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -sS -o /dev/null -w '%{http_code}' -X POST -H "Host: $domain" \
    --data 'quantity=1' "http://$ALIAS/api/v1/checkout/start/"
)"
[[ "$without_csrf" == "403" ]] || {
  echo "Checkout POST without CSRF should be 403, got $without_csrf" >&2
  exit 1
}

with_csrf_headers="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -sS -D - -o /dev/null -X POST -H "Host: $domain" \
    -H "X-CSRFToken: $csrf_token" \
    -H "Cookie: csrftoken=$csrf_cookie" \
    --data 'quantity=1' "http://$ALIAS/api/v1/checkout/start/"
)"
grep -qE '^HTTP/[0-9.]+ 302' <<<"$with_csrf_headers" || {
  echo "CSRF-valid checkout POST did not reach Django validation" >&2
  printf '%s\n' "$with_csrf_headers" >&2
  exit 1
}
grep -qiE '^location: /checkout/\?quantity=1(&|&)error=invalid' <<<"$with_csrf_headers" || {
  echo "CSRF-valid invalid checkout did not return the expected safe validation redirect" >&2
  printf '%s\n' "$with_csrf_headers" >&2
  exit 1
}

log "Current Free V2 cache-busting through external Caddy testen"
free_current="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -fsS -H "Host: $domain" "http://$ALIAS/free/"
)"
v2_css_url="$(
  grep -m1 -oE '/static/css/promptmaster_v2\.20260922\.css\?v=[^"[:space:]]+' <<<"$free_current"
)"
v2_js_url="$(
  grep -m1 -oE '/static/js/promptmaster_ui_v2\.20260922\.js\?v=[^"[:space:]]+' <<<"$free_current"
)"
[[ -n "$v2_css_url" ]] || {
  echo "Free V2 stylesheet is not cache-busted through external Caddy" >&2
  exit 1
}
[[ -n "$v2_js_url" ]] || {
  echo "Free V2 script is not cache-busted through external Caddy" >&2
  exit 1
}

mutable_headers="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -sS -D - -o /dev/null -H "Host: $domain" \
    "http://$ALIAS$v2_css_url"
)"
grep -qiE '^cache-control: .*no-cache.*must-revalidate' <<<"$mutable_headers" || {
  echo "Mutable V2 stylesheet still inherits immutable one-year cache" >&2
  printf '%s\n' "$mutable_headers" >&2
  exit 1
}

log "Legacy Free/Pro routes through external Caddy testen"
free_old="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -fsS -H "Host: $domain" "http://$ALIAS/free-old/"
)"
grep -q 'free_catalog_bridge.20260918.js' <<<"$free_old" || {
  echo "Free legacy route did not reach Django through external Caddy" >&2
  exit 1
}

pro_old_headers="$(
  docker run --rm --network "$NETWORK" curlimages/curl:8.12.1 \
    -sS -D - -o /dev/null -H "Host: $domain" "http://$ALIAS/pro-old/"
)"
grep -qE '^HTTP/[0-9.]+ 302' <<<"$pro_old_headers" || {
  echo "Pro legacy route did not preserve the Django authentication redirect" >&2
  printf '%s\n' "$pro_old_headers" >&2
  exit 1
}
grep -qiE '^location: .*/auth/login/' <<<"$pro_old_headers" || {
  echo "Pro legacy route redirect target is not the Django login route" >&2
  printf '%s\n' "$pro_old_headers" >&2
  exit 1
}

log "External-Caddy-Rehearsal OK"
