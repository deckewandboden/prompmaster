from django.db.models import F
from django.utils import timezone


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
