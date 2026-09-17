import hashlib

from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.crypto import decrypt
from .totp import matching_step

LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW = 900
LOGIN_LOCK_SECONDS = 900


def _login_identity(email):
    normalized = (email or '').strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest() if normalized else ''


def _login_cache_key(kind, email):
    identity = _login_identity(email)
    return f'auth:{kind}:{identity}' if identity else ''


def login_lock_remaining(email):
    key = _login_cache_key('lock', email)
    if not key:
        return 0
    locked_until = cache.get(key)
    if not locked_until:
        return 0
    remaining = max(0, int(float(locked_until) - timezone.now().timestamp()))
    if remaining <= 0:
        cache.delete(key)
        return 0
    return remaining


def register_login_failure(email):
    """Record a failed password login and temporarily lock repeated failures.

    Cache keys contain only a SHA-256 digest of the normalized e-mail address;
    raw account identifiers are never written to Redis by this mechanism.
    """
    failure_key = _login_cache_key('failures', email)
    lock_key = _login_cache_key('lock', email)
    if not failure_key or not lock_key:
        return 0, False

    if cache.add(failure_key, 1, LOGIN_FAILURE_WINDOW):
        failures = 1
    else:
        try:
            failures = cache.incr(failure_key)
        except (ValueError, TypeError):
            cache.set(failure_key, 1, LOGIN_FAILURE_WINDOW)
            failures = 1

    if failures >= LOGIN_FAILURE_LIMIT:
        locked_until = timezone.now().timestamp() + LOGIN_LOCK_SECONDS
        cache.set(lock_key, locked_until, LOGIN_LOCK_SECONDS)
        cache.delete(failure_key)
        return failures, True
    return failures, False


def clear_login_failures(email):
    for kind in ('failures', 'lock'):
        key = _login_cache_key(kind, email)
        if key:
            cache.delete(key)


@transaction.atomic
def consume_second_factor(user, value):
    """Serialize TOTP and recovery use, including concurrent logins."""
    locked = type(user).objects.select_for_update().get(pk=user.pk)
    if not locked.is_active or not locked.totp_secret_enc:
        return False
    step = matching_step(decrypt(locked.totp_secret_enc), value)
    if step is not None and step > locked.last_totp_step:
        locked.last_totp_step = step
        locked.save(update_fields=['last_totp_step', 'updated_at'])
        return True
    for recovery in locked.recovery_codes.filter(used_at__isnull=True):
        if check_password(value, recovery.code_hash):
            recovery.used_at = timezone.now()
            recovery.save(update_fields=['used_at', 'updated_at'])
            return True
    return False


def bump_security_version(user):
    """Invalidate every previously issued authenticated session for ``user``.

    The caller can re-bind the current session afterwards when the security
    action is intentionally performed by the authenticated user (for example
    completing TOTP setup).
    """
    type(user).objects.filter(pk=user.pk).update(
        security_version=F('security_version') + 1,
        last_security_change_at=timezone.now(),
    )
    user.refresh_from_db(fields=['security_version', 'last_security_change_at'])
    return user.security_version


def bind_security_session(request, user, *, two_factor_ok):
    request.session['security_version'] = int(user.security_version)
    request.session['two_factor_ok'] = bool(two_factor_ok)
    now = timezone.now().timestamp()
    request.session.setdefault('authenticated_at', now)
    request.session['last_activity_at'] = now
