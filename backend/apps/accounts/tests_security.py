from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User, RecoveryCode
from apps.accounts.security import consume_second_factor
from apps.accounts.totp import code
from apps.core.crypto import encrypt


@override_settings(APP_ENCRYPTION_KEY='3fDltyLLocPcNedSN3wwVTiyNlFCsVyTcdi-pP-WiJY=')
class SecondFactorTests(TestCase):
    def setUp(self):
        self.secret = 'JBSWY3DPEHPK3PXP'
        self.user = User.objects.create_user('security@example.test', 'Secure-Test-Password-42!', totp_secret_enc=encrypt(self.secret), two_factor_required=True)

    def test_totp_cannot_be_replayed(self):
        value = code(self.secret, at=1800000000)
        with patch('apps.accounts.totp.time.time', return_value=1800000000):
            self.assertTrue(consume_second_factor(self.user, value))
            self.assertFalse(consume_second_factor(self.user, value))

    def test_recovery_code_is_single_use(self):
        RecoveryCode.objects.create(user=self.user, code_hash=make_password('recovery-one-use'))
        self.assertTrue(consume_second_factor(self.user, 'recovery-one-use'))
        self.assertFalse(consume_second_factor(self.user, 'recovery-one-use'))

    def test_invalid_factor_does_not_consume_recovery(self):
        row = RecoveryCode.objects.create(user=self.user, code_hash=make_password('keep-code'))
        self.assertFalse(consume_second_factor(self.user, 'wrong-code'))
        row.refresh_from_db()
        self.assertIsNone(row.used_at)

    def test_pending_setup_secret_is_encrypted_in_session(self):
        self.user.totp_secret_enc = ''
        self.user.save()
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session.save()
        response = self.client.get('/auth/2fa/setup/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('pending_totp', self.client.session)
        self.assertNotIn(response.context['secret'], self.client.session['pending_totp_enc'])

    def test_idle_and_absolute_session_timeouts(self):
        for key, age in [('last_activity_at', 1801), ('authenticated_at', 28801)]:
            self.client.force_login(self.user)
            session = self.client.session
            session['security_version'] = self.user.security_version
            session['two_factor_ok'] = True
            session[key] = (timezone.now() - timedelta(seconds=age)).timestamp()
            session.save()
            self.assertEqual(self.client.get('/portal/dashboard/').status_code, 302)
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_invalid_session_security_version_logs_out(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = 'invalid'
        session.save()
        self.assertEqual(self.client.get('/portal/dashboard/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_is_temporarily_throttled_and_security_event_is_logged(self):
        payload = {
            'email': 'unknown@example.test',
            'password': 'Definitely-Wrong-Password-42!',
        }
        for _ in range(10):
            response = self.client.post(
                '/auth/login/',
                payload,
                REMOTE_ADDR='203.0.113.40',
            )
            self.assertEqual(response.status_code, 200)

        with self.assertLogs('apps.core.security', level='WARNING') as captured:
            response = self.client.post(
                '/auth/login/',
                payload,
                REMOTE_ADDR='203.0.113.40',
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '300')
        self.assertTrue(
            any('Rate limit exceeded for scope=login' in row for row in captured.output)
        )

