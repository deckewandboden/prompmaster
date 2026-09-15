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
