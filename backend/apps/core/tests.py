import json
import logging
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.integrations.models import ServiceAccount
from apps.legal.models import DeletionRequest
from .middleware import CorrelationIdMiddleware, JsonLogFormatter
from .security import token_hash, token_pair


class SecurityTests(SimpleTestCase):
    def test_token_hash(self):
        raw, hashed = token_pair()
        self.assertEqual(token_hash(raw), hashed)
        self.assertNotEqual(raw, hashed)


class ServiceAccountRotationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'api-admin@example.test',
            None,
            is_staff=True,
            is_superuser=True,
            two_factor_required=False,
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

        self.old_token, hashed = token_pair()
        self.account = ServiceAccount.objects.create(
            name='technikerportal-maintenance',
            token_hash=hashed,
            scopes=['ops.read'],
            active=True,
        )

    def test_rotation_invalidates_old_token_and_returns_new_token_once(self):
        response = self.client.post(
            f'/ns-admin/api/service-accounts/{self.account.id}/rotate/'
        )
        self.assertEqual(response.status_code, 200)
        new_token = response.context['token']
        self.assertTrue(new_token)
        self.assertNotEqual(new_token, self.old_token)

        self.account.refresh_from_db()
        self.assertEqual(self.account.token_hash, token_hash(new_token))
        self.assertIsNone(self.account.last_used_at)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='service_account.rotated',
                object_id=str(self.account.id),
            ).exists()
        )

        old_response = self.client.get(
            '/api/v1/ops/health',
            HTTP_AUTHORIZATION=f'Bearer {self.old_token}',
        )
        self.assertEqual(old_response.status_code, 401)

        new_response = self.client.get(
            '/api/v1/ops/health',
            HTTP_AUTHORIZATION=f'Bearer {new_token}',
        )
        self.assertEqual(new_response.status_code, 200)

    def test_rotation_requires_post_and_active_account(self):
        self.assertEqual(
            self.client.get(
                f'/ns-admin/api/service-accounts/{self.account.id}/rotate/'
            ).status_code,
            403,
        )
        self.account.active = False
        self.account.save(update_fields=['active', 'updated_at'])
        response = self.client.post(
            f'/ns-admin/api/service-accounts/{self.account.id}/rotate/'
        )
        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(self.account.token_hash, token_hash(self.old_token))


class PrivacyDeletionRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'privacy-user@example.test',
            None,
            two_factor_required=False,
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_deletion_request_is_post_only_and_idempotent(self):
        self.assertEqual(
            self.client.get('/portal/privacy/deletion-request/').status_code,
            403,
        )
        response = self.client.post(
            '/portal/privacy/deletion-request/',
            {'confirm': '1'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DeletionRequest.objects.filter(
                user=self.user,
                status__in=['open', 'processing'],
            ).count(),
            1,
        )
        request_row = DeletionRequest.objects.get(user=self.user)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='privacy.deletion_requested',
                object_id=str(request_row.id),
            ).exists()
        )

        response = self.client.post(
            '/portal/privacy/deletion-request/',
            {'confirm': '1'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DeletionRequest.objects.filter(user=self.user).count(), 1)

    def test_explicit_confirmation_is_required(self):
        response = self.client.post('/portal/privacy/deletion-request/', {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DeletionRequest.objects.filter(user=self.user).exists())


class StructuredLoggingTests(SimpleTestCase):
    def test_formatter_receives_request_correlation_and_user_context(self):
        captured = {}

        def view(request):
            record = logging.LogRecord(
                'promptmaster.test',
                logging.INFO,
                __file__,
                1,
                'hello %s',
                ('world',),
                None,
            )
            captured['payload'] = json.loads(JsonLogFormatter().format(record))
            return HttpResponse('ok')

        request = RequestFactory().get('/', HTTP_X_CORRELATION_ID='corr-123')
        request.user = SimpleNamespace(is_authenticated=True, pk='user-1')
        response = CorrelationIdMiddleware(view)(request)

        self.assertEqual(response['X-Correlation-ID'], 'corr-123')
        self.assertEqual(captured['payload']['correlation_id'], 'corr-123')
        self.assertEqual(captured['payload']['user_id'], 'user-1')
        self.assertEqual(captured['payload']['service'], 'promptmaster.test')
        self.assertEqual(captured['payload']['message'], 'hello world')
        self.assertEqual(captured['payload']['level'], 'INFO')
        self.assertIn('timestamp', captured['payload'])
        self.assertIn('event_code', captured['payload'])

    def test_invalid_correlation_id_is_replaced(self):
        request = RequestFactory().get('/', HTTP_X_CORRELATION_ID='bad value')
        request.user = SimpleNamespace(is_authenticated=False)
        response = CorrelationIdMiddleware(lambda request: HttpResponse('ok'))(request)
        self.assertNotEqual(response['X-Correlation-ID'], 'bad value')
        self.assertTrue(response['X-Correlation-ID'])
