from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.audit.services import audit

from .exporting import EXPORTS
from .models import ExportJob
from .permissions import has_perm


def _authorized_job(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied
    job = get_object_or_404(ExportJob.objects.select_related('requested_by'), pk=pk)
    config = EXPORTS.get(job.kind)
    if not config or not has_perm(request.user, config['permission']):
        raise PermissionDenied
    if job.requested_by_id != request.user.id and not request.user.is_superuser:
        raise PermissionDenied
    return job


@login_required
def export_status(request, pk):
    job = _authorized_job(request, pk)
    return render(
        request,
        'ns_admin/export_status.html',
        {
            'job': job,
            'expired': job.expires_at <= timezone.now(),
        },
    )


@login_required
def export_download(request, pk):
    job = _authorized_job(request, pk)
    if job.status != 'ready' or not job.file_name or job.expires_at <= timezone.now():
        raise Http404
    root = Path(getattr(settings, 'EXPORT_ROOT', '/app/exports')).resolve()
    path = (root / job.file_name).resolve()
    if path.parent != root or not path.is_file():
        raise Http404
    audit(request.user, 'export.downloaded', job, {'kind': job.kind, 'row_count': job.row_count}, request=request)
    response = FileResponse(path.open('rb'), as_attachment=True, filename=job.filename, content_type='text/csv; charset=utf-8')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
