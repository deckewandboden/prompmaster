import json
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import requests

from django.core.management import call_command
from django.core.management.base import CommandError
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.management.commands.external_graph_acceptance import INVALID_SENDER
from apps.core.management.commands.external_mollie_acceptance import Command as MollieAcceptanceCommand
from apps.notifications.models import EmailMessage


class ExternalAcceptanceSafetyTests(SimpleTestCase):

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
            if settings.GRAPH_SENDER == INVALID_SENDER:
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

    def test_mollie_paid_acceptance_rejects_live_provider_chargeback(self):
        payment = MagicMock()
        payment.amount = Decimal('35.88')

        with self.assertRaises(CommandError):
            MollieAcceptanceCommand()._assert_provider_state(
                payment,
                {'status': 'charged_back'},
                'paid',
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
