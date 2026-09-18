from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


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
