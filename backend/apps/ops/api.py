import json
from datetime import timedelta
import os
import platform
from pathlib import Path

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

from apps.notifications.models import EmailMessage
from apps.payments.models import MollieEvent
from .auth import service_account
from .metrics import caddy_health, celery_worker_status, certificate_status, prometheus_targets, snapshot
from .models import BeatHeartbeat, RestoreTest, TaskFailure, WorkerHeartbeat

BACKUP_STATUS = Path('/var/run/promptmaster-backup/last-backup.json')


def _json(payload, status=200):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def _guard(request):
    if request.method != 'GET':
        return None, _json({'detail': 'method_not_allowed'}, 405)
    account = service_account(request, 'ops.read')
    if not account:
        return None, _json({'detail': 'unauthorized'}, 401)
    return account, None


def _database_payload(safe=False):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                'select version(), pg_database_size(current_database()), '
                'count(*) from pg_stat_activity where datname=current_database()'
            )
            version, size, connections = cursor.fetchone()
        return {'status': 'ok', 'version': version, 'size_bytes': size, 'connections': connections}
    except Exception as exc:
        if not safe:
            raise
        return {'status': 'unavailable', 'error': exc.__class__.__name__}


def _backup_payload():
    try:
        return json.loads(BACKUP_STATUS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'status': 'unavailable'}


def _queue_depth():
    try:
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        return int(client.llen('celery'))
    except Exception:
        return None


def _service_payload():
    from django.core.cache import cache

    try:
        cache.set('ops:health', 'ok', 5)
        redis_ok = cache.get('ops:health') == 'ok'
    except Exception:
        redis_ok = False
    database_payload = _database_payload(safe=True)
    heartbeat = WorkerHeartbeat.objects.filter(name='default').first()
    beat = BeatHeartbeat.objects.filter(name='default').first()
    worker_state = celery_worker_status()
    worker_ok = bool(worker_state.get('ok'))
    beat_ok = bool(beat and beat.last_seen_at >= timezone.now() - timedelta(minutes=3))
    failures_24h = TaskFailure.objects.filter(
        resolved_at__isnull=True,
        failed_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    return {
        'django': True,
        'database': database_payload.get('status') == 'ok',
        'redis': redis_ok,
        'caddy': caddy_health(),
        'worker': worker_ok,
        'worker_names': worker_state.get('workers', []),
        'worker_last_seen_at': heartbeat.last_seen_at.isoformat() if heartbeat else None,
        'beat': beat_ok,
        'beat_last_seen_at': beat.last_seen_at.isoformat() if beat else None,
        'queue_depth': _queue_depth(),
        'failed_jobs_24h': failures_24h,
        'prometheus_targets': prometheus_targets(),
        'mcp': _mcp_payload(),
    }



def _mcp_payload():
    try:
        from apps.prompts.models import PromptDefinition, PromptVersion
        definitions = PromptDefinition.objects.filter(active=True).count()
        published = PromptVersion.objects.filter(lifecycle='PUBLISHED').count()
        ok = definitions == 194 and published >= 194
        return {
            'status': 'ok' if ok else 'degraded',
            'transport': 'streamable-http',
            'endpoint': '/api/v1/mcp/',
            'health_endpoint': '/api/v1/mcp/health/',
            'definitions': definitions,
            'published_versions': published,
            'tools': ['prompt.read', 'prompt.draft', 'prompt.test'],
            'publish_tool': False,
            'delete_tool': False,
        }
    except Exception as exc:
        return {'status': 'unavailable', 'error': exc.__class__.__name__}

def _integration_payload():
    from apps.integrations.services import get_secret

    mollie_configured = bool(get_secret('mollie_api_key', settings.MOLLIE_API_KEY))
    mail_configured = bool(settings.EMAIL_PROVIDER == 'smtp' or (
        settings.GRAPH_TENANT_ID and settings.GRAPH_CLIENT_ID and settings.GRAPH_SENDER
    ))
    hostname = settings.CADDY_DOMAIN.split(':', 1)[0] if settings.CADDY_DOMAIN else ''
    return {
        'mollie': {
            'configured': mollie_configured,
            'failures_24h': MollieEvent.objects.filter(
                error__gt='', created_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
        },
        'mail': {
            'provider': settings.EMAIL_PROVIDER,
            'configured': mail_configured,
            'failures_24h': EmailMessage.objects.filter(
                status='failed', created_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
        },
        'certificate': certificate_status(hostname),
        'mcp': _mcp_payload(),
    }


def health(request):
    _, denied = _guard(request)
    if denied:
        return denied
    return _json({'status': 'ok', 'timestamp': timezone.now().isoformat()})


def system(request):
    _, denied = _guard(request)
    if denied:
        return denied
    return _json({
        'metrics': snapshot(),
        'python': platform.python_version(),
        'django': __import__('django').get_version(),
        'app_version': settings.APP_VERSION,
        'git_sha': settings.GIT_SHA,
    })


def storage(request):
    _, denied = _guard(request)
    if denied:
        return denied
    data = snapshot()
    keys = ['disk_total', 'disk_used', 'disk_available', 'disk_percent', 'inodes_total', 'inodes_free', 'inode_percent']
    return _json({key: data.get(key) for key in keys})


def database(request):
    _, denied = _guard(request)
    if denied:
        return denied
    return _json(_database_payload(safe=True))


def backups(request):
    _, denied = _guard(request)
    if denied:
        return denied
    restore = RestoreTest.objects.order_by('-started_at').first()
    return _json({
        'backup': _backup_payload(),
        'last_restore_test': {
            'status': restore.status,
            'started_at': restore.started_at.isoformat(),
            'finished_at': restore.finished_at.isoformat() if restore.finished_at else None,
        } if restore else None,
    })


def services(request):
    _, denied = _guard(request)
    if denied:
        return denied
    return _json(_service_payload())


def integrations(request):
    _, denied = _guard(request)
    if denied:
        return denied
    return _json(_integration_payload())


def maintenance_snapshot(request):
    account, denied = _guard(request)
    if denied:
        return denied
    return _json({
        'schema_version': 1,
        'timestamp': timezone.now().isoformat(),
        'service_account': str(account.id),
        'app_version': settings.APP_VERSION,
        'git_sha': settings.GIT_SHA,
        'system': snapshot(),
        'database': _database_payload(safe=True),
        'backup': _backup_payload(),
        'last_restore_test': _restore_payload(),
        'services': _service_payload(),
        'integrations': _integration_payload(),
    })


def _restore_payload():
    restore = RestoreTest.objects.order_by('-started_at').first()
    if not restore:
        return None
    return {
        'status': restore.status,
        'started_at': restore.started_at.isoformat(),
        'finished_at': restore.finished_at.isoformat() if restore.finished_at else None,
        'backup_ref': restore.backup_ref,
    }
