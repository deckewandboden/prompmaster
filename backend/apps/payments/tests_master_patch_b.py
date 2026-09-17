from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Membership
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.licenses.services import assign_license, consume_assignment_link, create_assignment_link
from apps.notifications.tasks import sync_license_states
from apps.orders.models import Order, OrderItem

from .mollie import MollieError
from .models import Payment, RefundAttempt
from .services import create_refund_request, submit_refund


class RefundRetryStateMachineTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user(
            'refund-retry@example.test',
            'Refund-Retry-Password-42!',
            email_verified_at=now,
        )
        self.product = Product.objects.create(
            code='REFUND-RETRY-PRO',
            name='Refund Retry Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('36.50'),
            currency='EUR',
            valid_from=now,
        )
        self.order = Order.objects.create(
            order_number='PM-O-REFUND-RETRY',
            private_user=self.user,
            status='paid',
            currency='EUR',
            gross_total=Decimal('36.50'),
            tax_total=Decimal('5.83'),
            billing_snapshot={'customer_type': 'private'},
            idempotency_key='refund-retry-order',
        )
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price_version=price,
            quantity=1,
            unit_gross=Decimal('36.50'),
            unit_net=Decimal('30.67'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_refund_retry',
            status='paid',
            amount=Decimal('36.50'),
            currency='EUR',
            paid_at=now,
            processed_paid=True,
        )
        self.license = License.objects.create(
            owner_user=self.user,
            product=self.product,
            status='active',
            valid_from=now,
            valid_until=now + timedelta(days=365),
        )
        LicenseAssignment.objects.create(license=self.license, user=self.user)
        self.term = LicenseTerm.objects.create(
            license=self.license,
            order_item=item,
            valid_from=self.license.valid_from,
            valid_until=self.license.valid_until,
            paid_gross_amount=Decimal('36.50'),
            status='active',
        )

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.services.calculate_refund')
    @patch('apps.payments.services.MollieClient.create_refund')
    def test_deterministic_failure_is_requoted_and_uses_new_attempt_key(
        self, provider, calculate, _mail
    ):
        calculate.return_value = (300, Decimal('30.00'))
        refund = create_refund_request(term=self.term, actor=self.user, reason='first')
        provider.side_effect = MollieError('HTTP 422', ambiguous=False, status_code=422)
        with self.assertRaises(MollieError):
            submit_refund(refund)

        refund.refresh_from_db()
        first = refund.attempts.get(number=1)
        self.assertEqual(refund.status, 'failed')
        self.assertEqual(first.status, 'failed')
        self.assertTrue(first.idempotency_key.endswith(':attempt:1'))

        calculate.return_value = (250, Decimal('25.00'))
        requoted = create_refund_request(term=self.term, actor=self.user, reason='retry')
        self.assertEqual(requoted.status, 'created')
        self.assertEqual(requoted.remaining_days, 250)
        self.assertEqual(requoted.amount, Decimal('25.00'))

        provider.side_effect = None
        provider.return_value = {'id': 're_retry_2', 'status': 'pending'}
        submit_refund(requoted)
        requoted.refresh_from_db()
        second = requoted.attempts.get(number=2)
        self.assertEqual(requoted.status, 'submitted')
        self.assertEqual(second.amount, Decimal('25.00'))
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)
        self.assertTrue(second.idempotency_key.endswith(':attempt:2'))

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.services.calculate_refund')
    @patch('apps.payments.services.MollieClient.create_refund')
    def test_ambiguous_failure_reuses_same_quote_and_idempotency_key(
        self, provider, calculate, _mail
    ):
        calculate.return_value = (300, Decimal('30.00'))
        refund = create_refund_request(term=self.term, actor=self.user)
        provider.side_effect = MollieError('timeout', ambiguous=True)
        with self.assertRaises(MollieError):
            submit_refund(refund)

        refund.refresh_from_db()
        attempt = refund.attempts.get(number=1)
        original_key = attempt.idempotency_key
        self.assertEqual(refund.status, 'submitted')
        self.assertEqual(attempt.status, 'ambiguous')

        calculate.return_value = (200, Decimal('20.00'))
        same_refund = create_refund_request(term=self.term, actor=self.user)
        self.assertEqual(same_refund.amount, Decimal('30.00'))
        self.assertEqual(same_refund.remaining_days, 300)

        provider.side_effect = None
        provider.return_value = {'id': 're_ambiguous_1', 'status': 'refunded'}
        submit_refund(same_refund)
        same_refund.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(same_refund.status, 'succeeded')
        self.assertEqual(attempt.status, 'succeeded')
        self.assertEqual(attempt.idempotency_key, original_key)
        self.assertEqual(RefundAttempt.objects.filter(refund=same_refund).count(), 1)
        self.assertEqual(provider.call_args.args[-1], original_key)

    @patch('apps.payments.services._queue_after_commit')
    def test_license_sync_recovers_interrupted_provider_success(self, _mail):
        refund = create_refund_request(term=self.term, actor=self.user)
        refund.status = 'succeeded'
        refund.provider_refund_id = 're_interrupted_success'
        refund.save(update_fields=['status', 'provider_refund_id', 'updated_at'])

        result = sync_license_states.run()

        refund.refresh_from_db()
        self.term.refresh_from_db()
        self.payment.refresh_from_db()
        self.license.refresh_from_db()
        assignment = LicenseAssignment.objects.get(license=self.license, user=self.user)
        assignment.refresh_from_db()

        self.assertIsInstance(result, int)
        self.assertEqual(refund.status, 'succeeded')
        self.assertEqual(self.term.status, 'refunded')
        self.assertEqual(self.payment.status, 'refunded_full')
        self.assertEqual(self.license.status, 'refunded')
        self.assertIsNone(self.license.valid_from)
        self.assertIsNone(self.license.valid_until)
        self.assertIsNotNone(assignment.ended_at)


class SuspendedTenantAssignmentTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.company = Company.objects.create(
            customer_number='PM-C-SUSPENDED-B',
            name='Suspended Patch B GmbH',
            email='suspended-b@example.test',
        )
        self.admin = User.objects.create_user(
            'suspended-admin@example.test', 'Admin-Password-42!'
        )
        self.member = User.objects.create_user(
            'suspended-member@example.test', 'Member-Password-42!'
        )
        Membership.objects.create(
            company=self.company, user=self.admin, role='admin', active=True
        )
        Membership.objects.create(
            company=self.company, user=self.member, role='member', active=True
        )
        self.product = Product.objects.create(
            code='SUSPENDED-PRO',
            name='Suspended Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=now,
        )
        order = Order.objects.create(
            order_number='PM-O-SUSPENDED-B',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='suspended-b-order',
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            price_version=price,
            quantity=1,
            unit_gross=Decimal('35.88'),
            unit_net=Decimal('30.15'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='free',
            valid_from=now,
            valid_until=now + timedelta(days=365),
        )
        LicenseTerm.objects.create(
            license=self.license,
            order_item=item,
            valid_from=self.license.valid_from,
            valid_until=self.license.valid_until,
            paid_gross_amount=Decimal('35.88'),
            status='active',
        )

    def test_link_created_before_suspension_cannot_be_consumed(self):
        link, raw = create_assignment_link(
            company=self.company,
            target_user=self.member,
            license_obj=self.license,
            actor=self.admin,
        )
        self.company.status = 'inactive'
        self.company.save(update_fields=['status', 'updated_at'])

        with self.assertRaises(ValidationError):
            consume_assignment_link(raw_token=raw, user=self.member)
        link.refresh_from_db()
        self.assertIsNone(link.used_at)
        self.assertFalse(
            LicenseAssignment.objects.filter(
                license=self.license, user=self.member, ended_at__isnull=True
            ).exists()
        )

    def test_direct_assignment_is_blocked_for_inactive_company(self):
        self.company.status = 'inactive'
        self.company.save(update_fields=['status', 'updated_at'])
        with self.assertRaises(ValidationError):
            assign_license(self.license, self.member, self.admin)
        self.license.refresh_from_db()
        self.assertEqual(self.license.status, 'free')
