import contextvars
import json
import logging
import re
import uuid
from datetime import datetime, timezone

_CORRELATION_ID_RE = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')
_CORRELATION_ID = contextvars.ContextVar('promptmaster_correlation_id', default='')
_USER_ID = contextvars.ContextVar('promptmaster_user_id', default='')


class JsonLogFormatter(logging.Formatter):
    """Emit one valid JSON object per log record.

    Request-scoped identifiers are supplied through context variables so
    application and library loggers do not need the Django request object.
    Explicit record attributes still take precedence.
    """

    def format(self, record):
        correlation_id = getattr(record, 'correlation_id', '') or _CORRELATION_ID.get()
        user_id = getattr(record, 'user_id', '') or _USER_ID.get()
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'service': record.name,
            'message': record.getMessage(),
            'correlation_id': str(correlation_id or ''),
            'user_id': str(user_id or ''),
            'event_code': str(getattr(record, 'event_code', '') or ''),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = (request.headers.get('X-Correlation-ID') or '').strip()
        cid = supplied if _CORRELATION_ID_RE.fullmatch(supplied) else str(uuid.uuid4())
        request.correlation_id = cid
        user = getattr(request, 'user', None)
        uid = str(user.pk) if getattr(user, 'is_authenticated', False) else ''

        correlation_token = _CORRELATION_ID.set(cid)
        user_token = _USER_ID.set(uid)
        try:
            response = self.get_response(request)
        finally:
            _CORRELATION_ID.reset(correlation_token)
            _USER_ID.reset(user_token)

        response['X-Correlation-ID'] = cid
        return response


class LargeExportMiddleware:
    """Move large netstyle CSV exports off the request worker into Celery.

    The size decision happens before the view executes. This prevents a large
    export from first creating a synchronous export audit/event and only then
    being replaced by a background job.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != 'GET' or request.GET.get('export') != 'csv':
            return self.get_response(request)

        from datetime import timedelta
        from django.conf import settings
        from django.contrib import messages
        from django.db import transaction
        from django.shortcuts import redirect
        from django.urls import resolve, Resolver404
        from django.utils import timezone as django_timezone

        from apps.audit.services import audit
        from .exporting import EXPORTS, URL_NAME_TO_KIND, capture_query_state, decode_query_state, export_queryset
        from .models import ExportJob
        from .permissions import has_perm

        match = getattr(request, 'resolver_match', None)
        if not match:
            try:
                match = resolve(request.path_info)
            except Resolver404:
                return self.get_response(request)

        kind = URL_NAME_TO_KIND.get(match.url_name)
        config = EXPORTS.get(kind)
        user = getattr(request, 'user', None)
        if not config or not getattr(user, 'is_authenticated', False) or not user.is_staff:
            return self.get_response(request)
        if not has_perm(user, config['permission']):
            return self.get_response(request)

        query_state_enc = capture_query_state(request.GET)
        state = decode_query_state(query_state_enc)
        row_count = export_queryset(kind, state).count()
        threshold = max(1, int(getattr(settings, 'EXPORT_SYNC_LIMIT', 5000)))
        if row_count <= threshold:
            return self.get_response(request)

        ttl_hours = max(1, int(getattr(settings, 'EXPORT_TTL_HOURS', 24)))
        job = ExportJob.objects.create(
            requested_by=user,
            kind=kind,
            filename=config['filename'],
            query_state_enc=query_state_enc,
            expires_at=django_timezone.now() + timedelta(hours=ttl_hours),
        )
        from .tasks import generate_grid_export

        transaction.on_commit(
            lambda job_id=str(job.id): generate_grid_export.delay(job_id),
            robust=True,
        )
        audit(user, 'export.queued', job, {'kind': kind, 'row_count': row_count}, request=request)
        messages.info(request, f'Der Export enthält {row_count} Zeilen und wird im Hintergrund erstellt.')
        return redirect('ns_admin:export_status', pk=job.pk)
