import json
import os
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from unittest import skipUnless
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.integrations.models import ServiceAccount
from apps.companies.models import Company
from apps.legal.models import DeletionRequest
from .middleware import CorrelationIdMiddleware, JsonLogFormatter
from .datagrid import DataGrid, csv_response
from .security import token_hash, token_pair
from .sensitive import SENSITIVE_REAUTH_SESSION_KEY


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
            two_factor_required=True,
            totp_secret_enc='configured-service-account-test-secret',
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.user)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session[SENSITIVE_REAUTH_SESSION_KEY] = now
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
        EmailTemplate.objects.create(
            code='t60',
            subject='Lizenz-Erinnerung',
            body_text='Lizenz {license} endet am {expiry}.',
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

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_license_reminder_is_idempotent_for_same_expiry(self, delay):
        from datetime import timedelta
        from apps.catalog.models import Product
        from apps.licenses.models import License, LicenseAssignment, LicenseReminder
        from apps.notifications.models import EmailMessage
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

        with self.captureOnCommitCallbacks(execute=True):
            first = schedule_license_reminders.run()
        with self.captureOnCommitCallbacks(execute=True):
            second = schedule_license_reminders.run()

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        reminder = LicenseReminder.objects.get(license=license_obj, kind='t60')
        self.assertEqual(reminder.status, 'queued')
        message = EmailMessage.objects.get(context__reminder_id=str(reminder.id))
        self.assertEqual(message.recipient, user.email)
        self.assertEqual(message.context.get('pm_scope_user_id'), str(user.id))
        self.assertEqual(delay.call_count, 1)


class DataGridAcceptanceTests(TestCase):
    def _companies(self, count):
        Company.objects.bulk_create(
            [
                Company(
                    customer_number=f'DG-{i:06d}',
                    name=f'Company {i:06d}',
                    email=f'company-{i}@example.test',
                    status='active' if i % 2 == 0 else 'inactive',
                )
                for i in range(count)
            ],
            batch_size=1000,
        )

    def _grid(self, params=None):
        request = RequestFactory().get('/ns-admin/customers/', params or {})
        return DataGrid(
            request,
            Company.objects.all(),
            search_fields=('customer_number', 'name', 'email'),
            sort_fields={'name': 'name', 'number': 'customer_number'},
            default_sort='customer_number',
            filters={'status': 'status'},
        ).build()

    def test_default_pagination_boundaries_0_1_49_50_51(self):
        for count, pages, first_page_count in [
            (0, 1, 0),
            (1, 1, 1),
            (49, 1, 49),
            (50, 1, 50),
            (51, 2, 50),
        ]:
            Company.objects.all().delete()
            self._companies(count)
            grid = self._grid()
            self.assertEqual(grid.page.paginator.count, count)
            self.assertEqual(grid.page.paginator.num_pages, pages)
            self.assertEqual(len(grid.page.object_list), first_page_count)
            self.assertEqual(grid.page_size, 50)
            self.assertTrue(
                any(item['current'] and item['number'] == 1 for item in grid.navigation)
            )

    def test_page_size_search_filter_sort_and_deep_link_state(self):
        self._companies(120)
        grid = self._grid(
            {
                'q': 'Company',
                'status': 'active',
                'sort': 'name',
                'dir': 'desc',
                'page': '2',
                'page_size': '25',
            }
        )
        self.assertEqual(grid.page_size, 25)
        self.assertEqual(grid.page.number, 2)
        self.assertEqual(grid.page.paginator.count, 60)
        self.assertEqual(grid.sort, 'name')
        self.assertEqual(grid.direction, 'desc')
        self.assertTrue(grid.has_state)
        names = [row.name for row in grid.page.object_list]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_invalid_page_size_and_sort_fail_closed_to_defaults(self):
        self._companies(3)
        grid = self._grid({'page_size': '999999', 'sort': 'not-a-column', 'dir': 'desc'})
        self.assertEqual(grid.page_size, 50)
        self.assertEqual(grid.sort, '')
        self.assertEqual(grid.direction, 'asc')
        numbers = [row.customer_number for row in grid.page.object_list]
        self.assertEqual(numbers, sorted(numbers))

    def test_filtered_csv_export_is_bounded_and_formula_safe(self):
        Company.objects.create(
            customer_number='DG-CSV-1',
            name='=2+2',
            email='csv@example.test',
            status='active',
        )
        grid = self._grid({'status': 'active'})
        response = csv_response(
            grid.queryset,
            [('customer_number', 'Kundennummer'), ('name', 'Name')],
            'customers.csv',
        )
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('DG-CSV-1', body)
        self.assertIn("'=2+2", body)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_5000_rows_remain_server_paginated(self):
        self._companies(5000)
        grid = self._grid({'page': '100', 'page_size': '50'})
        self.assertEqual(grid.page.paginator.count, 5000)
        self.assertEqual(grid.page.paginator.num_pages, 100)
        self.assertEqual(grid.page.number, 100)
        self.assertEqual(len(grid.page.object_list), 50)


@skipUnless(
    os.environ.get('RUN_100K_DATAGRID_ACCEPTANCE') == '1',
    '100k DataGrid acceptance is an explicit staging/performance gate.',
)
class DataGrid100kAcceptanceTests(DataGridAcceptanceTests):
    def test_100000_rows_paginate_without_unbounded_result_materialization(self):
        self._companies(100000)
        with CaptureQueriesContext(connection) as queries:
            grid = self._grid({'page': '2000', 'page_size': '50'})
            rows = list(grid.page.object_list)

        self.assertEqual(grid.page.paginator.count, 100000)
        self.assertEqual(grid.page.paginator.num_pages, 2000)
        self.assertEqual(len(rows), 50)
        self.assertLessEqual(
            len(queries),
            3,
            f'100k pagination issued too many SQL queries: {[q["sql"] for q in queries]}',
        )
        select_sql = ' '.join(q['sql'] for q in queries if 'SELECT' in q['sql'].upper())
        self.assertIn('LIMIT 50', select_sql.upper())
        self.assertIn('OFFSET 99950', select_sql.upper())
