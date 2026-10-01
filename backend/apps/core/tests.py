from datetime import timedelta
import json
import os
import logging
from pathlib import Path
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
from apps.catalog.models import Product
from apps.integrations.models import ServiceAccount
from apps.companies.models import Company
from apps.legal.models import DeletionRequest
from apps.licenses.models import License
from apps.orders.models import Order
from .middleware import CorrelationIdMiddleware, JsonLogFormatter
from .datagrid import DataGrid, csv_response
from .security import token_hash, token_pair
from .sensitive import SENSITIVE_REAUTH_SESSION_KEY


class AdminFormSpacingCssContractTests(SimpleTestCase):
    def test_global_form_spacing_contract_prevents_control_text_overlap(self):
        from django.conf import settings

        css = (
            Path(settings.BASE_DIR) / 'static' / 'css' / 'app.css'
        ).read_text(encoding='utf-8')

        self.assertIn('System-wide admin form spacing contract', css)
        self.assertIn('.form label{', css)
        self.assertIn('display:grid;', css)
        self.assertIn('.form label:has(>input[type=checkbox])', css)
        self.assertIn('inline-size:18px;', css)
        self.assertIn('margin:0!important;', css)
        self.assertIn('.form .row{', css)
        self.assertIn('row-gap:14px;', css)


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


