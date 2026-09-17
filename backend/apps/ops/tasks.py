import json
import socket
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

import redis
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.notifications.models import EmailMessage
from apps.payments.models import MollieEvent
from .metrics import caddy_health, celery_worker_status, prometheus_targets, snapshot
from .models import BackupRecord, BeatHeartbeat, RestoreTest, SystemAlert, TaskFailure, WorkerHeartbeat

BACKUP_STATUS = Path('/var/run/promptmaster-backup/last-backup.json')
RESTORE_STATUS = Path('/var/run/promptmaster-backup/last-restore.json')
MANAGED_PREFIXES = (
    'disk.', 'ram.', 'cpu.', 'backup.', 'restore.', 'mail.', 'mollie.',
    'service.', 'worker.', 'beat.', 'queue.', 'task.',
)


def _thresholds():
    return get_setting(
        'ops_thresholds',
        {
            'disk_warning': 80,
            'disk_critical': 90,
            'ram_warning': 80,
            'ram_critical': 90,
            'cpu_warning': 80,
            'backup_warning_hours': 8,
            'backup_critical_hours': 24,
            'restore_warning_days': 35,
            'worker_warning_minutes': 3,
            'beat_warning_minutes': 3,
            'queue_warning': 100,
        },
    )


def _parse_status_time(value):
    try:
        return datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=dt_timezone.utc)
    except (TypeError, ValueError):
        return None


def _read_status_payload(path):
    """Return a dict status payload or None for any malformed/unreadable input."""
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _nonnegative_int(value):
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0, parsed)


def _backup_state():
    payload = _read_status_payload(BACKUP_STATUS)
    if payload is None:
        return None
    timestamp = payload.get('timestamp')
    finished = _parse_status_time(timestamp)
    size_bytes = _nonnegative_int(payload.get('size_bytes'))
    if size_bytes is None:
        return None
    status = payload.get('status', 'unknown')
    if not isinstance(status, str):
        return None
    if finished and not BackupRecord.objects.filter(provider_ref=timestamp).exists():
        BackupRecord.objects.create(
            status=status[:30],
            provider_ref=str(timestamp)[:200],
            size_bytes=size_bytes,
            finished_at=finished,
        )
    return {'payload': payload, 'finished_at': finished}


def _restore_state():
    payload = _read_status_payload(RESTORE_STATUS)
    if payload is None:
        return None
    started = _parse_status_time(payload.get('started_at'))
    finished = _parse_status_time(payload.get('finished_at'))
    raw_status = payload.get('status', 'unknown')
    raw_backup_ref = payload.get('backup_ref', '')
    if not isinstance(raw_status, str) or not isinstance(raw_backup_ref, (str, int, float)):
        return None
    backup_ref = str(raw_backup_ref)[:200]
    if started and not RestoreTest.objects.filter(started_at=started, backup_ref=backup_ref).exists():
        RestoreTest.objects.create(
            status=raw_status[:30],
            backup_ref=backup_ref,
            started_at=started,
            finished_at=finished,
            details={'detail': str(payload.get('detail') or '')[:1000]},
        )
    return {'payload': payload, 'started_at': started, 'finished_at': finished}


def _queue_depth():
    try:
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        return int(client.llen('celery'))
    except Exception:
        return None


@shared_task(name='apps.ops.tasks.worker_heartbeat')
def worker_heartbeat():
    now = timezone.now()
    WorkerHeartbeat.objects.update_or_create(
        name='default',
        defaults={'last_seen_at': now, 'hostname': socket.gethostname()[:200]},
    )
    return now.isoformat()


@shared_task(name='apps.ops.tasks.beat_heartbeat')
def beat_heartbeat():
    """Freshness proves Beat dispatch plus worker execution."""
    now = timezone.now()
    BeatHeartbeat.objects.update_or_create(
        name='default',
        defaults={'last_seen_at': now, 'hostname': socket.gethostname()[:200]},
    )
    return now.isoformat()


