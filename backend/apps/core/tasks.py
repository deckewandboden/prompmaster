import csv
import uuid
from datetime import timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import audit

from .exporting import EXPORTS, csv_value, decode_query_state, export_queryset
from .models import ExportJob


RUNNING_STALE_AFTER = timedelta(minutes=10)
LEASE_HEARTBEAT_ROWS = 1000


def _export_root():
    root = Path(getattr(settings, 'EXPORT_ROOT', '/app/exports')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _touch_lease(job_id, run_token):
    return bool(
        ExportJob.objects.filter(
            pk=job_id,
            status='running',
            run_token=run_token,
        ).update(updated_at=timezone.now())
    )


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_grid_export(self, job_id):
    run_token = uuid.uuid4()
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().select_related('requested_by').get(pk=job_id)
        now = timezone.now()
        if job.status == 'ready':
            return {'job_id': str(job.id), 'status': 'ready', 'rows': job.row_count}
        if job.expires_at <= now:
            job.status = 'failed'
            job.error = 'Exportauftrag ist abgelaufen.'
            job.finished_at = now
            job.run_token = None
            job.save(update_fields=['status', 'error', 'finished_at', 'run_token', 'updated_at'])
            return {'job_id': str(job.id), 'status': 'expired'}
        if job.status == 'running' and job.updated_at >= now - RUNNING_STALE_AFTER:
            return {'job_id': str(job.id), 'status': 'already_running'}
        job.status = 'running'
        job.error = ''
        job.finished_at = None
        job.run_token = run_token
        job.save(update_fields=['status', 'error', 'finished_at', 'run_token', 'updated_at'])

    root = _export_root()
    target = root / f'{job.id}.csv'
    temporary = root / f'{job.id}.{run_token}.tmp'
    try:
        state = decode_query_state(job.query_state_enc)
        queryset = export_queryset(job.kind, state)
        columns = EXPORTS[job.kind]['columns']
        rows = 0
        with temporary.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle, delimiter=';', quoting=csv.QUOTE_MINIMAL)
            writer.writerow([label for _, label in columns])
            for row in queryset.iterator(chunk_size=2000):
                writer.writerow([csv_value(row, path) for path, _label in columns])
                rows += 1
                if rows % LEASE_HEARTBEAT_ROWS == 0 and not _touch_lease(job.id, run_token):
                    temporary.unlink(missing_ok=True)
                    return {'job_id': str(job.id), 'status': 'superseded'}

        with transaction.atomic():
            current = ExportJob.objects.select_for_update().select_related('requested_by').get(pk=job.id)
            now = timezone.now()
            if current.status != 'running' or current.run_token != run_token:
                temporary.unlink(missing_ok=True)
                return {'job_id': str(job.id), 'status': 'superseded'}
            if current.expires_at <= now:
                temporary.unlink(missing_ok=True)
                current.status = 'failed'
                current.error = 'Exportauftrag ist während der Erstellung abgelaufen.'
                current.finished_at = now
                current.run_token = None
                current.save(update_fields=['status', 'error', 'finished_at', 'run_token', 'updated_at'])
                return {'job_id': str(job.id), 'status': 'expired'}

            temporary.replace(target)
            current.status = 'ready'
            current.file_name = target.name
            current.row_count = rows
            current.finished_at = now
            current.error = ''
            current.run_token = None
            current.save(
                update_fields=[
                    'status', 'file_name', 'row_count', 'finished_at',
                    'error', 'run_token', 'updated_at',
                ]
            )

        audit(current.requested_by, 'export.ready', current, {'kind': current.kind, 'row_count': rows})
        return {'job_id': str(current.id), 'status': 'ready', 'rows': rows}
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        owns_lease = False
        failed_job = None
        with transaction.atomic():
            current = ExportJob.objects.select_for_update().select_related('requested_by').get(pk=job.id)
            owns_lease = current.status == 'running' and current.run_token == run_token
            if owns_lease:
                current.status = 'failed'
                current.error = f'{exc.__class__.__name__}: Export konnte nicht erstellt werden.'[:500]
                current.finished_at = timezone.now()
                current.run_token = None
                current.save(update_fields=['status', 'error', 'finished_at', 'run_token', 'updated_at'])
                failed_job = current
        if not owns_lease:
            return {'job_id': str(job.id), 'status': 'superseded'}
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        audit(failed_job.requested_by, 'export.failed', failed_job, {'kind': failed_job.kind})
        raise


@shared_task
def dispatch_pending_exports():
    now = timezone.now()
    stale_before = now - RUNNING_STALE_AFTER
    queued = list(
        ExportJob.objects.filter(status='queued', expires_at__gt=now)
        .values_list('id', flat=True)[:100]
    )
    stale = list(
        ExportJob.objects.filter(status='running', expires_at__gt=now, updated_at__lt=stale_before)
        .values_list('id', flat=True)[:100]
    )
    if stale:
        ExportJob.objects.filter(
            id__in=stale,
            status='running',
            updated_at__lt=stale_before,
        ).update(
            status='queued', run_token=None, error='', finished_at=None, updated_at=now
        )
    job_ids = list(dict.fromkeys([*queued, *stale]))
    for job_id in job_ids:
        generate_grid_export.delay(str(job_id))
    return len(job_ids)


@shared_task
def cleanup_expired_exports():
    now = timezone.now()
    root = _export_root()
    removed = 0
    for job in ExportJob.objects.filter(expires_at__lte=now).iterator(chunk_size=500):
        if job.file_name:
            candidate = (root / job.file_name).resolve()
            if candidate.parent == root:
                candidate.unlink(missing_ok=True)
        for temporary in root.glob(f'{job.id}.*.tmp'):
            if temporary.resolve().parent == root:
                temporary.unlink(missing_ok=True)
        job.delete()
        removed += 1
    return removed
