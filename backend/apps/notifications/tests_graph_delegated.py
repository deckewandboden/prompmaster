"""No-network contract tests for delegated Microsoft 365 OAuth + Graph Mail.Send.Shared."""
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.core.settings_store import set_setting
from apps.integrations.models import IntegrationSecret
from apps.integrations.services import get_secret, set_secret

from .graph_delegated import (
    GraphDelegatedError,
    authorization_url,
    complete_authorization,
    connection_status,
    delegated_access_token,
    disconnect,
    OAUTH_SESSION_KEY,
)
from .services import _send_graph


TEST_KEY = base64.urlsafe_b64encode(b'0123456789abcdef0123456789abcdef').decode('ascii')
TENANT = '11111111-2222-4333-8444-555555555555'
CLIENT = '66666666-7777-4888-9999-aaaaaaaaaaaa'
LOGIN = 'test-operator@example.test'
SENDER = 'team-shared@example.test'
CALLBACK = 'https://example.test/ns-admin/email/graph/callback/'


@override_settings(APP_ENCRYPTION_KEY=TEST_KEY)
class DelegatedGraphMailTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk=123)
        set_setting('mail_graph', {
            'tenant_id': TENANT,
            'client_id': CLIENT,
            'sender': SENDER,
            'auth_mode': 'delegated',
            'login_email': LOGIN,
        })
        set_secret('graph_client_secret', 'confidential-test-secret')

    def _request(self, path='/ns-admin/email/graph/connect/', data=None):
        request = self.factory.get(path, data=data or {}, secure=True)
        request.user = self.user
        SessionMiddleware(lambda _: None).process_request(request)
        request.session.save()
        return request

    def _authorize(self):
        request = self._request()
        with patch('apps.notifications.graph_delegated.requests.post') as post:
            url = authorization_url(request, CALLBACK)
        post.assert_not_called()
        return request, url

    def test_connection_initially_disconnected_and_no_send_is_triggered(self):
        self.assertFalse(connection_status()['connected'])
        req, url = self._authorize()
        parsed = urlsplit(url)
        self.assertEqual(parsed.hostname, 'login.microsoftonline.com')
        self.assertEqual(parsed.path, f'/{TENANT}/oauth2/v2.0/authorize')
        params = parse_qs(parsed.query)
        self.assertEqual(params['redirect_uri'][0], CALLBACK)
        self.assertEqual(params['code_challenge_method'], ['S256'])
        self.assertIn('Mail.Send.Shared', params['scope'][0])
        self.assertIn('offline_access', params['scope'][0])
        self.assertNotIn('confidential-test-secret', url)
        self.assertEqual(req.session[OAUTH_SESSION_KEY]['state'], params['state'][0])

    def test_callback_requires_matching_state_and_expires_on_mismatch(self):
        req, url = self._authorize()
        req.GET = {'state': 'incorrect', 'code': 'code'}
        with patch('apps.notifications.graph_delegated.requests.post') as post:
            with self.assertRaises(GraphDelegatedError):
                complete_authorization(req, CALLBACK)
        post.assert_not_called()
        self.assertNotIn(OAUTH_SESSION_KEY, req.session)

    def test_verified_mfa_callback_persists_only_encrypted_refresh_token(self):
        req, url = self._authorize()
        query = parse_qs(urlsplit(url).query)
        verifier = req.session[OAUTH_SESSION_KEY]['verifier']
        req.GET = {'state': query['state'][0], 'code': 'test-code'}
        token_reply = MagicMock(status_code=200)
        token_reply.json.return_value = {
            'access_token': 'opaque-test-access',
            'refresh_token': 'test-rotating-refresh-token',
            'scope': 'Mail.Send.Shared User.Read',
        }
        account_reply = MagicMock(status_code=200)
        account_reply.json.return_value = {'userPrincipalName': LOGIN}
        with patch('apps.notifications.graph_delegated.requests.post', return_value=token_reply) as post, \
             patch('apps.notifications.graph_delegated.requests.get', return_value=account_reply) as get:
            self.assertEqual(complete_authorization(req, CALLBACK), LOGIN)
        self.assertEqual(post.call_args.kwargs['data']['code_verifier'], verifier)
        self.assertNotIn(OAUTH_SESSION_KEY, req.session)
        self.assertTrue(get.called)
        self.assertTrue(connection_status()['connected'])
        self.assertEqual(connection_status()['account'], LOGIN)
        encrypted = IntegrationSecret.objects.get(code='graph_delegated_refresh_token').encrypted_value
        self.assertNotIn('test-rotating-refresh-token', encrypted)
        self.assertEqual(get_secret('graph_delegated_refresh_token'), 'test-rotating-refresh-token')

    def test_callback_wrong_microsoft_account_is_rejected_without_storing_token(self):
        req, url = self._authorize()
        req.GET = {'state': parse_qs(urlsplit(url).query)['state'][0], 'code': 'code'}
        token_reply = MagicMock(status_code=200)
        token_reply.json.return_value = {
            'access_token': 'opaque', 'refresh_token': 'refresh',
            'scope': 'Mail.Send.Shared User.Read',
        }
        who_reply = MagicMock(status_code=200)
        who_reply.json.return_value = {'userPrincipalName': 'other@example.test'}
        with patch('apps.notifications.graph_delegated.requests.post', return_value=token_reply), \
             patch('apps.notifications.graph_delegated.requests.get', return_value=who_reply):
            with self.assertRaisesMessage(GraphDelegatedError, 'Wrong Microsoft sign-in account'):
                complete_authorization(req, CALLBACK)
        self.assertFalse(connection_status()['connected'])

    def test_refresh_is_rotated_and_delegated_send_uses_shared_from(self):
        set_secret('graph_delegated_refresh_token', 'prior-refresh')
        set_setting('mail_graph_delegated_connection', {
            'tenant_id': TENANT, 'client_id': CLIENT, 'login_email': LOGIN,
        })
        token_reply = MagicMock(status_code=200)
        token_reply.json.return_value = {
            'access_token': 'refreshed-access',
            'refresh_token': 'new-refresh',
            'scope': 'Mail.Send.Shared User.Read',
        }
        send_reply = MagicMock(status_code=202)
        send_reply.headers = {'request-id': 'test-graph-request-id'}
        with patch('apps.notifications.graph_delegated.requests.post', return_value=token_reply) as oauth, \
             patch('apps.notifications.services.requests.post', return_value=send_reply) as transport:
            reference = _send_graph(
                SimpleNamespace(subject='one explicitly selected test', recipient='recipient@example.test'),
                'test body',
            )
        self.assertEqual(reference, 'test-graph-request-id')
        self.assertEqual(oauth.call_args.kwargs['data']['grant_type'], 'refresh_token')
        self.assertEqual(get_secret('graph_delegated_refresh_token'), 'new-refresh')
        self.assertEqual(transport.call_args.args[0], 'https://graph.microsoft.com/v1.0/me/sendMail')
        payload = transport.call_args.kwargs['json']['message']
        self.assertEqual(payload['from']['emailAddress']['address'], SENDER)
        self.assertEqual(payload['toRecipients'][0]['emailAddress']['address'], 'recipient@example.test')

    def test_disconnection_revokes_local_credential_and_requires_relogin(self):
        set_secret('graph_delegated_refresh_token', 'prior-refresh')
        set_setting('mail_graph_delegated_connection', {
            'tenant_id': TENANT, 'client_id': CLIENT, 'login_email': LOGIN,
        })
        self.assertTrue(connection_status()['connected'])
        disconnect()
        self.assertFalse(connection_status()['connected'])
        self.assertFalse(IntegrationSecret.objects.get(code='graph_delegated_refresh_token').active)
        with self.assertRaises(GraphDelegatedError):
            delegated_access_token()

    def test_wrong_tenant_or_client_invalidates_existing_connection(self):
        set_secret('graph_delegated_refresh_token', 'prior-refresh')
        set_setting('mail_graph_delegated_connection', {
            'tenant_id': TENANT, 'client_id': CLIENT, 'login_email': LOGIN,
        })
        self.assertTrue(connection_status()['connected'])
        set_setting('mail_graph', {
            'tenant_id': '00000000-0000-4000-8000-000000000000',
            'client_id': CLIENT,
            'sender': SENDER,
            'auth_mode': 'delegated',
            'login_email': LOGIN,
        })
        self.assertFalse(connection_status()['connected'])


