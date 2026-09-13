#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; ARTIFACT_DIR="${PM_VALIDATION_ARTIFACT_DIR:-artifacts/runtime-validation}"; mkdir -p "$ARTIFACT_DIR"; LOG="$ARTIFACT_DIR/runtime-validation-${STAMP}.log"; exec > >(tee -a "$LOG") 2>&1
fail(){ echo "[FAIL] $*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail "docker fehlt auf diesem Host"; docker compose version >/dev/null 2>&1 || fail "docker compose ist nicht verfügbar"; [[ -f .env ]] || fail ".env fehlt"
python3 scripts/github_preflight.py; python3 scripts/validate_env.py --environment staging
FILES=(-f compose.yaml -f compose.staging.yaml)
docker compose -f compose.yaml -f compose.production.yaml config >/dev/null
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
docker compose "${FILES[@]}" run --rm web python manage.py check --deploy
docker compose "${FILES[@]}" run --rm web python manage.py collectstatic --noinput
docker compose "${FILES[@]}" up -d
docker compose "${FILES[@]}" exec -T beat sh -c 'test -w /tmp/celerybeat && touch /tmp/celerybeat/write-test && rm /tmp/celerybeat/write-test'
for i in $(seq 1 30); do docker compose "${FILES[@]}" exec -T web curl -fsS http://127.0.0.1:8000/health/ready/ >/dev/null 2>&1 && break; [[ "$i" -lt 30 ]] || fail "Django ready health blieb rot"; sleep 2; done
docker compose "${FILES[@]}" exec -T caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null
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