class MailIdentitySettingsTests(TestCase):
    def test_runtime_mail_identity_falls_back_to_environment_sender(self):
        from apps.notifications.services import get_mail_identity

        with self.settings(DEFAULT_FROM_EMAIL='fallback@example.test'):
            identity = get_mail_identity()

        self.assertEqual(identity['from_email'], 'fallback@example.test')
        self.assertEqual(identity['from_name'], '')
        self.assertEqual(identity['reply_to'], '')

    def test_smtp_delivery_uses_runtime_sender_name_and_reply_to(self):
        from apps.core.settings_store import set_setting
        from apps.notifications.services import _send_smtp

        set_setting(
            'mail_identity',
            {
                'from_email': 'promptmaster@decke-wand-boden.de',
                'from_name': 'PromptMaster',
                'reply_to': 'support@decke-wand-boden.de',
                'domain': 'decke-wand-boden.de',
                'spf_record': 'v=spf1 include:spf.protection.outlook.com -all',
                'dkim_selector': 'selector1 / selector2',
                'dkim_record': 'selector1._domainkey CNAME example',
                'dmarc_record': 'v=DMARC1; p=reject',
            },
        )
        message = SimpleNamespace(
            id='smtp-test-42',
            subject='PromptMaster SMTP identity test',
            recipient='recipient@example.test',
        )

        with patch('apps.notifications.services.get_connection') as get_connection:
            connection = get_connection.return_value
            with patch('apps.notifications.services.DjangoEmailMessage') as email_class:
                email = email_class.return_value
                _send_smtp(message, 'body')

        get_connection.assert_called_once_with(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host='mailpit',
            port=1025,
            username=None,
            password=None,
            use_tls=False,
            timeout=20,
        )
        email_class.assert_called_once_with(
            subject='PromptMaster SMTP identity test',
            body='body',
            from_email='PromptMaster <promptmaster@decke-wand-boden.de>',
            to=['recipient@example.test'],
            reply_to=['support@decke-wand-boden.de'],
            headers={'Message-ID': '<smtp-test-42@decke-wand-boden.de>'},
            connection=connection,
        )
        email.send.assert_called_once_with(fail_silently=False)

    def test_smtp_message_id_falls_back_to_from_domain(self):
        from apps.notifications.services import _smtp_message_id

        message = SimpleNamespace(id='message-123')
        identity = {
            'domain': '',
            'from_email': 'promptmaster@decke-wand-boden.de',
        }

        self.assertEqual(
            _smtp_message_id(message, identity),
            '<message-123@decke-wand-boden.de>',
        )

    def test_general_settings_form_validates_sender_domain_and_dns_records(self):
        from apps.core.admin_forms import GeneralSettingsForm

        data = {
            'support_email': 'support@example.test',
            'mail_from_email': 'promptmaster@decke-wand-boden.de',
            'mail_from_name': 'PromptMaster',
            'mail_reply_to': '',
            'mail_domain': 'promptmaster.ai',
            'mail_spf_record': 'include:spf.protection.outlook.com',
            'mail_dkim_selector': '',
            'mail_dkim_record': '',
            'mail_dmarc_record': 'p=reject',
            'disk_warning': 80,
            'disk_critical': 90,
            'ram_warning': 80,
            'ram_critical': 90,
            'cpu_warning': 80,
            'backup_warning_hours': 8,
            'backup_critical_hours': 24,
            'restore_warning_days': 35,
        }
        form = GeneralSettingsForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn('mail_domain', form.errors)
        self.assertIn('mail_spf_record', form.errors)
        self.assertIn('mail_dmarc_record', form.errors)


    def test_runtime_provider_and_graph_transport_use_db_settings(self):
        from apps.core.settings_store import set_setting
        from apps.integrations.services import set_secret
        from apps.notifications.services import get_graph_transport, get_mail_provider

        set_setting('mail_provider', 'graph')
        set_setting(
            'mail_graph',
            {
                'tenant_id': 'tenant-runtime',
                'client_id': 'client-runtime',
                'sender': 'promptmaster@netstyle.de',
            },
        )
        set_secret('graph_client_secret', 'Graph-Test-Secret-2026!')

        self.assertEqual(get_mail_provider(), 'graph')
        graph = get_graph_transport()
        self.assertEqual(graph['tenant_id'], 'tenant-runtime')
        self.assertEqual(graph['client_id'], 'client-runtime')
        self.assertEqual(graph['sender'], 'promptmaster@netstyle.de')
        self.assertEqual(graph['client_secret'], 'Graph-Test-Secret-2026!')
        self.assertTrue(graph['client_secret_configured'])

    def test_graph_provider_requires_non_secret_identifiers_in_form(self):
        from apps.core.admin_forms import GeneralSettingsForm

        form = GeneralSettingsForm(
            data={
                'support_email': 'support@example.test',
                'mail_provider': 'graph',
                'mail_from_email': 'promptmaster@netstyle.de',
                'mail_from_name': 'PromptMaster',
                'mail_reply_to': '',
                'mail_domain': 'netstyle.de',
                'mail_spf_record': '',
                'mail_dkim_selector': '',
                'mail_dkim_record': '',
                'mail_dmarc_record': '',
                'smtp_host': '',
                'smtp_port': '',
                'smtp_username': '',
                'graph_tenant_id': '',
                'graph_client_id': '',
                'graph_sender': '',
                'disk_warning': 80,
                'disk_critical': 90,
                'ram_warning': 80,
                'ram_critical': 90,
                'cpu_warning': 80,
                'backup_warning_hours': 8,
                'backup_critical_hours': 24,
                'restore_warning_days': 35,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('graph_tenant_id', form.errors)
        self.assertIn('graph_client_id', form.errors)
        self.assertIn('graph_sender', form.errors)

    def test_mail_delivery_builds_ordered_failover_route(self):
        from apps.core.settings_store import set_setting
        from apps.notifications.services import get_mail_delivery

        set_setting('mail_provider', 'graph')
        set_setting(
            'mail_delivery',
            {
                'mode': 'failover',
                'primary': 'graph',
                'fallback_1': 'smtp1',
                'fallback_2': 'smtp2',
            },
        )

        delivery = get_mail_delivery()

        self.assertEqual(delivery['mode'], 'failover')
        self.assertEqual(delivery['route'], ['graph', 'smtp1', 'smtp2'])

    def test_smtp2_transport_uses_separate_encrypted_secret(self):
        from apps.core.settings_store import set_setting
        from apps.integrations.services import set_secret
        from apps.notifications.services import get_smtp_transport

        set_setting(
            'mail_transport_2',
            {
                'host': 'smtp.fallback.example.test',
                'port': 587,
                'use_tls': True,
                'username': 'fallback@example.test',
            },
        )
        set_secret('smtp_password_2', 'SMTP2-Test-Secret-2026!')

        transport = get_smtp_transport('smtp2')

        self.assertEqual(transport['slot'], 'smtp2')
        self.assertEqual(transport['host'], 'smtp.fallback.example.test')
        self.assertEqual(transport['port'], 587)
        self.assertTrue(transport['use_tls'])
        self.assertEqual(transport['username'], 'fallback@example.test')
        self.assertEqual(transport['password'], 'SMTP2-Test-Secret-2026!')
        self.assertTrue(transport['password_configured'])

    @patch('apps.notifications.services._send_smtp')
    @patch('apps.notifications.services._send_graph')
    def test_safe_graph_failure_falls_back_to_smtp1(self, send_graph, send_smtp):
        from apps.core.settings_store import set_setting
        from apps.notifications.models import EmailMessage
        from apps.notifications.services import SafeMailFailoverError, send_now

        set_setting(
            'mail_delivery',
            {
                'mode': 'failover',
                'primary': 'graph',
                'fallback_1': 'smtp1',
                'fallback_2': 'smtp2',
            },
        )
        send_graph.side_effect = SafeMailFailoverError('graph', 'token endpoint unavailable')
        send_smtp.return_value = ''
        message = EmailMessage.objects.create(
            recipient='recipient@example.test',
            subject='Failover test',
            context={},
        )

        send_now(message)

        message.refresh_from_db()
        self.assertEqual(message.status, 'sent')
        self.assertEqual(message.provider_used, 'smtp1')
        self.assertEqual(
            message.delivery_attempts,
            [
                {
                    'provider': 'graph',
                    'result': 'failed-safe',
                    'error': 'token endpoint unavailable',
                },
                {'provider': 'smtp1', 'result': 'sent'},
            ],
        )
        send_smtp.assert_called_once_with(message, '', 'smtp1')

    @patch('apps.notifications.services._send_smtp')
    @patch('apps.notifications.services._send_graph')
    def test_ambiguous_graph_failure_does_not_fail_over(self, send_graph, send_smtp):
        from apps.core.settings_store import set_setting
        from apps.notifications.models import EmailMessage
        from apps.notifications.services import send_now

        set_setting(
            'mail_delivery',
            {
                'mode': 'failover',
                'primary': 'graph',
                'fallback_1': 'smtp1',
                'fallback_2': 'smtp2',
            },
        )
        send_graph.side_effect = RuntimeError('connection lost after send request')
        message = EmailMessage.objects.create(
            recipient='recipient@example.test',
            subject='Ambiguous failover test',
            context={},
        )

        with self.assertRaises(RuntimeError):
            send_now(message)

        message.refresh_from_db()
        self.assertEqual(
            message.delivery_attempts,
            [{'provider': 'graph', 'result': 'failed-uncertain'}],
        )
        send_smtp.assert_not_called()

    def test_smtp_authentication_error_is_failover_safe(self):
        import smtplib
        from apps.notifications.services import _smtp_error_allows_failover

        exc = smtplib.SMTPAuthenticationError(535, b'Authentication failed')
        self.assertTrue(_smtp_error_allows_failover(exc))

    def test_smtp_temporary_4xx_is_failover_safe_but_permanent_5xx_is_not(self):
        import smtplib
        from apps.notifications.services import _smtp_error_allows_failover

        self.assertTrue(
            _smtp_error_allows_failover(
                smtplib.SMTPDataError(451, b'Temporary local problem')
            )
        )
        self.assertFalse(
            _smtp_error_allows_failover(
                smtplib.SMTPDataError(550, b'Permanent rejection')
            )
        )
        self.assertTrue(
            _smtp_error_allows_failover(
                smtplib.SMTPRecipientsRefused(
                    {'recipient@example.test': (450, b'Mailbox busy')}
                )
            )
        )
        self.assertFalse(
            _smtp_error_allows_failover(
                smtplib.SMTPRecipientsRefused(
                    {'recipient@example.test': (550, b'Unknown user')}
                )
            )
        )

    def test_smtp_transport_uses_encrypted_secret_and_runtime_settings(self):
        from apps.core.settings_store import set_setting
        from apps.integrations.services import set_secret
        from apps.notifications.services import get_smtp_transport

        set_setting(
            'mail_transport',
            {
                'host': 'smtp.ionos.de',
                'port': 587,
                'use_tls': True,
                'username': 'promptmaster@decke-wand-boden.de',
            },
        )
        set_secret('smtp_password', 'SMTP-Test-Secret-2026!')

        transport = get_smtp_transport()

        self.assertEqual(transport['host'], 'smtp.ionos.de')
        self.assertEqual(transport['port'], 587)
        self.assertTrue(transport['use_tls'])
        self.assertEqual(
            transport['username'],
            'promptmaster@decke-wand-boden.de',
        )
        self.assertEqual(transport['password'], 'SMTP-Test-Secret-2026!')
        self.assertTrue(transport['password_configured'])


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
        send_response.status_code = 202
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


class AdminDashboardRegressionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'dashboard-admin@example.test',
            None,
            is_staff=True,
            is_superuser=True,
            two_factor_required=False,
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.admin)
        session = self.client.session
        now_ts = timezone.now().timestamp()
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now_ts
        session['last_activity_at'] = now_ts
        session.save()
        self.company = Company.objects.create(
            customer_number='DASH-1001',
            name='Dashboard GmbH',
            email='dashboard@example.test',
            status='active',
        )
        self.product = Product.objects.create(code='DASH-PRO', name='PromptMaster Pro Test')
        now = timezone.now()
        License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=now - timedelta(days=10),
            valid_until=now + timedelta(days=100),
        )
        License.objects.create(
            company=self.company,
            product=self.product,
            status='expired',
            valid_from=now - timedelta(days=400),
            valid_until=now - timedelta(days=1),
        )
        Order.objects.create(
            order_number='DASH-ORDER-1',
            company=self.company,
            status='paid',
            gross_total='35.88',
            tax_total='5.73',
            idempotency_key='dashboard-order-1',
        )

    @patch('apps.core.admin_views.snapshot', return_value={})
    def test_dashboard_css_percentages_are_locale_neutral_and_counts_align(self, _snapshot):
        response = self.client.get('/ns-admin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['licenses'], 1)
        self.assertEqual(response.context['product_total'], 1)
        self.assertEqual(response.context['product_mix'][0]['percent_css'], '100.0')
        self.assertEqual(response.context['revenue_months'][0]['percent_css'], '100.0')
        body = response.content.decode('utf-8')
        self.assertIn('height:100.0%', body)
        self.assertIn('--share:100.0%', body)
        self.assertNotIn('height:100,0%', body)
        self.assertNotIn('--share:100,0%', body)
        self.assertIn('alert-stack', body)


class AdminOrderGridTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'orders-admin@example.test',
            None,
            is_staff=True,
            is_superuser=True,
            two_factor_required=False,
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.admin)
        session = self.client.session
        now_ts = timezone.now().timestamp()
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now_ts
        session['last_activity_at'] = now_ts
        session.save()
        self.company = Company.objects.create(
            customer_number='ORD-COMPANY',
            name='Alpha GmbH',
            email='alpha@example.test',
            status='active',
        )
        self.private_user = User.objects.create_user(
            'zeta.private@example.test',
            None,
            email_verified_at=timezone.now(),
        )
        Order.objects.create(
            order_number='ORD-C-1',
            company=self.company,
            gross_total='10.00',
            tax_total='1.60',
            idempotency_key='order-company-1',
        )
        Order.objects.create(
            order_number='ORD-P-1',
            private_user=self.private_user,
            gross_total='20.00',
            tax_total='3.19',
            idempotency_key='order-private-1',
        )

    def test_customer_column_sorts_company_and_private_orders_and_can_reset(self):
        response = self.client.get('/ns-admin/orders/?sort=customer&dir=asc')
        self.assertEqual(response.status_code, 200)
        rows = list(response.context['grid'].page.object_list)
        self.assertEqual(
            [row.customer_display for row in rows],
            ['Alpha GmbH', 'zeta.private@example.test'],
        )
        body = response.content.decode('utf-8')
        self.assertIn('sort=customer', body)
        self.assertIn('Sortierung zurücksetzen', body)
        self.assertIn('Alles zurücksetzen', body)
        self.assertIn('Alpha GmbH', body)
        self.assertIn('zeta.private@example.test', body)


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


class MollieAdminPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'mollie-admin-page@example.test',
            None,
            is_staff=True,
            is_superuser=True,
            two_factor_required=True,
            totp_secret_enc='configured-mollie-admin-test-secret',
            email_verified_at=timezone.now(),
        )
        self.client.force_login(self.user)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session.save()

    def test_mollie_overview_renders_without_optional_webhook_setting(self):
        response = self.client.get('/ns-admin/mollie/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>Mollie</h1>', html=True)
        self.assertEqual(response.context['webhook_base'], 'http://testserver')


class MonitoringScopeTests(SimpleTestCase):
    @patch('apps.ops.metrics.query_labels')
    @patch('apps.ops.metrics.query_value')
    def test_snapshot_separates_vm_and_container_metrics(self, query_value, query_labels):
        from apps.ops.metrics import snapshot

        values = {
            '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[1m]))*100)': 12.5,
            '100-(avg(rate(node_cpu_seconds_total{mode="idle"}[10m]))*100)': 10.0,
            'node_memory_MemTotal_bytes': 16 * 1024**3,
            'node_memory_MemAvailable_bytes': 9 * 1024**3,
            'node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 500 * 1024**3,
            'node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 300 * 1024**3,
            'node_filesystem_files{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 10000,
            'node_filesystem_files_free{mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}': 9500,
            'time()-node_boot_time_seconds': 3600,
            'node_load1': 0.5,
            'node_load5': 0.4,
            'node_load15': 0.3,
            'count(container_last_seen{image!=""})': 12,
            'sum(container_memory_working_set_bytes{image!=""})': 3 * 1024**3,
            'sum(rate(container_cpu_usage_seconds_total{image!=""}[1m]))': 1.25,
        }
        query_value.side_effect = lambda expression: values.get(expression)

        def labels(expression):
            if expression == 'node_uname_info':
                return {
                    'nodename': 'promptmaster-vm',
                    'release': '6.8.0',
                    'sysname': 'Linux',
                    'machine': 'x86_64',
                }
            if expression == 'cadvisor_version_info':
                return {'dockerVersion': '28.0.0'}
            return {}

        query_labels.side_effect = labels
        data = snapshot()

        self.assertEqual(data['scope'], 'vm')
        self.assertEqual(data['scope_label'], 'Docker-Host-VM')
        self.assertEqual(data['memory_total'], 16 * 1024**3)
        self.assertEqual(data['memory_available'], 9 * 1024**3)
        self.assertEqual(data['memory_used'], 7 * 1024**3)
        self.assertAlmostEqual(data['memory_percent'], 43.75)
        self.assertEqual(data['disk_used'], 200 * 1024**3)
        self.assertAlmostEqual(data['inode_percent'], 5.0)
        self.assertEqual(data['container_count'], 12)
        self.assertEqual(data['container_memory_used'], 3 * 1024**3)
        self.assertEqual(data['container_cpu_cores'], 1.25)
        self.assertEqual(data['host']['hostname'], 'promptmaster-vm')
        self.assertEqual(data['docker_version'], '28.0.0')
