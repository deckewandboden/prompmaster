from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.admin_forms import MollieConfigForm
from apps.catalog.models import Product, ProductPrice
from apps.licenses.models import License, LicenseTerm
from apps.orders.models import Order, OrderItem

from .mollie import MollieClient, MollieError
from .models import MollieEvent, Payment, Refund
from .services import calculate_refund, process_provider_state


class RefundMathTests(SimpleTestCase):
    def test_full_remaining(self):
        now = timezone.now()
        term = SimpleNamespace(
            paid_gross_amount=Decimal('35.88'),
            valid_from=now,
            valid_until=now + timedelta(days=365),
        )
        days, amount = calculate_refund(term, now=now)
        self.assertEqual(days, 365)
        self.assertEqual(amount, Decimal('35.88'))

    def test_halfish_remaining_is_prorated(self):
        now = timezone.now()
        term = SimpleNamespace(
            paid_gross_amount=Decimal('35.88'),
            valid_from=now - timedelta(days=265),
            valid_until=now + timedelta(days=100),
        )
        days, amount = calculate_refund(term, now=now)
        self.assertEqual(days, 100)
        self.assertEqual(amount, Decimal('9.83'))


class MollieConfigurationSafetyTests(SimpleTestCase):
    @override_settings(ENVIRONMENT='production')
    def test_production_form_accepts_only_live_keys(self):
        valid = MollieConfigForm({'profile_id': 'pfl_live', 'api_key': 'live_valid_key'})
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = MollieConfigForm({'profile_id': 'pfl_live', 'api_key': 'test_wrong_mode'})
        self.assertFalse(invalid.is_valid())
        self.assertIn('api_key', invalid.errors)

    @override_settings(ENVIRONMENT='staging')
    def test_nonproduction_form_accepts_only_test_keys(self):
        valid = MollieConfigForm({'profile_id': 'pfl_test', 'api_key': 'test_valid_key'})
        self.assertTrue(valid.is_valid(), valid.errors)
        invalid = MollieConfigForm({'profile_id': 'pfl_test', 'api_key': 'live_wrong_mode'})
        self.assertFalse(invalid.is_valid())
        self.assertIn('api_key', invalid.errors)

    @override_settings(ENVIRONMENT='production')
    def test_production_client_rejects_runtime_test_key(self):
        with self.assertRaisesMessage(MollieError, 'Production requires a Mollie live API key'):
            MollieClient(key='test_runtime_key')

    @override_settings(ENVIRONMENT='staging')
    def test_nonproduction_client_rejects_runtime_live_key(self):
        with self.assertRaisesMessage(MollieError, 'Non-production environments refuse Mollie live API keys'):
            MollieClient(key='live_runtime_key')


    @override_settings(ENVIRONMENT='staging')
    def test_conflict_timeout_and_rate_limit_are_ambiguous_provider_outcomes(self):
        client = MollieClient(key='test_http_classification')
        for status_code in (408, 409, 429, 500, 503):
            with self.subTest(status_code=status_code):
                response = MagicMock()
                response.ok = False
                response.status_code = status_code
                with patch(
                    'apps.payments.mollie.requests.request',
                    return_value=response,
                ):
                    with self.assertRaises(MollieError) as caught:
                        client._request('POST', '/payments')
                self.assertTrue(caught.exception.ambiguous)

    @override_settings(ENVIRONMENT='staging')
    def test_validation_4xx_remains_deterministic(self):
        client = MollieClient(key='test_http_classification')
        response = MagicMock()
        response.ok = False
        response.status_code = 422
        with patch(
            'apps.payments.mollie.requests.request',
            return_value=response,
        ):
            with self.assertRaises(MollieError) as caught:
                client._request('POST', '/payments')
        self.assertFalse(caught.exception.ambiguous)