@override_settings(APP_ENCRYPTION_KEY=TEST_KEY)
class DelegatedGraphHttpSecurityTests(TestCase):
    """Actual Django HTTP route boundary; no live Microsoft request."""

    def setUp(self):
        from django.utils import timezone
        from apps.accounts.models import User

        self.admin = User.objects.create_superuser(
            'graph-superadmin@example.test',
            'Graph-Test-Strong-Password-2026!',
            first_name='Graph',
            last_name='Admin',
        )
        self.admin.totp_secret_enc = 'configured-for-test'
        self.admin.save(update_fields=['totp_secret_enc', 'updated_at'])
        self.client.force_login(self.admin)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session.save()
        set_setting('mail_graph', {
            'tenant_id': TENANT,
            'client_id': CLIENT,
            'sender': SENDER,
            'auth_mode': 'delegated',
            'login_email': LOGIN,
        })
        set_secret('graph_client_secret', 'confidential-test-secret')

    def test_mfa_connect_requires_post_and_does_not_send_mail(self):
        from django.urls import reverse

        connect = reverse('ns_admin:graph_mail_connect')
        self.assertEqual(self.client.get(connect, secure=True).status_code, 405)
        with patch('apps.notifications.graph_delegated.requests.post') as post:
            response = self.client.post(connect, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login.microsoftonline.com/', response.url)
        self.assertIn('Mail.Send.Shared', response.url)
        post.assert_not_called()

    def test_callback_invalid_state_does_not_store_credentials(self):
        from django.urls import reverse

        self.client.post(reverse('ns_admin:graph_mail_connect'), secure=True)
        response = self.client.get(
            reverse('ns_admin:graph_mail_callback'),
            {'state': 'incorrect', 'code': 'invalid'},
            secure=True,
        )
        self.assertRedirects(response, reverse('ns_admin:settings'), fetch_redirect_response=False)
        self.assertFalse(connection_status()['connected'])

    def test_real_test_send_requires_explicit_confirmation(self):
        from django.urls import reverse

        set_secret('graph_delegated_refresh_token', 'refresh')
        set_setting('mail_graph_delegated_connection', {
            'tenant_id': TENANT, 'client_id': CLIENT, 'login_email': LOGIN,
        })
        endpoint = reverse('ns_admin:graph_mail_test')
        with patch('apps.core.graph_mail_views._send_graph') as send:
            response = self.client.post(
                endpoint,
                {'recipient': 'test-recipient@example.test'},
                secure=True,
            )
            self.assertEqual(response.status_code, 302)
            send.assert_not_called()
            response = self.client.post(
                endpoint,
                {'recipient': 'test-recipient@example.test', 'confirm': 'send-one-test'},
                secure=True,
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(send.call_count, 1)

    def test_non_staff_cannot_manage_graph_connection(self):
        from apps.accounts.models import User
        from django.urls import reverse

        other = User.objects.create_user(
            'graph-customer@example.test',
            'Graph-Test-Strong-Password-2026!',
        )
        from django.utils import timezone

        self.client.force_login(other)
        session = self.client.session
        current_time = timezone.now().timestamp()
        session['security_version'] = other.security_version
        session['authenticated_at'] = current_time
        session['last_activity_at'] = current_time
        session.save()
        self.assertEqual(
            self.client.post(reverse('ns_admin:graph_mail_connect'), secure=True).status_code,
            403,
        )

    def test_mfa_settings_never_expose_secret_or_refresh_token(self):
        from django.urls import reverse

        set_secret('graph_delegated_refresh_token', 'secret-refresh-token')
        set_setting('mail_graph_delegated_connection', {
            'tenant_id': TENANT, 'client_id': CLIENT, 'login_email': LOGIN,
        })
        response = self.client.get(reverse('ns_admin:settings'), secure=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Mit Microsoft 365 verbinden', html)
        self.assertIn(reverse('ns_admin:graph_mail_callback'), html)
        self.assertNotIn('confidential-test-secret', html)
        self.assertNotIn('secret-refresh-token', html)
