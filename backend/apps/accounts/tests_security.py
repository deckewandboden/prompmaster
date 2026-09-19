from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, RecoveryCode
from apps.accounts.security import consume_second_factor, login_lock_remaining
from apps.accounts.totp import code
from apps.accounts.views import PASSWORD_RESET_SALT
from apps.audit.models import AuditEvent
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

    def test_safe_login_page_requests_do_not_consume_attempt_budget(self):
        for _ in range(25):
            response = self.client.get('/auth/login/', REMOTE_ADDR='203.0.113.41')
            self.assertEqual(response.status_code, 200)

        payload = {
            'email': 'unknown@example.test',
            'password': 'Definitely-Wrong-Password-42!',
        }
        for _ in range(10):
            response = self.client.post(
                '/auth/login/',
                payload,
                REMOTE_ADDR='203.0.113.41',
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            '/auth/login/',
            payload,
            REMOTE_ADDR='203.0.113.41',
        )
        self.assertEqual(response.status_code, 429)

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


class LoginLockoutTests(TestCase):
    email = 'lockout@example.test'
    password = 'Lockout-Test-Password-42!'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(self.email, self.password)

    def tearDown(self):
        cache.clear()

    def test_five_failures_temporarily_lock_account_and_are_audited(self):
        for _ in range(5):
            response = self.client.post(
                '/auth/login/',
                {'email': self.email, 'password': 'Wrong-Password-42!'},
            )
            self.assertEqual(response.status_code, 200)

        self.assertGreater(login_lock_remaining(self.email), 0)
        self.assertEqual(
            AuditEvent.objects.filter(actor=self.user, action='auth.login_failed').count(),
            5,
        )
        last_failure = AuditEvent.objects.filter(
            actor=self.user,
            action='auth.login_failed',
        ).latest('created_at')
        self.assertTrue(last_failure.changes['locked'])

        response = self.client.post(
            '/auth/login/',
            {'email': self.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Anmeldung fehlgeschlagen. Bitte später erneut versuchen.')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(
            AuditEvent.objects.filter(actor=self.user, action='auth.login_locked').exists()
        )

    def test_failed_login_audit_contains_request_evidence(self):
        response = self.client.post(
            '/auth/login/',
            {'email': self.email, 'password': 'Wrong-Password-42!'},
            REMOTE_ADDR='203.0.113.55',
            HTTP_USER_AGENT='PromptMaster-Security-Test/1.0',
            HTTP_X_CORRELATION_ID='auth-lockout-test-001',
        )
        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(actor=self.user, action='auth.login_failed')
        self.assertEqual(event.ip, '203.0.113.55')
        self.assertEqual(event.user_agent, 'PromptMaster-Security-Test/1.0')
        self.assertEqual(event.correlation_id, 'auth-lockout-test-001')

    def test_successful_login_clears_account_failure_counter(self):
        for _ in range(4):
            self.client.post(
                '/auth/login/',
                {'email': self.email, 'password': 'Wrong-Password-42!'},
            )
        response = self.client.post(
            '/auth/login/',
            {'email': self.email, 'password': self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(login_lock_remaining(self.email), 0)

        self.client.post('/auth/logout/')
        for _ in range(4):
            self.client.post(
                '/auth/login/',
                {'email': self.email, 'password': 'Wrong-Password-42!'},
            )
        self.assertEqual(login_lock_remaining(self.email), 0)

    def test_unknown_account_uses_same_generic_failure_without_audit_target(self):
        response = self.client.post(
            '/auth/login/',
            {'email': 'unknown@example.test', 'password': 'Wrong-Password-42!'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Anmeldung fehlgeschlagen.')
        self.assertFalse(AuditEvent.objects.filter(action='auth.login_failed').exists())
