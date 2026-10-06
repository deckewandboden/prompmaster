import json
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import requests

from django.core.management import call_command
from django.core.management.base import CommandError
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.management.commands.external_graph_acceptance import INVALID_SENDER
from apps.core.management.commands.external_mollie_acceptance import Command as MollieAcceptanceCommand
from apps.core.models import SystemSetting
from apps.notifications.models import EmailMessage


class ExternalAcceptanceSafetyTests(TestCase):

    def test_graph_acceptance_requires_explicit_confirmation(self):
        with self.assertRaises(CommandError):
            call_command(
                'external_graph_acceptance',
                recipient='probe@example.test',
                confirm='WRONG',
                stdout=StringIO(),
            )

    @override_settings(
        EMAIL_PROVIDER='graph',
        GRAPH_TENANT_ID='',
        GRAPH_CLIENT_ID='',
        GRAPH_CLIENT_SECRET='',
        GRAPH_SENDER='',
    )
    def test_graph_acceptance_refuses_missing_configuration(self):
        with self.assertRaises(CommandError):
            call_command(
                'external_graph_acceptance',
                recipient='probe@example.test',
                confirm='SEND-GRAPH-ACCEPTANCE',
                stdout=StringIO(),
            )

    @override_settings(MOLLIE_API_KEY='')
    def test_mollie_acceptance_refuses_live_key(self):
        live_key = 'li' + 've_' + 'not_allowed'
        with patch('apps.integrations.services.get_secret', return_value=live_key):
            with self.assertRaises(CommandError):
                call_command(
                    'external_mollie_acceptance',
                    'verify',
                    payment_id='tr_dummy',
                    stdout=StringIO(),
                )

    def test_mollie_acceptance_refuses_non_public_webhook_bases(self):
        command = MollieAcceptanceCommand()
        for base_url in (
            'https://localhost',
            'https://127.0.0.1',
            'https://10.20.30.40',
            'https://promptmaster.local',
            'https://promptmaster.example.test',
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(CommandError):
                    command._base_url({'base_url': base_url})

    def test_mollie_acceptance_allows_public_https_hostname(self):
        parsed = MollieAcceptanceCommand()._base_url(
            {'base_url': 'https://promptmaster-staging.netstyle.de'}
        )
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'promptmaster-staging.netstyle.de')

    @override_settings(MOLLIE_API_KEY='')
    def test_mollie_start_requires_explicit_confirmation(self):
        test_key = 'te' + 'st_' + 'safe'
        with patch('apps.integrations.services.get_secret', return_value=test_key):
            with self.assertRaises(CommandError):
                call_command(
                    'external_mollie_acceptance',
                    'start',
                    user_email='probe@example.test',
                    base_url='https://promptmaster.example.test',
                    stdout=StringIO(),
                )

    @override_settings(MOLLIE_API_KEY='')
    def test_mollie_refund_requires_explicit_confirmation(self):
        test_key = 'te' + 'st_' + 'safe'
        with patch('apps.integrations.services.get_secret', return_value=test_key):
            with self.assertRaises(CommandError):
                call_command(
                    'external_mollie_acceptance',
                    'refund',
                    payment_id='tr_dummy',
                    confirm='WRONG',
                    stdout=StringIO(),
                )


    def test_mollie_live_activation_requires_explicit_confirmation(self):
        with self.assertRaisesMessage(
            CommandError,
            'Refusing to enable live checkout',
        ):
            call_command(
                'external_mollie_acceptance',
                'activate-live',
                confirm='WRONG',
                stdout=StringIO(),
            )
        self.assertFalse(
            SystemSetting.objects.filter(
                key='mollie_checkout_enabled',
                value=True,
            ).exists()
        )

    def test_mollie_live_activation_sets_gate_only_after_successful_probe(self):
        fake = MagicMock()
        fake.key = 'live_runtime_secret'
        fake.get_current_profile.return_value = {
            'resource': 'profile',
            'id': 'pfl_runtime',
            'mode': 'live',
            'name': 'PROMPTFINISHER',
            'status': 'verified',
            'review': None,
        }
        fake.list_methods.return_value = {
            '_embedded': {
                'methods': [
                    {'id': 'creditcard', 'status': 'activated'},
                ]
            }
        }
        out = StringIO()
        with (
            patch(
                'apps.core.management.commands.external_mollie_acceptance.MollieClient',
                return_value=fake,
            ),
            patch(
                'apps.core.management.commands.external_mollie_acceptance.get_setting',
                return_value='pfl_runtime',
            ),
        ):
            call_command(
                'external_mollie_acceptance',
                'activate-live',
                confirm='ENABLE-MOLLIE-LIVE-CHECKOUT',
                stdout=out,
            )

        gate = SystemSetting.objects.get(key='mollie_checkout_enabled')
        self.assertIs(gate.value, True)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload['checkout_enabled'])
        self.assertEqual(payload['profile_status'], 'verified')
        self.assertEqual(payload['activated_methods'], ['creditcard'])
        fake.get_current_profile.assert_called_once_with()
        fake.list_methods.assert_called_once_with()


class MollieAdminCheckoutGateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='mollie-admin@example.test',
            password='Mollie-Admin-Password-2026!',
            first_name='Mollie',
            last_name='Admin',
            email_verified_at=timezone.now(),
            two_factor_required=False,
        )
        self.client.force_login(self.admin)
        session = self.client.session
        session['security_version'] = self.admin.security_version
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()

    def test_mollie_admin_shows_and_executes_checkout_emergency_stop(self):
        SystemSetting.objects.update_or_create(
            key='mollie_checkout_enabled',
            defaults={'value': True},
        )

        page = self.client.get('/ns-admin/mollie/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Produktiv-Checkout sperren')
        self.assertContains(page, '/ns-admin/mollie/checkout/disable/')

        response = self.client.post('/ns-admin/mollie/checkout/disable/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/ns-admin/mollie/')
        gate = SystemSetting.objects.get(key='mollie_checkout_enabled')
        self.assertIs(gate.value, False)

    def test_mollie_checkout_emergency_stop_refuses_get(self):
        SystemSetting.objects.update_or_create(
            key='mollie_checkout_enabled',
            defaults={'value': True},
        )
        response = self.client.get('/ns-admin/mollie/checkout/disable/')
        self.assertEqual(response.status_code, 405)
        gate = SystemSetting.objects.get(key='mollie_checkout_enabled')
        self.assertIs(gate.value, True)


@override_settings(
    EMAIL_PROVIDER='graph',
    GRAPH_TENANT_ID='tenant-test',
    GRAPH_CLIENT_ID='client-test',
    GRAPH_CLIENT_SECRET='secret-test',
    GRAPH_SENDER='sender@example.test',
)
class ExternalGraphAcceptanceFlowTests(TestCase):

    @patch('apps.notifications.services._send_graph')
    def test_graph_acceptance_uses_persisted_success_and_real_retry_state_path(self, send_graph):
        def provider(message, _body):
            from apps.notifications.services import get_graph_transport

            if get_graph_transport()['sender'] == INVALID_SENDER:
                response = requests.Response()
                response.status_code = 404
                response.url = 'https://graph.microsoft.com/v1.0/users/invalid/sendMail'
                raise requests.HTTPError('Graph sender not found', response=response)
            return 'req-success-123'

        send_graph.side_effect = provider
        stdout = StringIO()
        call_command(
            'external_graph_acceptance',
            recipient='probe@example.test',
            confirm='SEND-GRAPH-ACCEPTANCE',
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['request_id'], 'req-success-123')
        self.assertEqual(payload['provider_failure_status'], 404)
        self.assertEqual(payload['retry_count'], 1)

        success = EmailMessage.objects.get(pk=payload['success_message_id'])
        failure = EmailMessage.objects.get(pk=payload['failure_message_id'])
        self.assertEqual(success.status, 'sent')
        self.assertEqual(success.provider_reference, 'req-success-123')
        self.assertEqual(failure.status, 'failed')
        self.assertEqual(failure.retry_count, 1)



