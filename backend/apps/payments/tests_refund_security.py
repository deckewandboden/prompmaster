from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order, OrderItem

from .models import Payment
from .services import create_refund_request, process_provider_state, submit_refund


class RefundAccessTerminationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user(
            'refund-security@example.test',
            None,
            email_verified_at=now,
        )
        self.product = Product.objects.create(
            code='REFUND-SECURITY-PRO',
            name='Refund Security Pro',
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
            order_number='PM-O-REFUND-SECURITY',
            private_user=self.user,
            status='payment_open',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={'customer_type': 'private'},
            idempotency_key='refund-security-order',
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
            provider_payment_id='tr_refund_security',
            status='open',
            amount=Decimal('35.88'),
            currency='EUR',
        )

    def paid_payload(self):
        return {
            'id': self.payment.provider_payment_id,
            'status': 'paid',
            'amount': {'value': '35.88', 'currency': 'EUR'},
            'method': 'banktransfer',
        }

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.services.MollieClient.create_refund')
    def test_successful_refund_terminates_assignment_device_and_sessions(self, create_refund, _mail):
        process_provider_state(self.payment.provider_payment_id, self.paid_payload())
        license_obj = License.objects.get(owner_user=self.user)
        term = LicenseTerm.objects.get(license=license_obj)
        assignment = LicenseAssignment.objects.get(license=license_obj, ended_at__isnull=True)
        device, _raw = register_device(self.user, license_obj, 'Refund Browser')
        self.user.refresh_from_db()
        security_version_before = self.user.security_version

        refund = create_refund_request(term=term, actor=self.user, reason='Test refund')
        create_refund.return_value = {'id': 're_refund_security', 'status': 'refunded'}
        submit_refund(refund)

        refund.refresh_from_db()
        term.refresh_from_db()
        license_obj.refresh_from_db()
        assignment.refresh_from_db()
        device.refresh_from_db()
        self.payment.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(refund.status, 'succeeded')
        self.assertEqual(refund.provider_refund_id, 're_refund_security')
        self.assertEqual(term.status, 'refunded')
        self.assertEqual(license_obj.status, 'refunded')
        self.assertIsNone(license_obj.valid_from)
        self.assertIsNone(license_obj.valid_until)
        self.assertEqual(self.payment.status, 'refunded_full')
        self.assertIsNotNone(assignment.ended_at)
        self.assertIsNotNone(device.revoked_at)
        self.assertGreater(self.user.security_version, security_version_before)
