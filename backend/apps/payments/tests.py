from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Membership
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.licenses.services import assign_license
from apps.orders.models import Order, OrderItem

from .models import MollieEvent, Payment, Refund
from .services import _activate_order, calculate_refund, process_provider_state


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


class RefundWorkflowIntegrationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='REFUND-PRO',
            name='Refund Pro',
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
            valid_from=self.now - timedelta(days=1),
        )
        self.company = Company.objects.create(
            customer_number='PM-C-REFUND',
            name='Refund GmbH',
            email='refund@example.test',
            country='DE',
        )
        self.company_admin = User.objects.create_user(
            'refund-admin@example.test',
            'Refund-Admin-Password-42!',
            first_name='Refund',
            last_name='Admin',
        )
        self.member_a = User.objects.create_user(
            'refund-a@example.test',
            'Refund-Member-A-42!',
            first_name='Refund',
            last_name='A',
            email_verified_at=self.now,
        )
        self.member_b = User.objects.create_user(
            'refund-b@example.test',
            'Refund-Member-B-42!',
            first_name='Refund',
            last_name='B',
            email_verified_at=self.now,
        )
        Membership.objects.create(company=self.company, user=self.company_admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member_a, role='member', active=True)
        Membership.objects.create(company=self.company, user=self.member_b, role='member', active=True)

        self.order = Order.objects.create(
            order_number='PM-O-REFUND',
            company=self.company,
            status='draft',
            currency='EUR',
            gross_total=Decimal('71.76'),
            tax_total=Decimal('11.46'),
            billing_snapshot={'customer_type': 'company'},
            idempotency_key='refund-two-seat-order',
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price_version=self.price,
            quantity=2,
            unit_gross=Decimal('35.88'),
            unit_net=Decimal('30.15'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        _activate_order(self.order, self.now)
        self.payment = Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_refund_two_seats',
            status='paid',
            amount=Decimal('71.76'),
            currency='EUR',
            paid_at=self.now,
            processed_paid=True,
        )
        licenses = list(License.objects.filter(company=self.company).order_by('license_number'))
        self.license_a, self.license_b = licenses
        self.term_a = self.license_a.terms.get()
        self.term_b = self.license_b.terms.get()
        assign_license(self.license_a, self.member_a, self.company_admin)
        assign_license(self.license_b, self.member_b, self.company_admin)
        self.device_a, _raw = register_device(self.member_a, self.license_a, 'Refund Notebook')

        self.staff = User.objects.create_user(
            'refund-staff@example.test',
            'Refund-Staff-Password-42!',
            is_staff=True,
        )
        role = Role.objects.create(code='refund-role-test', name='Refund Role Test')
        permissions = [
            Permission.objects.create(code='licenses.read', name='Licenses read'),
            Permission.objects.create(code='payments.refund', name='Payments refund'),
        ]
        role.permissions.set(permissions)
        UserRole.objects.create(user=self.staff, role=role)
        self._login(self.staff)
        self.preview_url = reverse(
            'ns_admin:license_refund',
            args=[self.license_a.id, self.term_a.id],
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_refund_preview_is_read_only_and_contains_required_business_values(self):
        response = self.client.get(self.preview_url)
        self.assertEqual(response.status_code, 200)
        preview = response.context['preview']
        self.assertEqual(preview['license'].id, self.license_a.id)
        self.assertEqual(preview['purchase_at'], self.payment.paid_at)
        self.assertEqual(preview['license_start'], self.term_a.valid_from)
        self.assertEqual(preview['used_days'], 0)
        self.assertEqual(preview['remaining_days'], 365)
        self.assertEqual(preview['paid_gross_amount'], Decimal('35.88'))
        self.assertEqual(preview['refund_amount'], Decimal('35.88'))
        self.assertEqual(preview['resulting_status'], 'refunded')
        self.assertEqual(Refund.objects.count(), 0)
        self.assertIsNone(
            LicenseAssignment.objects.get(license=self.license_a, user=self.member_a).ended_at
        )

    @patch('apps.payments.services.MollieClient.create_refund')
    def test_confirmation_and_reason_are_required_before_mollie_call(self, create_refund):
        response = self.client.post(
            self.preview_url,
            {'reason': 'Kulanz ohne Bestätigung'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'confirm', 'Dieses Feld ist zwingend erforderlich.')
        create_refund.assert_not_called()
        self.assertEqual(Refund.objects.count(), 0)

    @patch('apps.payments.services.MollieClient.create_refund')
    def test_refunding_one_of_two_seats_revokes_only_that_access_and_session(self, create_refund):
        create_refund.return_value = {'id': 're_refund_a', 'status': 'refunded'}
        member_a_version = self.member_a.security_version
        member_b_version = self.member_b.security_version

        response = self.client.post(
            self.preview_url,
            {'reason': 'Vertraglich vereinbarte Erstattung', 'confirm': 'on'},
        )

        self.assertRedirects(
            response,
            reverse('ns_admin:license_detail', args=[self.license_a.id]),
        )
        refund = Refund.objects.get(term=self.term_a)
        self.assertEqual(refund.reason, 'Vertraglich vereinbarte Erstattung')
        self.assertEqual(refund.status, 'succeeded')
        self.term_a.refresh_from_db()
        self.term_b.refresh_from_db()
        self.license_a.refresh_from_db()
        self.license_b.refresh_from_db()
        self.member_a.refresh_from_db()
        self.member_b.refresh_from_db()
        self.device_a.refresh_from_db()
        assignment_a = LicenseAssignment.objects.get(license=self.license_a, user=self.member_a)
        assignment_b = LicenseAssignment.objects.get(license=self.license_b, user=self.member_b)

        self.assertEqual(self.term_a.status, 'refunded')
        self.assertEqual(self.license_a.status, 'refunded')
        self.assertIsNotNone(assignment_a.ended_at)
        self.assertIsNotNone(self.device_a.revoked_at)
        self.assertEqual(self.member_a.security_version, member_a_version + 1)

        self.assertEqual(self.term_b.status, 'active')
        self.assertEqual(self.license_b.status, 'active')
        self.assertIsNone(assignment_b.ended_at)
        self.assertEqual(self.member_b.security_version, member_b_version)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded_partial')
        self.assertTrue(
            AuditEvent.objects.filter(
                action='refund.created',
                actor=self.staff,
                object_id=str(refund.id),
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action='refund.succeeded',
                object_id=str(refund.id),
            ).exists()
        )

    def test_staff_without_refund_permission_sees_no_action_and_gets_403(self):
        reader = User.objects.create_user(
            'refund-reader@example.test',
            'Refund-Reader-Password-42!',
            is_staff=True,
        )
        role = Role.objects.create(code='refund-reader-test', name='Refund Reader Test')
        role.permissions.add(Permission.objects.get(code='licenses.read'))
        UserRole.objects.create(user=reader, role=role)
        self._login(reader)

        detail_url = reverse('ns_admin:license_detail', args=[self.license_a.id])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.preview_url)

        response = self.client.get(self.preview_url)
        self.assertEqual(response.status_code, 403)



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
    def test_duplicate_paid_webhook_creates_exactly_one_license_and_term(self, _mail):
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

    @patch('apps.payments.services._queue_after_commit')
    def test_failed_payment_creates_no_license(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('failed'))
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, 'failed')
        self.assertEqual(self.payment.status, 'failed')
        self.assertFalse(self.payment.processed_paid)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())

    @patch('apps.payments.services._queue_after_commit')
    def test_chargeback_blocks_license_and_paid_reversal_restores_access_state(self, _mail):
        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        license_obj = License.objects.get(owner_user=self.user)
        self.assertEqual(license_obj.status, 'active')

        process_provider_state(self.payment.provider_payment_id, self.payload('charged_back'))
        license_obj.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'charged_back')
        self.assertEqual(license_obj.status, 'payment_review')

        process_provider_state(self.payment.provider_payment_id, self.payload('paid'))
        license_obj.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(license_obj.status, 'active')
        self.assertEqual(License.objects.filter(owner_user=self.user).count(), 1)
        self.assertTrue(
            MollieEvent.objects.filter(
                payment=self.payment,
                provider_status='charged_back',
            ).exists()
        )

    @patch('apps.payments.services._queue_after_commit')
    def test_provider_amount_or_currency_mismatch_is_rejected(self, _mail):
        from django.core.exceptions import ValidationError

        wrong = self.payload('paid')
        wrong['amount'] = {'value': '99.99', 'currency': 'EUR'}
        with self.assertRaises(ValidationError):
            process_provider_state(self.payment.provider_payment_id, wrong)
        self.assertFalse(License.objects.filter(owner_user=self.user).exists())
