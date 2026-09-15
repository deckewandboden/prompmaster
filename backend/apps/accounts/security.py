from django.db.models import F
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.hashers import check_password
from apps.core.crypto import decrypt
from .totp import matching_step


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
