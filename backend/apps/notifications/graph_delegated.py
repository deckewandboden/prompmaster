"""Delegated Microsoft Graph mail authorization with MFA and shared-mailbox Send As.

OAuth credentials and refresh tokens are server-only encrypted IntegrationSecrets.
No application token or mailbox password is exposed to the browser. All Graph
network requests are bounded and all public errors are intentionally sanitized.
"""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from apps.core.settings_store import get_setting, set_setting
from apps.integrations.models import IntegrationSecret
from apps.integrations.services import get_secret, set_secret

AUTH_SCOPE = (
    'openid profile offline_access '
    'https://graph.microsoft.com/Mail.Send.Shared '
    'https://graph.microsoft.com/User.Read'
)
REFRESH_SECRET_KEY = 'graph_delegated_refresh_token'
CONNECTION_SETTING_KEY = 'mail_graph_delegated_connection'
OAUTH_SESSION_KEY = 'mail_graph_delegated_oauth'
OAUTH_TTL_SECONDS = 600


class GraphDelegatedError(RuntimeError):
    """Safe to present to administrators; never contains tokens or secrets."""


def _config():
    from .services import get_graph_transport

    return get_graph_transport()


def _connection():
    return get_setting(CONNECTION_SETTING_KEY, {}) or {}


def connection_status():
    graph = _config()
    connection = _connection()
    token = get_secret(REFRESH_SECRET_KEY, '')
    valid = bool(
        graph.get('auth_mode') == 'delegated'
        and token
        and connection.get('tenant_id') == graph['tenant_id']
        and connection.get('client_id') == graph['client_id']
        and connection.get('login_email', '').casefold() == graph.get('login_email', '').casefold()
    )
    return {
        'connected': valid,
        'account': connection.get('login_email', '') if valid else '',
        'connected_at': connection.get('connected_at', '') if valid else '',
        'needs_consent': not valid,
    }


def disconnect():
    # Invalidate the stored credential, not merely the displayed status.
    IntegrationSecret.objects.filter(code=REFRESH_SECRET_KEY).update(
        encrypted_value='', active=False,
    )
    set_setting(CONNECTION_SETTING_KEY, {}, 'Delegated Graph connection disconnected')


def _tenant_url(tenant, action):
    # Callers validate identifiers before passing them to an outbound URL.
    return f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{action}'


def _valid_tenant_id(value):
    import uuid

    try:
        return str(uuid.UUID(str(value))) == str(value).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _jwt_claims(token):
    """Decode only the diagnostic claims of a token issued over Microsoft TLS.

    This is NOT authentication: Graph itself verifies the bearer token.
    """
    try:
        payload = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (IndexError, ValueError, UnicodeDecodeError, TypeError):
        return {}


def _require_tenant_claim(token, tenant):
    claims = _jwt_claims(token)
    if claims.get('tid') and str(claims['tid']).lower() != tenant.lower():
        raise GraphDelegatedError('Microsoft returned a token for another tenant.')


def _require_scope(payload):
    scopes = set(str(payload.get('scope') or '').split())
    if scopes and not (
        {'Mail.Send.Shared', 'https://graph.microsoft.com/Mail.Send.Shared'} & scopes
    ):
        raise GraphDelegatedError('Delegated Mail.Send.Shared permission was not granted.')


def _post_token(tenant, fields):
    try:
        result = requests.post(_tenant_url(tenant, 'token'), data=fields, timeout=(5, 20))
        if result.status_code != 200:
            raise GraphDelegatedError(
                f'Microsoft OAuth refused the request (HTTP {result.status_code}). '
                'Check consent, credentials and whether MFA reconnect is required.'
            )
        data = result.json()
    except (requests.RequestException, ValueError) as exc:
        raise GraphDelegatedError('Microsoft OAuth token endpoint unavailable or returned invalid JSON.') from None
    if not data.get('access_token'):
        raise GraphDelegatedError('Microsoft OAuth response contained no access token.')
    _require_scope(data)
    _require_tenant_claim(data['access_token'], tenant)
    return data


