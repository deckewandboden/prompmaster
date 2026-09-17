import csv
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


def _export_root():
    root = Path(getattr(settings, 'EXPORT_ROOT', '/app/exports')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_grid_export(self, job_id):
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().select_related('requested_by').get(pk=job_id)
        now = timezone.now()
        if job.status == 'ready':
            return {'job_id': str(job.id), 'status': 'ready', 'rows': job.row_count}
        if job.expires_at <= now:
            job.status = 'failed'
            job.error = 'Exportauftrag ist abgelaufen.'
            job.finished_at = now
            job.save(update_fields=['status', 'error', 'finished_at', 'updated_at'])
            return {'job_id': str(job.id), 'status': 'expired'}
        # Duplicate deliveries can happen when the broker reconnects or the
        # recovery dispatcher sees a just-started job. Only one fresh worker
        # may generate a file. Stale running jobs are deliberately recoverable.
        if job.status == 'running' and job.updated_at >= now - RUNNING_STALE_AFTER:
            return {'job_id': str(job.id), 'status': 'already_running'}
        job.status = 'running'
        job.error = ''
        job.finished_at = None
        job.save(update_fields=['status', 'error', 'finished_at', 'updated_at'])

    target = _export_root() / f'{job.id}.csv'
    try:
        state = decode_query_state(job.query_state_enc)
        queryset = export_queryset(job.kind, state)
        columns = EXPORTS[job.kind]['columns']
        rows = 0
        with target.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle, delimiter=';', quoting=csv.QUOTE_MINIMAL)
            writer.writerow([label for _, label in columns])
            for row in queryset.iterator(chunk_size=2000):
                writer.writerow([csv_value(row, path) for path, _label in columns])
                rows += 1

        job.status = 'ready'
        job.file_name = target.name
        job.row_count = rows
        job.finished_at = timezone.now()
        job.error = ''
        job.save(update_fields=['status', 'file_name', 'row_count', 'finished_at', 'error', 'updated_at'])
        audit(job.requested_by, 'export.ready', job, {'kind': job.kind, 'row_count': rows})
        return {'job_id': str(job.id), 'status': 'ready', 'rows': rows}
    except Exception as exc:
        target.unlink(missing_ok=True)
        job.status = 'failed'
        job.error = f'{exc.__class__.__name__}: Export konnte nicht erstellt werden.'[:500]
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error', 'finished_at', 'updated_at'])
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        audit(job.requested_by, 'export.failed', job, {'kind': job.kind})
        raise


@shared_task
def dispatch_pending_exports():
    """Recover queued jobs and stale running jobs after broker/worker outages."""
    now = timezone.now()
    stale_before = now - RUNNING_STALE_AFTER
    candidates = list(
        ExportJob.objects.filter(expires_at__gt=now)
        .filter(status='queued')
        .values_list('id', flat=True)[:100]
    )
    stale = list(
        ExportJob.objects.filter(status='running', expires_at__gt=now, updated_at__lt=stale_before)
        .values_list('id', flat=True)[:100]
    )
    job_ids = list(dict.fromkeys([*candidates, *stale]))
    if stale:
        ExportJob.objects.filter(id__in=stale, status='running', updated_at__lt=stale_before).update(
            status='queued', error='', finished_at=None, updated_at=now
        )
    dispatched = 0
    for job_id in job_ids:
        generate_grid_export.delay(str(job_id))
        dispatched += 1
    return dispatched


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
        job.delete()
        removed += 1
    return removed
