from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class ExternalAcceptanceSafetyTests(SimpleTestCase):
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

    @override_settings(MOLLIE_API_KEY='live_not_allowed')
    def test_mollie_acceptance_refuses_live_key(self):
        with patch('apps.integrations.services.get_secret', return_value='live_not_allowed'):
            with self.assertRaises(CommandError):
                call_command(
                    'external_mollie_acceptance',
                    'verify',
                    payment_id='tr_dummy',
                    stdout=StringIO(),
                )

    @override_settings(MOLLIE_API_KEY='test_safe')
    def test_mollie_start_requires_explicit_confirmation(self):
        with patch('apps.integrations.services.get_secret', return_value='test_safe'):
            with self.assertRaises(CommandError):
                call_command(
                    'external_mollie_acceptance',
                    'start',
                    user_email='probe@example.test',
                    base_url='https://promptmaster.example.test',
                    stdout=StringIO(),
                )