@shared_task
def refresh_alerts():
    metrics = snapshot()
    thresholds = _thresholds()
    active = []

    disk = metrics.get('disk_percent')
    if disk is not None:
        if disk >= thresholds['disk_critical']:
            active.append(('disk.critical', 'critical', f'Disk {disk:.1f}% belegt'))
        elif disk >= thresholds['disk_warning']:
            active.append(('disk.warning', 'warning', f'Disk {disk:.1f}% belegt'))

    ram = metrics.get('memory_percent')
    if ram is not None:
        if ram >= thresholds['ram_critical']:
            active.append(('ram.critical', 'critical', f'RAM {ram:.1f}% belegt'))
        elif ram >= thresholds['ram_warning']:
            active.append(('ram.warning', 'warning', f'RAM {ram:.1f}% belegt'))

    cpu = metrics.get('cpu_percent')
    if cpu is not None and cpu >= thresholds['cpu_warning']:
        active.append(('cpu.warning', 'warning', f'CPU 10-Minuten-Mittel {cpu:.1f}%'))

    backup = _backup_state()
    if not backup or not backup['finished_at']:
        active.append(('backup.unavailable', 'critical', 'Kein auswertbarer Backupstatus verfügbar'))
    else:
        age_hours = (timezone.now() - backup['finished_at']).total_seconds() / 3600
        status = backup['payload'].get('status')
        if status != 'ok':
            active.append(('backup.failed', 'critical', f'Letztes Backup meldet Status {status}'))
        elif age_hours >= thresholds['backup_critical_hours']:
            active.append(('backup.critical', 'critical', f'Backup ist {age_hours:.1f} Stunden alt'))
        elif age_hours >= thresholds['backup_warning_hours']:
            active.append(('backup.warning', 'warning', f'Backup ist {age_hours:.1f} Stunden alt'))

    restore_state = _restore_state()
    restore = RestoreTest.objects.order_by('-started_at').first()
    if restore_state is None and RESTORE_STATUS.exists():
        active.append(('restore.unavailable', 'warning', 'Restore-Statusdatei ist nicht auswertbar'))
    if not restore:
        active.append(('restore.missing', 'warning', 'Noch kein Restore-Test protokolliert'))
    else:
        age_days = (timezone.now() - restore.started_at).days
        if restore.status != 'ok':
            active.append(('restore.failed', 'critical', 'Letzter Restore-Test war nicht erfolgreich'))
        elif age_days > thresholds['restore_warning_days']:
            active.append(('restore.old', 'warning', f'Letzter Restore-Test ist {age_days} Tage alt'))

    for job, up in prometheus_targets().items():
        if up is False:
            active.append((f'service.{job}.down', 'critical', f'Monitoring-Ziel {job} ist nicht erreichbar'))
        elif up is None:
            active.append((f'service.{job}.unknown', 'warning', f'Monitoring-Ziel {job} liefert keinen Status'))
    if not caddy_health():
        active.append(('service.caddy.down', 'critical', 'Caddy Healthcheck ist nicht erreichbar'))

    worker_state = celery_worker_status()
    if not worker_state.get('ok'):
        active.append(('worker.ping', 'critical', 'Kein Celery Worker beantwortet den aktiven Ping'))

    beat = BeatHeartbeat.objects.filter(name='default').first()
    beat_minutes = thresholds.get('beat_warning_minutes', 3)
    if not beat or beat.last_seen_at < timezone.now() - timedelta(minutes=beat_minutes):
        active.append(('beat.heartbeat', 'critical', f'Celery Beat-Heartbeat älter als {beat_minutes} Minuten'))

    depth = _queue_depth()
    if depth is None:
        active.append(('queue.unavailable', 'warning', 'Celery Queue-Tiefe kann nicht gelesen werden'))
    elif depth >= thresholds.get('queue_warning', 100):
        active.append(('queue.backlog', 'warning', f'Celery Queue enthält {depth} wartende Jobs'))

    failed_tasks = TaskFailure.objects.filter(
        resolved_at__isnull=True,
        failed_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    if failed_tasks:
        active.append(('task.failures', 'warning', f'{failed_tasks} fehlgeschlagene Hintergrundjobs in 24 Stunden'))

    mail_failures = EmailMessage.objects.filter(
        status='failed', created_at__gte=timezone.now() - timedelta(hours=24)
    ).count()
    if mail_failures:
        active.append(('mail.failures', 'warning', f'{mail_failures} E-Mail-Fehler in 24 Stunden'))

    mollie_failures = MollieEvent.objects.filter(
        error__gt='', created_at__gte=timezone.now() - timedelta(hours=24)
    ).count()
    if mollie_failures:
        active.append(('mollie.failures', 'warning', f'{mollie_failures} Mollie-Verarbeitungsfehler in 24 Stunden'))

    active_codes = {item[0] for item in active}
    managed = SystemAlert.objects.filter(active=True)
    for alert in managed:
        if any(alert.code.startswith(prefix) for prefix in MANAGED_PREFIXES) and alert.code not in active_codes:
            alert.active = False
            alert.resolved_at = timezone.now()
            alert.save(update_fields=['active', 'resolved_at', 'updated_at'])

    for code, severity, message in active:
        alert = SystemAlert.objects.filter(code=code, active=True).first()
        if alert:
            if alert.severity != severity or alert.message != message:
                alert.severity = severity
                alert.message = message
                alert.save(update_fields=['severity', 'message', 'updated_at'])
        else:
            SystemAlert.objects.create(code=code, severity=severity, message=message, active=True)
    return active
