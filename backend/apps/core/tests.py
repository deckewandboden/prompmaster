from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.integrations.models import ServiceAccount
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
