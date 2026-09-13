import hashlib
import ipaddress
import secrets

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429


def token_pair(bytes_len=32):
    raw = secrets.token_urlsafe(bytes_len)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def token_hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def client_ip(request):
    """Return the canonical client IP when Django is reachable only via Caddy.

    Caddy appends/sets X-Forwarded-For. We intentionally use the right-most
    valid address so a client-supplied left-most spoof cannot bypass per-IP
    throttling. Direct internal requests fall back to REMOTE_ADDR.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    candidates = [part.strip() for part in forwarded.split(',') if part.strip()]
    candidates.reverse()
    remote = (request.META.get('REMOTE_ADDR') or '').strip()
    if remote:
        candidates.append(remote)
    for value in candidates:
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            continue
    return 'unknown'


def check_rate(request, scope, limit=8, window=300):
    ip = client_ip(request)
    key = f'rl:{scope}:{ip}'
    added = cache.add(key, 1, window)
    if not added:
        try:
            n = cache.incr(key)
        except (ValueError, TypeError):
            cache.set(key, 1, window)
            n = 1
        if n > limit:
            response = HttpResponseTooManyRequests('Zu viele Versuche. Bitte später erneut versuchen.')
            response['Retry-After'] = str(window)
            return response
    return None


def require_post(request):
    if request.method != 'POST':
        raise PermissionDenied