class MollieRuntimeReadinessTests(SimpleTestCase):
    @override_settings(ENVIRONMENT='production', MOLLIE_API_KEY='')
    def test_production_credentials_do_not_enable_checkout_without_explicit_gate(self):
        with (
            patch(
                'apps.integrations.services.get_secret',
                return_value='live_runtime_key',
            ),
            patch(
                'apps.core.settings_store.get_setting',
                side_effect=lambda key, default=None: (
                    'pfl_runtime'
                    if key == 'mollie_profile_id'
                    else False
                    if key == 'mollie_checkout_enabled'
                    else default
                ),
            ),
        ):
            from apps.payments.mollie import mollie_runtime_ready

            self.assertFalse(mollie_runtime_ready())

    @override_settings(ENVIRONMENT='production', MOLLIE_API_KEY='')
    def test_production_checkout_requires_explicit_approved_gate(self):
        with (
            patch(
                'apps.integrations.services.get_secret',
                return_value='live_runtime_key',
            ),
            patch(
                'apps.core.settings_store.get_setting',
                side_effect=lambda key, default=None: (
                    'pfl_runtime'
                    if key == 'mollie_profile_id'
                    else True
                    if key == 'mollie_checkout_enabled'
                    else default
                ),
            ),
        ):
            from apps.payments.mollie import mollie_runtime_ready

            self.assertTrue(mollie_runtime_ready())

    @override_settings(ENVIRONMENT='staging', MOLLIE_API_KEY='')
    def test_staging_test_checkout_does_not_require_production_approval_gate(self):
        with (
            patch(
                'apps.integrations.services.get_secret',
                return_value='test_runtime_key',
            ),
            patch(
                'apps.core.settings_store.get_setting',
                side_effect=lambda key, default=None: (
                    'pfl_runtime'
                    if key == 'mollie_profile_id'
                    else False
                    if key == 'mollie_checkout_enabled'
                    else default
                ),
            ),
        ):
            from apps.payments.mollie import mollie_runtime_ready

            self.assertTrue(mollie_runtime_ready())


