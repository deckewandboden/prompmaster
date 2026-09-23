from __future__ import annotations

from urllib.parse import urlsplit

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.audit.services import audit
from apps.core.security import check_rate

SENSITIVE_REAUTH_SESSION_KEY = 'staff_sensitive_reauth_at'
SENSITIVE_REAUTH_NEXT_KEY = 'staff_sensitive_reauth_next'
SENSITIVE_REAUTH_MAX_AGE_SECONDS = 300


class SensitiveReauthForm(forms.Form):
    password = forms.CharField(
        label='Eigenes Passwort',
        widget=forms.PasswordInput(render_value=False),
        help_text='Bestätigen Sie Ihre netstyle Identität für Hochrisikoaktionen.',
    )


def sensitive_reauth_is_fresh(request, user=None):
    user = user or getattr(request, 'user', None)
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if not user.two_factor_required or not user.totp_secret_enc:
        return False
    if request.session.get('two_factor_ok') is not True:
        return False
    try:
        granted_at = float(request.session.get(SENSITIVE_REAUTH_SESSION_KEY, 0))
    except (TypeError, ValueError):
        return False
    if granted_at <= 0:
        return False
    age = timezone.now().timestamp() - granted_at
    return 0 <= age <= SENSITIVE_REAUTH_MAX_AGE_SECONDS


def safe_internal_return_url(request, candidate):
    candidate = (candidate or '').strip()
    if not candidate:
        return reverse('ns_admin:dashboard')
    if candidate.startswith('/') and not candidate.startswith('//'):
        return candidate
    if not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return reverse('ns_admin:dashboard')
    parts = urlsplit(candidate)
    value = parts.path or '/'
    if parts.query:
        value += '?' + parts.query
    return value


@login_required
def sensitive_reauth(request):
    user = request.user
    if not user.is_staff:
        raise PermissionDenied
    if not user.two_factor_required or not user.totp_secret_enc:
        raise PermissionDenied
    if request.session.get('two_factor_ok') is not True:
        request.session['post_2fa_next'] = request.get_full_path()
        return redirect('accounts:two_factor')

    form = SensitiveReauthForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if not user.check_password(form.cleaned_data['password']):
            limited = check_rate(
                request,
                f'staff-sensitive-reauth:{user.pk}',
                limit=8,
                window=300,
            )
            if limited:
                return limited
            form.add_error('password', 'Passwort falsch.')
        else:
            # Rotate the session identifier while retaining the already proven
            # 2FA/security-version state. The grant is deliberately short-lived.
            request.session.cycle_key()
            request.session[SENSITIVE_REAUTH_SESSION_KEY] = timezone.now().timestamp()
            target = safe_internal_return_url(
                request,
                request.session.pop(SENSITIVE_REAUTH_NEXT_KEY, ''),
            )
            audit(
                user,
                'auth.staff_sensitive_reauth',
                user,
                {'max_age_seconds': SENSITIVE_REAUTH_MAX_AGE_SECONDS},
                request=request,
            )
            messages.success(
                request,
                'Sicherheitsfreigabe aktiv. Hochrisikoaktionen sind für fünf Minuten freigegeben.',
            )
            return redirect(target)

    return render(
        request,
        'ns_admin/form.html',
        {
            'title': 'Sicherheitsfreigabe bestätigen',
            'form': form,
            'form_variant': 'security',
            'cancel_url': safe_internal_return_url(
                request,
                request.session.get(SENSITIVE_REAUTH_NEXT_KEY, ''),
            ),
        },
    )
