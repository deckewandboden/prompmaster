from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order, OrderItem

from .models import MollieEvent, Payment
from .services import calculate_refund, create_refund_request, process_provider_state, submit_refund


class RefundMathTests(SimpleTestCase):
    def test_full_remaining(self):
        now = timezone.now()
        term = SimpleNamespace(
            paid_gross_amount=Decimal('35.88'),
            valid_from=now,
            valid_until=now + timedelta(days=365),
        )
        days, amount = calculate_refund(term, today=timezone.localdate(now))
        self.assertEqual(days, 365)
        self.assertEqual(amount, Decimal('35.88'))

    def test_halfish_remaining_is_prorated(self):
        now = timezone.now()
        term = SimpleNamespace(
            paid_gross_amount=Decimal('35.88'),
            valid_from=now - timedelta(days=265),
            valid_until=now + timedelta(days=100),
        )
        days, amount = calculate_refund(term, today=timezone.localdate(now))
        self.assertEqual(days, 100)
        self.assertEqual(amount, Decimal('9.83'))


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

    @patch('apps.payments.services._queue_after_commit')
    def test_duplicate_paid_webhook_creates_exactly_one_license_term_and_event(self, _mail):
        paid = self.payload('paid')
        with patch('apps.payments.views.MollieClient.get_payment', return_value=paid):
            first = self.client.post(
                '/api/webhooks/mollie/',
                {'id': self.payment.provider_payment_id},
            )
            second = self.client.post(
                '/api/webhooks/mollie/',
                {'id': self.payment.provider_payment_id},
            )

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
    def test_chargeback_blocks_license_and_paid_reversal_restores_access_state(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(license_obj.status, 'active')

        process_provider_state(self.payment.provider_payment_id, self.payload('charged_back'))
        license_obj.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback')
        self.assertEqual(license_obj.status, 'payment_review')

        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
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
        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'chargeback_reversed')
        self.assertEqual(
            MollieEvent.objects.filter(payment=self.payment).count(),
            events_before_duplicate,
        )

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.services.MollieClient.create_refund')
    def test_refund_terminates_access_revokes_device_and_invalidates_sessions(self, create_refund, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        license_obj = License.objects.get(owner_user=self.user)
        term = LicenseTerm.objects.get(license=license_obj)
        assignment = LicenseAssignment.objects.get(license=license_obj, ended_at__isnull=True)
        device, _raw = register_device(self.user, license_obj, 'Refund Browser')
        self.user.refresh_from_db()
        security_version_before = self.user.security_version

        refund = create_refund_request(term=term, actor=self.user, reason='Test refund')
        create_refund.return_value = {'id': 're_refund_test', 'status': 'refunded'}
        submit_refund(refund)

        refund.refresh_from_db()
        term.refresh_from_db()
        license_obj.refresh_from_db()
        assignment.refresh_from_db()
        device.refresh_from_db()
        self.payment.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(refund.status, 'succeeded')
        self.assertEqual(refund.provider_refund_id, 're_refund_test')
        self.assertEqual(term.status, 'refunded')
        self.assertEqual(license_obj.status, 'refunded')
        self.assertEqual(self.payment.status, 'refunded_full')
        self.assertIsNotNone(assignment.ended_at)
        self.assertIsNotNone(device.revoked_at)
        self.assertGreater(self.user.security_version, security_version_before)

    @patch('apps.payments.services._queue_after_commit')
    def test_provider_amount_or_currency_mismatch_is_rejected(self, _mail):
        wrong = self.payload('paid')
        wrong['amount'] = {'value': '99.99', 'currency': 'EUR'}
        with self.assertRaises(ValidationError):
            process_provider_state(self.payment.provider_payment_id, wrong)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())