def authorization_url(request, callback_url):
    config = _config()
    if config.get('auth_mode') != 'delegated':
        raise GraphDelegatedError('Select delegated Microsoft 365 MFA in the mail settings first.')
    if not (
        _valid_tenant_id(config['tenant_id'])
        and config['client_id']
        and config['client_secret']
        and config['sender']
        and config['login_email']
    ):
        raise GraphDelegatedError('Complete tenant, client, secret, login account and shared mailbox first.')
    if not callback_url.startswith('https://') and not settings.DEBUG:
        raise GraphDelegatedError('Microsoft OAuth requires an HTTPS callback.')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode('ascii')).digest()
    ).decode('ascii').rstrip('=')
    request.session[OAUTH_SESSION_KEY] = {
        'state': state,
        'verifier': verifier,
        'created_at': int(time.time()),
        'user_id': str(request.user.pk),
        'tenant_id': config['tenant_id'],
        'client_id': config['client_id'],
        'login_email': config['login_email'],
        'callback_url': callback_url,
    }
    request.session.modified = True
    query = urlencode({
        'client_id': config['client_id'],
        'response_type': 'code',
        'redirect_uri': callback_url,
        'response_mode': 'query',
        'scope': AUTH_SCOPE,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'prompt': 'select_account',
    })
    return _tenant_url(config['tenant_id'], 'authorize') + '?' + query


def complete_authorization(request, callback_url):
    # Pop first so a code/state cannot be replayed, including on an error.
    pending = request.session.pop(OAUTH_SESSION_KEY, None)
    request.session.modified = True
    if not pending:
        raise GraphDelegatedError('Microsoft connection expired. Start the MFA login again.')
    config = _config()
    if (
        not secrets.compare_digest(str(pending.get('state', '')), str(request.GET.get('state', '')))
        or int(time.time()) - int(pending.get('created_at', 0)) > OAUTH_TTL_SECONDS
        or int(time.time()) < int(pending.get('created_at', 0))
        or pending.get('user_id') != str(request.user.pk)
        or pending.get('tenant_id') != config['tenant_id']
        or pending.get('client_id') != config['client_id']
        or pending.get('login_email') != config['login_email']
        or pending.get('callback_url') != callback_url
    ):
        raise GraphDelegatedError('Microsoft connection state is invalid or expired.')
    if request.GET.get('error'):
        raise GraphDelegatedError('Microsoft login was cancelled or consent was refused.')
    code = request.GET.get('code', '')
    if not code:
        raise GraphDelegatedError('Microsoft OAuth did not return an authorization code.')
    token = _post_token(config['tenant_id'], {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'grant_type': 'authorization_code',
        'code': code,
        'scope': AUTH_SCOPE,
        'redirect_uri': callback_url,
        'code_verifier': pending['verifier'],
    })
    if not token.get('refresh_token'):
        raise GraphDelegatedError('Missing offline_access refresh token; reconnect with consent.')
    try:
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers={'Authorization': f"Bearer {token['access_token']}"},
            params={'$select': 'userPrincipalName,mail,id'},
            timeout=(5, 20),
        )
        if response.status_code != 200:
            raise GraphDelegatedError(
                f'Microsoft Graph could not verify the signed-in account (HTTP {response.status_code}).'
            )
        me = response.json()
    except (requests.RequestException, ValueError):
        raise GraphDelegatedError('Unable to verify the Microsoft signed-in account.') from None
    actual_account = str(me.get('userPrincipalName') or '').casefold()
    if actual_account != config['login_email'].casefold():
        raise GraphDelegatedError('Wrong Microsoft sign-in account selected for delegated mail.')
    set_secret(REFRESH_SECRET_KEY, token['refresh_token'])
    set_setting(CONNECTION_SETTING_KEY, {
        'tenant_id': config['tenant_id'],
        'client_id': config['client_id'],
        'login_email': config['login_email'],
        'connected_at': timezone.now().isoformat(),
    }, 'Delegated Microsoft Graph OAuth MFA connection metadata (no tokens)')
    return actual_account


def delegated_access_token():
    config = _config()
    if not connection_status()['connected']:
        raise GraphDelegatedError('Microsoft 365 MFA connection missing; reconnect in Admin E-Mail settings.')
    token = _post_token(config['tenant_id'], {
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'grant_type': 'refresh_token',
        'refresh_token': get_secret(REFRESH_SECRET_KEY),
        'scope': AUTH_SCOPE,
    })
    if token.get('refresh_token'):
        set_secret(REFRESH_SECRET_KEY, token['refresh_token'])
    return token['access_token']