class ExternalMollieAcceptanceInvariantTests(SimpleTestCase):

    def test_mollie_acceptance_company_checkout_payload_matches_required_form(self):
        user = MagicMock()
        user.company_memberships.filter.return_value.exists.return_value = True

        payload = MollieAcceptanceCommand()._checkout_payload(user)

        self.assertEqual(payload['quantity'], '1')
        self.assertEqual(payload['accept_terms'], 'on')
        self.assertEqual(payload['accept_privacy'], 'on')
        self.assertEqual(payload['accept_license'], 'on')
        self.assertNotIn('accept_withdrawal', payload)
        self.assertNotIn('request_early_performance', payload)

    def test_mollie_acceptance_private_checkout_payload_matches_required_form(self):
        user = MagicMock()
        user.company_memberships.filter.return_value.exists.return_value = False
        user.private_customer = MagicMock()

        payload = MollieAcceptanceCommand()._checkout_payload(user)

        self.assertEqual(payload['quantity'], '1')
        self.assertEqual(payload['accept_terms'], 'on')
        self.assertEqual(payload['accept_privacy'], 'on')
        self.assertEqual(payload['accept_license'], 'on')
        self.assertEqual(payload['accept_withdrawal'], 'on')
        self.assertEqual(payload['request_early_performance'], 'on')

    def test_mollie_acceptance_requires_provider_test_mode(self):
        payment = MagicMock()
        payment.order_id = 'order-1'
        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_test_payment_payload(
                {'mode': 'live', 'metadata': {'order_id': 'order-1'}},
                payment=payment,
            )

    def test_mollie_acceptance_rejects_wrong_order_metadata(self):
        payment = MagicMock()
        payment.order_id = 'order-1'
        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_test_payment_payload(
                {'mode': 'test', 'metadata': {'order_id': 'order-2'}},
                payment=payment,
            )

    def test_mollie_acceptance_rejects_wrong_webhook_url(self):
        payment = MagicMock()
        payment.order_id = 'order-1'
        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_test_payment_payload(
                {
                    'mode': 'test',
                    'metadata': {'order_id': 'order-1'},
                    'webhookUrl': 'https://wrong.example.org/api/webhooks/mollie/',
                },
                payment=payment,
                expected_webhook='https://promptmaster.example.org/api/webhooks/mollie/',
            )

    def test_mollie_paid_acceptance_rejects_active_chargeback_resource(self):
        payment = MagicMock()
        payment.provider_payment_id = 'tr_payment_test'
        payment.amount = Decimal('35.88')
        payment.currency = 'EUR'
        chargebacks = {
            '_embedded': {
                'chargebacks': [{
                    'id': 'chb_test',
                    'paymentId': 'tr_payment_test',
                    'amount': {'value': '35.88', 'currency': 'EUR'},
                    'reversedAt': None,
                }]
            }
        }

        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_provider_state(
                payment,
                {'status': 'paid'},
                'paid',
                chargebacks=chargebacks,
            )

    def test_mollie_chargeback_reversal_acceptance_uses_reversed_at(self):
        payment = MagicMock()
        payment.provider_payment_id = 'tr_payment_test'
        payment.amount = Decimal('35.88')
        payment.currency = 'EUR'
        chargebacks = {
            '_embedded': {
                'chargebacks': [{
                    'id': 'chb_test',
                    'paymentId': 'tr_payment_test',
                    'amount': {'value': '35.88', 'currency': 'EUR'},
                    'reversedAt': '2026-09-18T10:00:00+00:00',
                }]
            }
        }

        MollieAcceptanceCommand()._assert_provider_state(
            payment,
            {'status': 'paid'},
            'chargeback_reversed',
            chargebacks=chargebacks,
        )

    def test_mollie_acceptance_rejects_cross_payment_chargeback_resource(self):
        payment = MagicMock()
        payment.provider_payment_id = 'tr_payment_test'
        payment.amount = Decimal('35.88')
        payment.currency = 'EUR'
        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_provider_state(
                payment,
                {'status': 'paid'},
                'chargeback',
                chargebacks={
                    '_embedded': {
                        'chargebacks': [{
                            'paymentId': 'tr_other_payment',
                            'amount': {'value': '35.88', 'currency': 'EUR'},
                            'reversedAt': None,
                        }]
                    }
                },
            )

    def test_mollie_full_refund_acceptance_requires_live_refunded_amount(self):
        payment = MagicMock()
        payment.amount = Decimal('35.88')
        succeeded = MagicMock()
        succeeded.aggregate.return_value = {'total': Decimal('35.88')}
        payment.refunds.filter.return_value = succeeded

        MollieAcceptanceCommand()._assert_provider_state(
            payment,
            {
                'status': 'paid',
                'amountRefunded': {'currency': 'EUR', 'value': '35.88'},
            },
            'refunded_full',
        )

    def test_mollie_refund_acceptance_rejects_provider_local_total_mismatch(self):
        payment = MagicMock()
        payment.amount = Decimal('35.88')
        succeeded = MagicMock()
        succeeded.aggregate.return_value = {'total': Decimal('20.00')}
        payment.refunds.filter.return_value = succeeded

        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_provider_state(
                payment,
                {
                    'status': 'paid',
                    'amountRefunded': {'currency': 'EUR', 'value': '25.00'},
                },
                'refunded_partial',
            )

    def test_mollie_paid_acceptance_requires_real_license_activation(self):
        payment = MagicMock()
        payment.status = 'paid'
        payment.processed_paid = True
        payment.amount = Decimal('35.88')
        order = MagicMock()
        order.status = 'paid'
        order.items.filter.return_value.exists.return_value = False
        payment.order = order

        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_business_state(payment, 'paid')

    def test_mollie_refund_acceptance_rejects_unreconciled_local_refund(self):
        payment = MagicMock()
        payment.status = 'refunded_full'
        payment.processed_paid = True
        payment.amount = Decimal('35.88')
        order = MagicMock()
        order.status = 'paid'
        payment.order = order

        succeeded_filter = MagicMock()
        succeeded = MagicMock()
        succeeded.exists.return_value = False
        succeeded_filter.select_related.return_value = succeeded
        payment.refunds.filter.return_value = succeeded_filter

        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_business_state(payment, 'refunded_full')
