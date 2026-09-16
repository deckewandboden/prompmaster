import json
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company, Membership
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment
from apps.audit.models import AuditEvent
from apps.integrations.models import ServiceAccount
from apps.legal.models import DeletionRequest
from .datagrid import DataGrid
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

    def test_ops_api_requires_scope_and_is_get_only(self):
        raw, hashed = token_pair()
        account = ServiceAccount.objects.create(
            name='wrong-scope', token_hash=hashed, scopes=['api.read'], active=True
        )
        self.assertEqual(
            self.client.get('/api/v1/ops/health', HTTP_AUTHORIZATION=f'Bearer {raw}').status_code,
            401,
        )
        account.scopes = ['ops.read']
        account.save(update_fields=['scopes', 'updated_at'])
        self.assertEqual(
            self.client.post('/api/v1/ops/health', HTTP_AUTHORIZATION=f'Bearer {raw}').status_code,
            405,
        )
        response = self.client.get('/api/v1/ops/health', HTTP_AUTHORIZATION=f'Bearer {raw}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(response['Cache-Control'], 'no-store')


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


class NotificationReleaseTests(TestCase):
    def setUp(self):
        from apps.notifications.models import EmailTemplate

        self.template = EmailTemplate.objects.create(
            code='completion-test',
            subject='Status {value}',
            body_text='Text {value}',
            active=True,
        )

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_queue_is_persisted_before_task_and_normalizes_recipient(self, delay):
        from apps.notifications.services import queue_email

        with self.captureOnCommitCallbacks(execute=True):
            message = queue_email(
                'completion-test',
                '  USER@Example.TEST ',
                {'value': 'OK'},
            )
        message.refresh_from_db()
        self.assertEqual(message.recipient, 'user@example.test')
        self.assertEqual(message.status, 'queued')
        self.assertEqual(message.subject, 'Status OK')
        delay.assert_called_once_with(str(message.id))

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_queue_persists_explicit_customer_scope(self, delay):
        from apps.notifications.services import queue_email

        with self.captureOnCommitCallbacks(execute=True):
            message = queue_email(
                'completion-test',
                'scope@example.test',
                {'value': 'Scoped'},
                scope_company='company-42',
                scope_user='user-42',
            )
        message.refresh_from_db()
        self.assertEqual(message.context['pm_scope_company_id'], 'company-42')
        self.assertEqual(message.context['pm_scope_user_id'], 'user-42')
        self.assertEqual(message.subject, 'Status Scoped')
        delay.assert_called_once_with(str(message.id))

    @patch('apps.notifications.services.requests.post')
    def test_graph_provider_uses_client_credentials_and_records_request_id(self, post):
        from apps.notifications.models import EmailMessage
        from apps.notifications.services import send_now

        token_response = Mock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {'access_token': 'access-token'}
        send_response = Mock()
        send_response.raise_for_status.return_value = None
        send_response.headers = {'request-id': 'graph-request-42'}
        post.side_effect = [token_response, send_response]

        message = EmailMessage.objects.create(
            template=self.template,
            recipient='user@example.test',
            subject='Status OK',
            context={'value': 'OK'},
        )
        with self.settings(
            EMAIL_PROVIDER='graph',
            GRAPH_TENANT_ID='tenant',
            GRAPH_CLIENT_ID='client',
            GRAPH_CLIENT_SECRET='secret',
            GRAPH_SENDER='sender@example.test',
        ):
            send_now(message)

        message.refresh_from_db()
        self.assertEqual(message.status, 'sent')
        self.assertIsNotNone(message.sent_at)
        self.assertEqual(message.provider_reference, 'graph-request-42')
        self.assertEqual(post.call_count, 2)
        token_call, send_call = post.call_args_list
        self.assertIn('tenant/oauth2/v2.0/token', token_call.args[0])
        self.assertEqual(token_call.kwargs['data']['client_secret'], 'secret')
        self.assertIn('/users/sender@example.test/sendMail', send_call.args[0])
        self.assertEqual(send_call.kwargs['headers']['Authorization'], 'Bearer access-token')
        self.assertNotIn('secret', json.dumps(send_call.kwargs['json']))

    @patch('apps.notifications.tasks.queue_email')
    def test_license_reminder_is_idempotent_for_same_expiry(self, queue_email_mock):
        from datetime import timedelta
        from apps.catalog.models import Product
        from apps.licenses.models import License, LicenseAssignment, LicenseReminder
        from apps.notifications.tasks import schedule_license_reminders

        user = User.objects.create_user(
            'reminder@example.test', None, email_verified_at=timezone.now()
        )
        product = Product.objects.create(
            code='REMINDER-TEST',
            name='Reminder Test',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        now = timezone.now()
        license_obj = License.objects.create(
            owner_user=user,
            product=product,
            status='active',
            valid_from=now - timedelta(days=305),
            valid_until=now + timedelta(days=60),
        )
        LicenseAssignment.objects.create(license=license_obj, user=user)

        first = schedule_license_reminders.run()
        second = schedule_license_reminders.run()

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        reminder = LicenseReminder.objects.get(license=license_obj, kind='t60')
        self.assertEqual(reminder.status, 'queued')
        self.assertEqual(queue_email_mock.call_count, 1)
        args = queue_email_mock.call_args.args
        self.assertEqual(args[0], 't60')
        self.assertEqual(args[1], user.email)

class PortalTenantIsolationHttpTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PORTAL-IDOR-PRO',
            name='Portal IDOR Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company_a = Company.objects.create(
            customer_number='PM-IDOR-A',
            name='Tenant A GmbH',
            email='tenant-a@example.test',
            country='DE',
        )
        self.company_b = Company.objects.create(
            customer_number='PM-IDOR-B',
            name='Tenant B GmbH',
            email='tenant-b@example.test',
            country='DE',
        )
        self.admin_a = User.objects.create_user(
            'admin-a@example.test',
            'Portal-Idor-Password-42!',
            first_name='Admin',
            last_name='A',
            email_verified_at=self.now,
        )
        self.member_a = User.objects.create_user(
            'member-a@example.test',
            'Portal-Idor-Password-42!',
            first_name='Member',
            last_name='A',
            email_verified_at=self.now,
        )
        self.member_b = User.objects.create_user(
            'member-b@example.test',
            'Portal-Idor-Password-42!',
            first_name='Member',
            last_name='B',
            email_verified_at=self.now,
        )
        Membership.objects.create(
            company=self.company_a,
            user=self.admin_a,
            role='admin',
            active=True,
        )
        self.member_a_membership = Membership.objects.create(
            company=self.company_a,
            user=self.member_a,
            role='member',
            active=True,
        )
        Membership.objects.create(
            company=self.company_b,
            user=self.member_b,
            role='admin',
            active=True,
        )
        # Realistic historical state: the user used to belong to tenant B, but
        # an old tenant-B license/device still exists after moving to tenant A.
        Membership.objects.create(
            company=self.company_b,
            user=self.member_a,
            role='member',
            active=False,
        )
        self.foreign_license = License.objects.create(
            company=self.company_b,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        LicenseAssignment.objects.create(
            license=self.foreign_license,
            user=self.member_a,
        )
        self.foreign_device = DeviceRegistration.objects.create(
            user=self.member_a,
            license=self.foreign_license,
            token_hash='a' * 64,
            display_name='FOREIGN-TENANT-DEVICE',
            last_seen_at=self.now,
        )
        self._login(self.admin_a)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_foreign_team_member_direct_url_is_not_found(self):
        response = self.client.get(f'/portal/team/{self.member_b.id}/')
        self.assertEqual(response.status_code, 404)

    def test_foreign_company_license_cannot_be_renewed_by_admin(self):
        response = self.client.get(f'/portal/licenses/{self.foreign_license.id}/renew/')
        self.assertEqual(response.status_code, 403)

    def test_company_admin_device_views_hide_foreign_tenant_device(self):
        response = self.client.get('/portal/devices/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.foreign_device.display_name)

        response = self.client.get(f'/portal/team/{self.member_a.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.foreign_device.display_name)

    def test_company_member_device_list_hides_foreign_tenant_device(self):
        self._login(self.member_a)
        response = self.client.get('/portal/devices/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.foreign_device.display_name)

    def test_company_admin_cannot_revoke_foreign_tenant_device(self):
        response = self.client.post(f'/portal/devices/{self.foreign_device.id}/revoke/')
        self.assertEqual(response.status_code, 404)
        self.foreign_device.refresh_from_db()
        self.assertIsNone(self.foreign_device.revoked_at)

    def test_member_deactivation_does_not_revoke_foreign_tenant_device(self):
        response = self.client.post(f'/portal/team/{self.member_a.id}/deactivate/')
        self.assertEqual(response.status_code, 302)
        self.foreign_device.refresh_from_db()
        self.assertIsNone(self.foreign_device.revoked_at)

    def test_member_cannot_open_admin_only_portal_areas_or_post_admin_action(self):
        self._login(self.member_a)
        for path in (
            '/portal/team/',
            '/portal/team/invitations/',
            '/portal/company/',
            '/portal/orders/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(
            self.client.post(f'/portal/team/{self.admin_a.id}/deactivate/').status_code,
            403,
        )

@tag('datagrid_100k')
class DataGridLargeDatasetGateTests(TestCase):
    ROW_COUNT = 100_000
    BATCH_SIZE = 1_000

    def test_last_page_uses_bounded_queries_and_sql_limit_offset(self):
        for start in range(0, self.ROW_COUNT, self.BATCH_SIZE):
            Company.objects.bulk_create(
                [
                    Company(
                        customer_number=f'LOAD-{index:06d}',
                        name=f'Lasttest {index:06d}',
                        email='load-test@example.test',
                        country='DE',
                    )
                    for index in range(start, start + self.BATCH_SIZE)
                ],
                batch_size=self.BATCH_SIZE,
            )

        request = RequestFactory().get(
            '/ns-admin/customers/',
            {'page': '2000', 'page_size': '50'},
        )

        with CaptureQueriesContext(connection) as queries:
            grid = DataGrid(
                request,
                Company.objects.all(),
                sort_fields={'number': 'customer_number'},
                default_sort='customer_number',
            ).build()
            rows = list(grid.page.object_list)

        self.assertEqual(grid.page.paginator.count, self.ROW_COUNT)
        self.assertEqual(grid.page.number, 2000)
        self.assertEqual(len(rows), 50)
        self.assertLessEqual(
            len(queries.captured_queries),
            3,
            queries.captured_queries,
        )

        sql = [
            query['sql'].upper().replace('\n', ' ')
            for query in queries.captured_queries
        ]
        self.assertTrue(
            any(
                'LIMIT 50' in statement
                and 'OFFSET 99950' in statement
                for statement in sql
            ),
            sql,
        )

