"""Administrative Microsoft 365 MFA configuration endpoints (no automatic mail send)."""
import logging
from types import SimpleNamespace

import requests
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.utils.translation import gettext as _

from apps.audit.services import audit as write_audit
from apps.notifications.graph_delegated import (
    GraphDelegatedError,
    authorization_url,
    complete_authorization,
    connection_status,
    disconnect,
)
from apps.notifications.services import MailProviderError, _send_graph, get_graph_transport

from .admin_views import staff_perm

logger = logging.getLogger(__name__)


@never_cache
@staff_perm('settings.write')
@require_POST
def graph_connect(request):
    callback = request.build_absolute_uri(reverse('ns_admin:graph_mail_callback'))
    try:
        url = authorization_url(request, callback)
    except GraphDelegatedError as exc:
        messages.error(request, str(exc))
        return redirect('ns_admin:settings')
    write_audit(request.user, 'mail.graph_oauth_started', request.user, {}, request=request)
    return redirect(url)


@never_cache
@staff_perm('settings.write')
@require_GET
def graph_callback(request):
    callback = request.build_absolute_uri(reverse('ns_admin:graph_mail_callback'))
    try:
        account = complete_authorization(request, callback)
    except GraphDelegatedError as exc:
        messages.error(request, str(exc))
        write_audit(request.user, 'mail.graph_oauth_failed', request.user, {}, request=request)
    else:
        messages.success(
            request,
            _('Microsoft 365 MFA verbunden (%(account)s). Noch keine Test-E-Mail gesendet.') %
            {'account': account},
        )
        write_audit(request.user, 'mail.graph_oauth_connected', request.user, {'account': account}, request=request)
    return redirect('ns_admin:settings')


@staff_perm('settings.write')
@require_POST
def graph_disconnect(request):
    if request.POST.get('confirm') != 'disconnect':
        messages.error(request, _('Trennen wurde nicht bestätigt.'))
        return redirect('ns_admin:settings')
    disconnect()
    write_audit(request.user, 'mail.graph_oauth_disconnected', request.user, {}, request=request)
    messages.success(request, _('Microsoft-365-Verbindung getrennt. Keine E-Mail versendet.'))
    return redirect('ns_admin:settings')


@staff_perm('settings.write')
@require_POST
def graph_test_send(request):
    # This endpoint sends a real single message only on explicit confirmation.
    if request.POST.get('confirm') != 'send-one-test':
        messages.error(request, _('Testversand muss ausdrücklich bestätigt werden.'))
        return redirect('ns_admin:settings')
    recipient = (request.POST.get('recipient') or '').strip()
    try:
        validate_email(recipient)
    except ValidationError:
        messages.error(request, _('Bitte eine gültige Testempfängeradresse eintragen.'))
        return redirect('ns_admin:settings')
    if get_graph_transport().get('auth_mode') != 'delegated' or not connection_status()['connected']:
        messages.error(request, _('Zuerst Microsoft 365 per MFA verbinden.'))
        return redirect('ns_admin:settings')
    # Prevent accidental double-clicks and bursts; never send during setup.
    limit_key = f'graph-test-send:{request.user.pk}'
    if not cache.add(limit_key, 'active', timeout=60):
        messages.error(request, _('Ein Testversand wurde gerade ausgelöst. Bitte später erneut versuchen.'))
        return redirect('ns_admin:settings')
    try:
        ref = _send_graph(
            SimpleNamespace(subject='PROMPTFINISHER Microsoft 365 Graph Test', recipient=recipient),
            'Bewusst ausgelöster Microsoft Graph Versandtest aus PROMPTFINISHER.',
        )
    except (MailProviderError, requests.RequestException) as exc:
        logger.warning('Graph acceptance test failed (error class: %s)', type(exc).__name__)
        # No provider payload/headers, token, or secret included in UI or audit.
        messages.error(request, _('Microsoft Graph hat den Testversand nicht bestätigt. Versandprotokoll prüfen.'))
        write_audit(request.user, 'mail.graph_test_failed', request.user, {'recipient': recipient}, request=request)
    else:
        write_audit(
            request.user,
            'mail.graph_test_accepted',
            request.user,
            {'recipient': recipient, 'graph_request_id': ref},
            request=request,
        )
        messages.success(
            request,
            _('Microsoft Graph hat den Test mit HTTP 202 angenommen. Der tatsächliche Posteingang muss separat bestätigt werden.'),
        )
    return redirect('ns_admin:settings')
