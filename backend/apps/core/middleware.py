import re
import uuid

_CORRELATION_ID_RE = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = (request.headers.get('X-Correlation-ID') or '').strip()
        cid = supplied if _CORRELATION_ID_RE.fullmatch(supplied) else str(uuid.uuid4())
        request.correlation_id = cid
        response = self.get_response(request)
        response['X-Correlation-ID'] = cid
        return response
