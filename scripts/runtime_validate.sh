#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; ARTIFACT_DIR="${PM_VALIDATION_ARTIFACT_DIR:-artifacts/runtime-validation}"; mkdir -p "$ARTIFACT_DIR"; LOG="$ARTIFACT_DIR/runtime-validation-${STAMP}.log"; exec > >(tee -a "$LOG") 2>&1
fail(){ echo "[FAIL] $*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "docker fehlt auf diesem Host"; docker compose version >/dev/null 2>&1 || fail "docker compose ist nicht verfügbar"; [[ -f .env ]] || fail ".env fehlt"
bash scripts/run_repo_preflight.sh staging
FILES=(-f compose.yaml -f compose.staging.yaml)
docker compose -f compose.yaml -f compose.production.yaml config >/dev/null
PM_EXTERNAL_CADDY_NETWORK=promptmaster-ci-external docker compose -f compose.yaml -f compose.production.yaml -f compose.external-caddy.yaml config >/dev/null
# Exercise production filesystem restrictions with safe staging integrations.
if [[ "${PM_VALIDATE_READ_ONLY:-0}" == 1 ]]; then FILES+=(-f compose.production.yaml); fi
docker compose "${FILES[@]}" config >/dev/null; docker compose "${FILES[@]}" build; docker compose "${FILES[@]}" up -d postgres redis mailpit
docker compose "${FILES[@]}" run --rm web python manage.py makemigrations --check --dry-run
docker compose "${FILES[@]}" run --rm web python manage.py check
docker compose "${FILES[@]}" run --rm web python manage.py migrate --plan
docker compose "${FILES[@]}" run --rm web python manage.py migrate --noinput
docker compose "${FILES[@]}" run --rm web python manage.py seed_defaults
docker compose "${FILES[@]}" run --rm web python manage.py seed_prompt_catalog
docker compose "${FILES[@]}" run --rm web python manage.py seed_faqs
docker compose "${FILES[@]}" run --rm web python manage.py validate_prompt_runtime
docker compose "${FILES[@]}" run --rm web python manage.py test --verbosity 2
docker compose "${FILES[@]}" run --rm -e ENVIRONMENT=production -e SECURE_SSL_REDIRECT=1 web python manage.py check --deploy
docker compose "${FILES[@]}" run --rm web python manage.py collectstatic --noinput
docker compose "${FILES[@]}" up -d
docker compose "${FILES[@]}" exec -T beat sh -c 'test -w /tmp/celerybeat && touch /tmp/celerybeat/write-test && rm /tmp/celerybeat/write-test'
for i in $(seq 1 30); do docker compose "${FILES[@]}" exec -T web curl -fsS http://127.0.0.1:8000/health/ready/ >/dev/null 2>&1 && break; [[ "$i" -lt 30 ]] || fail "Django ready health blieb rot"; sleep 2; done
docker compose "${FILES[@]}" exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null
docker compose "${FILES[@]}" exec -T caddy caddy validate --config /dev/stdin < Caddyfile.external >/dev/null
check_caddy_redirect(){
  local path="$1" expected="$2" headers
  headers="$(docker compose "${FILES[@]}" exec -T web sh -c "curl -skS --connect-to localhost:443:caddy:443 -D - -o /dev/null 'https://localhost${path}'" | tr -d '\r')"
  printf '%s\\n' "$headers" | grep -Eq '^HTTP/[0-9.]+ 302' || fail "Caddy redirect erwartet 302 für ${path}"
  printf '%s\\n' "$headers" | grep -Fqi "location: ${expected}" || { printf '%s\\n' "$headers"; fail "Caddy redirect falsch: ${path} -> erwartet ${expected}"; }
}
check_caddy_redirect '/login/' '/auth/login/'
check_caddy_redirect '/checkout/?quantity=3' '/portal/licenses/buy/?quantity=3'
check_caddy_redirect '/app/pro/' '/pro/'
check_caddy_redirect '/portal' '/portal/dashboard/'
check_caddy_redirect '/portal/' '/portal/dashboard/'
check_caddy_redirect '/datenschutz/' '/legal/privacy/'
check_caddy_redirect '/agb/' '/legal/terms/'
check_caddy_redirect '/lizenzbedingungen/' '/legal/license/'
check_caddy_redirect '/widerruf/' '/legal/withdrawal/'
echo "CADDY ROUTE CONTRACT OK: compatibility + legal redirects execute correctly"
check_caddy_status(){
  local path="$1" expected="$2" status
  status="$(docker compose "${FILES[@]}" exec -T web sh -c "curl -skS --connect-to localhost:443:caddy:443 -o /dev/null -w '%{http_code}' 'https://localhost${path}'")"
  [[ "$status" == "$expected" ]] || fail "Caddy Status ${path}: erwartet ${expected}, erhalten ${status}"
}
for path in '/.env' '/.git/config' '/Dockerfile' '/compose.yaml'; do
  check_caddy_status "$path" 404
done
echo "CADDY SENSITIVE-PATH CONTRACT OK: source/configuration probes return 404"
for i in $(seq 1 30); do
  MONITOR_OK="$(docker compose "${FILES[@]}" exec -T web sh -c "curl -fsS 'http://prometheus:9090/api/v1/targets?state=active' | python -c 'import json,sys; d=json.load(sys.stdin); rows=d.get(\"data\",{}).get(\"activeTargets\",[]); state={r.get(\"labels\",{}).get(\"job\"):r.get(\"health\") for r in rows}; required={\"node\",\"postgres\",\"cadvisor\",\"django\"}; print(\"1\" if required.issubset(state) and all(state[x]==\"up\" for x in required) else \"0\")'" 2>/dev/null | tail -n1 | tr -d '\r')"
  [[ "$MONITOR_OK" == 1 ]] && break
  [[ "$i" -lt 30 ]] || fail "Prometheus Monitoring-Targets (node/postgres/cadvisor/django) wurden nicht vollständig UP"
  sleep 2
done
# Runtime trust-boundary evidence: do not rely only on Compose source validation.
for spec in "cadvisor:8080" "prometheus:9090"; do
  service="${spec%%:*}"; port="${spec##*:}"
  published="$(docker compose "${FILES[@]}" port "$service" "$port" 2>/dev/null || true)"
  [[ -z "$published" ]] || fail "$service darf keinen veröffentlichten Host-Port besitzen: $published"
done
CADVISOR_ID="$(docker compose "${FILES[@]}" ps -q cadvisor)"
PROMETHEUS_ID="$(docker compose "${FILES[@]}" ps -q prometheus)"
[[ -n "$CADVISOR_ID" && -n "$PROMETHEUS_ID" ]] || fail "Monitoring-Container fehlen"
[[ "$(docker inspect -f '{{.HostConfig.Privileged}}' "$CADVISOR_ID")" == "true" ]] || fail "cAdvisor Trust-Boundary erwartet privileged=true"
CADVISOR_NETWORKS="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$CADVISOR_ID" | sed '/^$/d')"
PROMETHEUS_NETWORKS="$(docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$PROMETHEUS_ID" | sed '/^$/d')"
[[ "$(printf '%s\n' "$CADVISOR_NETWORKS" | wc -l | tr -d ' ')" == "1" && "$CADVISOR_NETWORKS" == *_monitor ]] || fail "cAdvisor läuft nicht ausschließlich im monitor-Netz: $CADVISOR_NETWORKS"
[[ "$(printf '%s\n' "$PROMETHEUS_NETWORKS" | wc -l | tr -d ' ')" == "1" && "$PROMETHEUS_NETWORKS" == *_monitor ]] || fail "Prometheus läuft nicht ausschließlich im monitor-Netz: $PROMETHEUS_NETWORKS"
RW_HOST_MOUNTS="$(docker inspect -f '{{range .Mounts}}{{if .RW}}{{println .Source "->" .Destination}}{{end}}{{end}}' "$CADVISOR_ID" | sed '/^$/d')"
[[ -z "$RW_HOST_MOUNTS" ]] || fail "cAdvisor besitzt unerwartete schreibbare Host-Mounts: $RW_HOST_MOUNTS"
echo "MONITOR TRUST BOUNDARY OK: internal-only ports/network, cAdvisor privileged, mounts read-only"
docker compose "${FILES[@]}" exec -T caddy sh -c "test -s /srv/marketing/index.html && test -s /srv/marketing/models/head.glb && test -s /srv/marketing/integration-patch.js" || fail "Marketing-Artefakte fehlen im Caddy-Container"
docker compose "${FILES[@]}" exec -T web sh -c "curl -fsS http://127.0.0.1:8000/catalog.json | python -c 'import json,sys; d=json.load(sys.stdin); assert d[\"proApplicationCount\"]==34; p=next(x for x in d[\"products\"] if x[\"id\"]==\"PROMPTMASTER_PRO\"); assert p[\"annualGrossCents\"]==3588'" || fail "Öffentlicher Marketing-Katalog ist nicht synchron"
docker compose "${FILES[@]}" exec -T web python manage.py shell -c "from apps.prompts.models import PromptApplication,PromptDefinition,PromptLegacyContract; a=PromptApplication.objects.filter(active=True).count(); t=PromptDefinition.objects.filter(active=True).count(); f=PromptLegacyContract.objects.filter(source='FREE_1_2_4').count(); print(f'PROMPT_DOMAIN:{a}:{t}:{f}'); raise SystemExit(0 if (a,t,f)==(34,194,16) else 1)"
# Consume the full CLI output: grep -q can close the pipe early and make
# Celery fail with SIGPIPE under pipefail even after a successful pong.
for i in $(seq 1 10); do
  WORKER_REPLY="$(docker compose "${FILES[@]}" exec -T web celery -A config inspect ping --timeout 3 2>&1)" && [[ "$WORKER_REPLY" == *pong* ]] && break
  [[ "$i" -lt 10 ]] || { printf '%s\n' "$WORKER_REPLY"; fail "Kein Celery Worker antwortet"; }
  sleep 2
