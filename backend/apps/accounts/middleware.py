from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone

from apps.core.security import check_rate


class TwoFactorEnforcementMiddleware:
    """Enforce session security-version, mandatory TOTP and sensitive re-auth.

    ``security_version`` is deliberately independent of Django's password
    session hash. Role changes, company-admin promotion, 2FA resets and other
    privilege changes can therefore invalidate every older session immediately.

    Selected high-impact staff actions additionally require the executing
    staff identity to prove its password again inside an already completed
    2FA session. This protects against a stolen but still-valid browser session.
    """

    allowed_prefixes = (
        '/auth/2fa/',
        '/auth/logout/',
        '/auth/verify/',
        '/auth/password-reset/',
        '/health/',
        '/static/',
        '/api/webhooks/mollie/',
    )

    sensitive_reauth_views = {
        'ns_admin:customer_admin_transfer',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def _sensitive_reauth(self, request, user):
        if request.method != 'POST':
            return None
        try:
            view_name = resolve(request.path_info).view_name
        except Resolver404:
            return None
        if view_name not in self.sensitive_reauth_views:
            return None

        # A high-impact staff action must never rely on a password-only staff
        # account or on a session that has not completed the configured TOTP.
        if not (
            user.is_staff
            and user.two_factor_required
            and bool(user.totp_secret_enc)
            and request.session.get('two_factor_ok') is True
        ):
            raise PermissionDenied

        limited = check_rate(
            request,
            f'sensitive-reauth:{user.pk}',
            limit=10,
            window=300,
        )
        if limited:
            return limited

        password = request.POST.get('password', '')
        if not password or not user.check_password(password):
            raise PermissionDenied
        return None

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        session_version = request.session.get('security_version')
        if session_version is None:
            # Sessions that pre-date this mechanism must authenticate again;
            # silently blessing them would defeat privilege-change invalidation.
            next_url = request.get_full_path()
            logout(request)
            return redirect(f"{reverse('accounts:login')}?{urlencode({'next': next_url})}")
        try:
            valid_version = int(session_version) == int(user.security_version)
            now = timezone.now().timestamp()
            started = float(request.session.get('authenticated_at', now))
            activity = float(request.session.get('last_activity_at', now))
            valid_time = (
                now - started <= settings.SESSION_COOKIE_AGE
                and now - activity <= settings.SESSION_IDLE_TIMEOUT
            )
        except (ValueError, TypeError):
            valid_version = valid_time = False
        if not valid_version or not valid_time:
            next_url = request.get_full_path()
            logout(request)
            return redirect(f"{reverse('accounts:login')}?{urlencode({'next': next_url})}")

        request.session.setdefault('authenticated_at', now)
        request.session['last_activity_at'] = now

        if user.two_factor_required and not user.totp_secret_enc:
            if not request.path.startswith(('/auth/2fa/setup/', '/auth/logout/', '/auth/verify/')):
                request.session['post_2fa_next'] = request.get_full_path()
                return redirect(reverse('accounts:two_factor_setup'))

        if (
            user.two_factor_required
            and not request.session.get('two_factor_ok')
            and not any(request.path.startswith(prefix) for prefix in self.allowed_prefixes)
        ):
            request.session['post_2fa_next'] = request.get_full_path()
            return redirect(reverse('accounts:two_factor'))

        denied = self._sensitive_reauth(request, user)
        if denied:
            return denied
        return self.get_response(request)