class MollieRefundPaginationTests(SimpleTestCase):
    @override_settings(ENVIRONMENT='staging')
    def test_refund_listing_follows_safe_mollie_pagination(self):
        client = MollieClient(key='test_refund_pagination')
        pages = [
            {
                'count': 1,
                '_embedded': {'refunds': [{'id': 're_page_1'}]},
                '_links': {
                    'next': {
                        'href': (
                            'https://api.mollie.com/v2/payments/tr_page/refunds'
                            '?from=re_page_1&limit=250'
                        )
                    }
                },
            },
            {
                'count': 1,
                '_embedded': {'refunds': [{'id': 're_page_2'}]},
                '_links': {'next': None},
            },
        ]
        with patch.object(client, '_request', side_effect=pages) as request:
            payload = client.list_refunds('tr_page')

        self.assertEqual(
            [row['id'] for row in payload['_embedded']['refunds']],
            ['re_page_1', 're_page_2'],
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(request.call_count, 2)
        request.assert_any_call(
            'GET',
            '/payments/tr_page/refunds?from=re_page_1&limit=250',
        )

    @override_settings(ENVIRONMENT='staging')
    def test_refund_listing_rejects_foreign_pagination_host(self):
        client = MollieClient(key='test_refund_pagination')
        payload = {
            '_embedded': {'refunds': []},
            '_links': {
                'next': {
                    'href': (
                        'https://attacker.example/v2/payments/tr_page/refunds'
                        '?from=re_bad&limit=250'
                    )
                }
            },
        }
        with patch.object(client, '_request', return_value=payload):
            with self.assertRaisesMessage(
                MollieError,
                'unexpected host',
            ):
                client.list_refunds('tr_page')


class MollieReconciliationScheduleTests(SimpleTestCase):
    def test_unsettled_reconciliation_is_scheduled(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE['mollie-unsettled-reconciliation']
        self.assertEqual(
            entry['task'],
            'apps.payments.tasks.reconcile_mollie_unsettled_states',
        )
        self.assertEqual(entry['schedule'], 900.0)


class MollieLiveProbeTests(SimpleTestCase):
    @override_settings(ENVIRONMENT='production')
    def test_current_profile_uses_read_only_profiles_me_endpoint(self):
        client = MollieClient(key='live_probe_key')
        payload = {'resource': 'profile', 'id': 'pfl_probe', 'mode': 'live'}
        with patch.object(client, '_request', return_value=payload) as request:
            self.assertEqual(client.get_current_profile(), payload)
        request.assert_called_once_with('GET', '/profiles/me')

    @override_settings(ENVIRONMENT='production')
    def test_live_methods_probe_uses_oneoff_endpoint(self):
        client = MollieClient(key='live_probe_key')
        payload = {
            '_embedded': {
                'methods': [{'id': 'creditcard', 'status': 'activated'}]
            }
        }
        with patch.object(client, '_request', return_value=payload) as request:
            self.assertEqual(client.list_methods(), payload)
        request.assert_called_once_with('GET', '/methods?sequenceType=oneoff')

    def test_live_probe_accepts_matching_runtime_profile_without_exposing_key(self):
        fake = SimpleNamespace(
            key='live_runtime_secret',
            get_current_profile=lambda: {
                'resource': 'profile',
                'id': 'pfl_runtime',
                'mode': 'live',
                'name': 'PROMPTFINISHER',
                'status': 'verified',
                'review': None,
            },
            list_methods=lambda: {
                '_embedded': {
                    'methods': [
                        {'id': 'creditcard', 'status': 'activated'},
                        {'id': 'paypal', 'status': 'activated'},
                    ]
                }
            },
        )
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
            call_command('external_mollie_acceptance', 'probe-live', stdout=out)

        rendered = out.getvalue()
        self.assertIn('"status": "ok"', rendered)
        self.assertIn('"profile_id": "pfl_runtime"', rendered)
        self.assertIn('"profile_status": "verified"', rendered)
        self.assertIn('"creditcard"', rendered)
        self.assertIn('"paypal"', rendered)
        self.assertNotIn(fake.key, rendered)

    def test_live_probe_refuses_test_key(self):
        fake = SimpleNamespace(key='test_runtime_secret')
        with patch(
            'apps.core.management.commands.external_mollie_acceptance.MollieClient',
            return_value=fake,
        ):
            with self.assertRaisesMessage(CommandError, 'requires the effective live_ API key'):
                call_command('external_mollie_acceptance', 'probe-live')

    def test_live_probe_rejects_profile_mismatch(self):
        fake = SimpleNamespace(
            key='live_runtime_secret',
            get_current_profile=lambda: {
                'resource': 'profile',
                'id': 'pfl_provider',
                'mode': 'live',
                'status': 'verified',
            },
            list_methods=lambda: {
                '_embedded': {
                    'methods': [{'id': 'creditcard', 'status': 'activated'}]
                }
            },
        )
        with (
            patch(
                'apps.core.management.commands.external_mollie_acceptance.MollieClient',
                return_value=fake,
            ),
            patch(
                'apps.core.management.commands.external_mollie_acceptance.get_setting',
                return_value='pfl_configured',
            ),
        ):
            with self.assertRaisesMessage(CommandError, 'runtime profile mismatch'):
                call_command('external_mollie_acceptance', 'probe-live')


    def test_live_probe_rejects_unverified_profile(self):
        fake = SimpleNamespace(
            key='live_runtime_secret',
            get_current_profile=lambda: {
                'resource': 'profile',
                'id': 'pfl_runtime',
                'mode': 'live',
                'status': 'unverified',
            },
            list_methods=lambda: {
                '_embedded': {
                    'methods': [{'id': 'creditcard', 'status': 'activated'}]
                }
            },
        )
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
            with self.assertRaisesMessage(CommandError, 'not verified'):
                call_command('external_mollie_acceptance', 'probe-live')

    def test_live_probe_rejects_profile_without_activated_oneoff_method(self):
        fake = SimpleNamespace(
            key='live_runtime_secret',
            get_current_profile=lambda: {
                'resource': 'profile',
                'id': 'pfl_runtime',
                'mode': 'live',
                'status': 'verified',
            },
            list_methods=lambda: {
                '_embedded': {
                    'methods': [
                        {'id': 'paypal', 'status': 'pending-review'},
                    ]
                }
            },
        )
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
            with self.assertRaisesMessage(
                CommandError,
                'no activated one-off payment method',
            ):
                call_command('external_mollie_acceptance', 'probe-live')


class MollieStateIntegrationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user(
            'payment-test@example.test',
            None,
            email_verified_at=now,
        )
        self.product = Product.objects.create(
            code='PAYMENT-TEST-PRO',
            name='Payment Test Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=now - timedelta(days=1),
        )
        self.order = Order.objects.create(
            order_number='PM-O-PAYMENT-TEST',
            private_user=self.user,
            status='payment_open',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={'customer_type': 'private'},
            idempotency_key='payment-integration-order',
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price_version=self.price,
            quantity=1,
            unit_gross=Decimal('35.88'),
            unit_net=Decimal('30.15'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_payment_test',
            status='open',
            amount=Decimal('35.88'),
            currency='EUR',
        )

    def payload(self, status):
        return {
            'id': self.payment.provider_payment_id,
            'status': status,
            'amount': {'value': '35.88', 'currency': 'EUR'},
            'method': 'banktransfer',
        }

    def chargebacks(self, *rows):
        return {'_embedded': {'chargebacks': list(rows)}}

    def chargeback(self, *, reversed_at=None, payment_id=None):
        return {
            'resource': 'chargeback',
            'id': 'chb_payment_test',
            'paymentId': payment_id or self.payment.provider_payment_id,
            'amount': {'value': '35.88', 'currency': 'EUR'},
            'createdAt': '2026-09-18T09:00:00+00:00',
            'reversedAt': reversed_at,
        }

    def test_unknown_webhook_id_does_not_call_provider_api(self):
        with (
            patch('apps.payments.views.MollieClient.get_payment') as provider_get,
            patch('apps.payments.views.MollieClient.list_chargebacks') as provider_chargebacks,
        ):
            response = self.client.post(
                '/api/webhooks/mollie/',
                {'id': 'tr_unknown_payment'},
            )
        self.assertEqual(response.status_code, 404)
        provider_get.assert_not_called()
        provider_chargebacks.assert_not_called()

    @patch('apps.payments.services._queue_after_commit')
    def test_duplicate_paid_webhook_creates_exactly_one_license_and_term(self, _mail):
        paid = self.payload('paid')
        with (
            patch('apps.payments.views.MollieClient.get_payment', return_value=paid),
            patch(
                'apps.payments.views.MollieClient.list_chargebacks',
                return_value=self.chargebacks(),
            ) as provider_chargebacks,
        ):
            first = self.client.post(
                '/api/webhooks/mollie/',
                {'id': self.payment.provider_payment_id},
            )
            second = self.client.post(
                '/api/webhooks/mollie/',
                {'id': self.payment.provider_payment_id},
            )
        self.assertEqual(provider_chargebacks.call_count, 2)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertTrue(self.payment.processed_paid)
        self.assertEqual(License.objects.filter(owner_user=self.user).count(), 1)
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(LicenseTerm.objects.filter(license=license_obj).count(), 1)
        self.assertEqual(license_obj.valid_until - license_obj.valid_from, timedelta(days=365))
        self.assertEqual(
            MollieEvent.objects.filter(payment=self.payment, provider_status='paid').count(),
            1,
        )

    @patch('apps.payments.services._queue_after_commit')
    def test_paid_order_cannot_be_downgraded_by_stale_checkout_state(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

        for stale_status in ('payment_open', 'failed', 'canceled', 'draft'):
            with self.subTest(stale_status=stale_status):
                self.order.status = stale_status
                self.order.save(update_fields=['status', 'updated_at'])
                self.order.refresh_from_db()
                self.assertEqual(self.order.status, 'paid')

    @patch('apps.payments.services._queue_after_commit')
    def test_failed_payment_creates_no_license_and_preserves_first_failure_time(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('failed'))
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'failed')
        self.assertEqual(self.payment.status, 'failed')
        self.assertIsNotNone(self.payment.failed_at)
        first_failed_at = self.payment.failed_at
        self.assertFalse(self.payment.processed_paid)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())

        process_provider_state(self.payment.provider_payment_id, self.payload('failed'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.failed_at, first_failed_at)

    @patch('apps.payments.services._queue_after_commit')
    def test_nonterminal_provider_states_never_activate_entitlement(self, _mail):
        for provider_status in ('created', 'open', 'pending', 'authorized'):
            with self.subTest(provider_status=provider_status):
                process_provider_state(
                    self.payment.provider_payment_id,
                    self.payload(provider_status),
                )
                self.order.refresh_from_db()
                self.payment.refresh_from_db()
                self.assertEqual(self.order.status, 'payment_open')
                self.assertEqual(self.payment.status, provider_status)
                self.assertFalse(self.payment.processed_paid)
                self.assertFalse(
                    License.objects.filter(owner_user=self.user).exists()
                )

    @patch('apps.payments.services._queue_after_commit')
    def test_unknown_provider_state_fails_closed_without_entitlement(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('provider_future_state'),
        )
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'payment_open')
        self.assertEqual(self.payment.status, 'unknown')
        self.assertFalse(self.payment.processed_paid)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())

    @patch('apps.payments.services._queue_after_commit')
    def test_canceled_payment_cancels_order_without_creating_license(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('canceled'))
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'canceled')
        self.assertEqual(self.payment.status, 'canceled')
        self.assertIsNotNone(self.payment.failed_at)
        self.assertFalse(self.payment.processed_paid)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())

    @patch('apps.payments.services._queue_after_commit')
    def test_expired_payment_fails_order_without_creating_license(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('expired'))
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'failed')
        self.assertEqual(self.payment.status, 'expired')
        self.assertIsNotNone(self.payment.failed_at)
        self.assertFalse(self.payment.processed_paid)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())

    @patch('apps.payments.services._queue_after_commit')
    def test_stale_negative_webhook_cannot_downgrade_paid_payment(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(self.payment.status, 'paid')

        for stale_status in ('canceled', 'expired', 'failed'):
            with self.subTest(stale_status=stale_status):
                process_provider_state(
                    self.payment.provider_payment_id,
                    self.payload(stale_status),
                    chargebacks_payload=self.chargebacks(),
                )
                self.order.refresh_from_db()
                self.payment.refresh_from_db()
                license_obj.refresh_from_db()
                self.assertEqual(self.order.status, 'paid')
                self.assertEqual(self.payment.status, 'paid')
                self.assertTrue(self.payment.processed_paid)
                self.assertIn(license_obj.status, {'active', 'free'})

    @patch('apps.payments.services._queue_after_commit')
    def test_stale_nonterminal_or_unknown_webhook_cannot_reopen_paid_payment(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        license_obj = License.objects.get(owner_user=self.user)

        for stale_status in ('created', 'open', 'pending', 'authorized', 'future_status'):
            with self.subTest(stale_status=stale_status):
                process_provider_state(
                    self.payment.provider_payment_id,
                    self.payload(stale_status),
                    chargebacks_payload=self.chargebacks(),
                )
                self.order.refresh_from_db()
                self.payment.refresh_from_db()
                license_obj.refresh_from_db()
                self.assertEqual(self.order.status, 'paid')
                self.assertEqual(self.payment.status, 'paid')
                self.assertTrue(self.payment.processed_paid)
                self.assertIn(license_obj.status, {'active', 'free'})

    @patch('apps.payments.services._queue_after_commit')
    def test_stale_paid_snapshot_cannot_erase_local_refund_state(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        self.payment.refresh_from_db()
        self.payment.status = 'refunded_partial'
        self.payment.save(update_fields=['status', 'updated_at'])

        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded_partial')

    @patch('apps.payments.services._queue_after_commit')
    def test_empty_chargeback_list_cannot_silently_clear_active_chargeback(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(self.chargeback()),
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback')

        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback')

    @patch('apps.payments.services._queue_after_commit')
    def test_untracked_provider_refund_quarantines_active_license(self, _mail):
        paid = self.payload('paid')
        paid['amountRefunded'] = {'value': '0.00', 'currency': 'EUR'}
        process_provider_state(
            self.payment.provider_payment_id,
            paid,
            chargebacks_payload=self.chargebacks(),
        )
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(license_obj.status, 'active')

        provider_refund = self.payload('paid')
        provider_refund['amountRefunded'] = {'value': '10.00', 'currency': 'EUR'}
        process_provider_state(
            self.payment.provider_payment_id,
            provider_refund,
            chargebacks_payload=self.chargebacks(),
        )

        self.payment.refresh_from_db()
        license_obj.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded_partial')
        self.assertEqual(license_obj.status, 'payment_review')

    @patch('apps.payments.services._queue_after_commit')
    def test_locally_tracked_provider_refund_does_not_trigger_untracked_quarantine(self, _mail):
        paid = self.payload('paid')
        paid['amountRefunded'] = {'value': '0.00', 'currency': 'EUR'}
        process_provider_state(
            self.payment.provider_payment_id,
            paid,
            chargebacks_payload=self.chargebacks(),
        )
        license_obj = License.objects.get(owner_user=self.user)
        term = LicenseTerm.objects.get(license=license_obj)

        Refund.objects.create(
            term=term,
            payment=self.payment,
            provider_refund_id='re_locally_tracked',
            amount=Decimal('10.00'),
            remaining_days=100,
            status='submitted',
        )
        provider_refund = self.payload('paid')
        provider_refund['amountRefunded'] = {'value': '10.00', 'currency': 'EUR'}
        process_provider_state(
            self.payment.provider_payment_id,
            provider_refund,
            chargebacks_payload=self.chargebacks(),
        )

        self.payment.refresh_from_db()
        license_obj.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded_partial')
        self.assertEqual(license_obj.status, 'active')

    @patch('apps.payments.services._queue_after_commit')
    def test_chargeback_blocks_license_and_reversal_restores_access_state(self, _mail):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(license_obj.status, 'active')

        active_chargeback = self.chargebacks(self.chargeback())
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=active_chargeback,
        )
        license_obj.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback')
        self.assertEqual(license_obj.status, 'payment_review')

        reversed_chargeback = self.chargebacks(
            self.chargeback(reversed_at='2026-09-18T10:00:00+00:00')
        )
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=reversed_chargeback,
        )
        license_obj.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback_reversed')
        self.assertEqual(license_obj.status, 'active')
        self.assertEqual(License.objects.filter(owner_user=self.user).count(), 1)
        self.assertTrue(
            MollieEvent.objects.filter(
                payment=self.payment,
                provider_status='chargeback',
            ).exists()
        )
        self.assertTrue(
            MollieEvent.objects.filter(
                payment=self.payment,
                provider_status='chargeback_reversed',
            ).exists()
        )

        events_before_duplicate = MollieEvent.objects.filter(payment=self.payment).count()
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=reversed_chargeback,
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback_reversed')
        self.assertEqual(
            MollieEvent.objects.filter(payment=self.payment).count(),
            events_before_duplicate,
        )

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.tasks.MollieClient.list_chargebacks')
    @patch('apps.payments.tasks.MollieClient.get_payment')
    def test_periodic_reconciliation_restores_reversed_chargeback(
        self,
        provider_get,
        provider_chargebacks,
        _mail,
    ):
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(),
        )
        license_obj = License.objects.get(owner_user=self.user)
        process_provider_state(
            self.payment.provider_payment_id,
            self.payload('paid'),
            chargebacks_payload=self.chargebacks(self.chargeback()),
        )
        self.payment.refresh_from_db()
        license_obj.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback')
        self.assertEqual(license_obj.status, 'payment_review')

        provider_get.return_value = self.payload('paid')
        provider_chargebacks.return_value = self.chargebacks(
            self.chargeback(reversed_at='2026-09-18T10:00:00+00:00')
        )

        from apps.payments.tasks import reconcile_mollie_unsettled_states

        result = reconcile_mollie_unsettled_states.run()
        self.assertEqual(result['scanned'], 1)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['errors'], 0)

        self.payment.refresh_from_db()
        license_obj.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback_reversed')
        self.assertEqual(license_obj.status, 'active')
        provider_get.assert_called_once_with(self.payment.provider_payment_id)
        provider_chargebacks.assert_called_once_with(
            self.payment.provider_payment_id
        )

    @patch('apps.payments.services._queue_after_commit')
    def test_foreign_chargeback_reference_is_rejected(self, _mail):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            process_provider_state(
                self.payment.provider_payment_id,
                self.payload('paid'),
                chargebacks_payload=self.chargebacks(
                    self.chargeback(payment_id='tr_different_payment')
                ),
            )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'open')
        self.assertFalse(self.payment.processed_paid)


    @patch('apps.payments.services._queue_after_commit')
    def test_provider_amount_or_currency_mismatch_is_rejected(self, _mail):
        from django.core.exceptions import ValidationError

        wrong = self.payload('paid')
        wrong['amount'] = {'value': '99.99', 'currency': 'EUR'}
        with self.assertRaises(ValidationError):
            process_provider_state(self.payment.provider_payment_id, wrong)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())