done
for i in $(seq 1 20); do BEAT_OK="$(docker compose "${FILES[@]}" exec -T web python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from apps.ops.models import BeatHeartbeat; h=BeatHeartbeat.objects.filter(name='default').first(); print('1' if h and h.last_seen_at >= timezone.now()-timedelta(minutes=3) else '0')" 2>/dev/null | tail -n1 | tr -d '\r')"; [[ "$BEAT_OK" == 1 ]] && break; [[ "$i" -lt 20 ]] || fail "Celery Beat-Heartbeat blieb rot"; sleep 5; done
docker compose "${FILES[@]}" ps
docker compose "${FILES[@]}" exec -T web python manage.py shell -c "from pathlib import Path; import hashlib; from django.conf import settings; p=Path(settings.PRO_GOLDEN_MASTER_PATH); expected='aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf'; actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ''; print('PRO_GOLDEN_MASTER_OK' if actual==expected else f'PRO_GOLDEN_MASTER_FAIL:{actual}'); raise SystemExit(0 if actual==expected else 1)"
for i in $(seq 1 40); do
  BACKUP_OK="$(docker compose "${FILES[@]}" exec -T web python -c "import json,pathlib; p=pathlib.Path('/var/run/promptmaster-backup/last-backup.json'); print('1' if p.is_file() and json.loads(p.read_text()).get('status')=='ok' else '0')" 2>/dev/null | tail -n1 | tr -d '\r')"
  [[ "$BACKUP_OK" == 1 ]] && break
  [[ "$i" -lt 40 ]] || fail "Staging-Backup blieb rot"
  sleep 3
done
for i in $(seq 1 40); do
  RESTORE_OK="$(docker compose "${FILES[@]}" exec -T web python -c "import json,pathlib; p=pathlib.Path('/var/run/promptmaster-backup/last-restore.json'); print('1' if p.is_file() and json.loads(p.read_text()).get('status')=='ok' else '0')" 2>/dev/null | tail -n1 | tr -d '\r')"
  [[ "$RESTORE_OK" == 1 ]] && break
  [[ "$i" -lt 40 ]] || fail "Staging-Restore-Test blieb rot"
  sleep 3
done
echo "RUNTIME VALIDATION OK"; echo "Log: $LOG"
