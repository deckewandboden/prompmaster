from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog.models import Feature, Product, ProductEntitlement, ProductPrice
from apps.catalog.services import PRO_ACCESS_FEATURE
from apps.companies.models import Company, Membership
from apps.devices.services import register_device
from apps.orders.models import Order, OrderItem

from .models import License, LicenseAssignment, LicenseTerm
from .services import assign_license, release_license


class LicenseAssignmentContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-ASSIGN',
            name='PromptMaster Pro Assignment Test',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-ASSIGN',
            name='Assignment GmbH',
            email='assignment@example.test',
            country='DE',
        )
        self.admin = User.objects.create_user(
            'assignment-admin@example.test',
            'Assignment-Admin-Password-42!',
            first_name='Ada',
            last_name='Admin',
        )
        self.member_a = User.objects.create_user(
            'assignment-a@example.test',
            'Assignment-Member-A-42!',
            first_name='Anna',
            last_name='A',
        )
        self.member_b = User.objects.create_user(
            'assignment-b@example.test',
            'Assignment-Member-B-42!',
            first_name='Berta',
            last_name='B',
        )
        Membership.objects.create(company=self.company, user=self.admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member_a, role='member', active=True)
        Membership.objects.create(company=self.company, user=self.member_b, role='member', active=True)
        self.price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=self.now - timedelta(days=2),
        )
        self.order = Order.objects.create(
            order_number='PM-O-ASSIGN',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='assignment-contract',
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            price_version=self.price,
            quantity=1,
            unit_gross=Decimal('35.88'),
            unit_net=Decimal('30.15'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        self.valid_from = self.now - timedelta(days=1)
        self.valid_until = self.now + timedelta(days=364)
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='free',
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        LicenseTerm.objects.create(
            license=self.license,
            order_item=self.item,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            paid_gross_amount=Decimal('35.88'),
        )

    def _login_admin(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_only_free_valid_license_can_be_assigned(self):
        assignment = assign_license(self.license, self.member_a, self.admin)
        self.license.refresh_from_db()
        self.assertEqual(self.license.status, 'active')
        self.assertEqual(assignment.user_id, self.member_a.id)

        with self.assertRaises(ValidationError):
            assign_license(self.license, self.member_b, self.admin)

        assignment.refresh_from_db()
        self.assertIsNone(assignment.ended_at)
        self.assertFalse(
            LicenseAssignment.objects.filter(
                license=self.license,
                user=self.member_b,
                ended_at__isnull=True,
            ).exists()
        )

    def test_release_preserves_term_and_dates_and_revokes_device(self):
        assignment = assign_license(self.license, self.member_a, self.admin)
        device, _raw = register_device(self.member_a, self.license, 'Arbeitsplatz')
        terms_before = list(
            self.license.terms.values_list('id', 'valid_from', 'valid_until', 'status')
        )

        release_license(self.license, self.admin)

        self.license.refresh_from_db()
        assignment.refresh_from_db()
        device.refresh_from_db()
        self.assertEqual(self.license.status, 'free')
        self.assertEqual(self.license.valid_from, self.valid_from)
        self.assertEqual(self.license.valid_until, self.valid_until)
        self.assertIsNotNone(assignment.ended_at)
        self.assertIsNotNone(device.revoked_at)
        self.assertEqual(
            list(self.license.terms.values_list('id', 'valid_from', 'valid_until', 'status')),
            terms_before,
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action='license.released',
                object_id=str(self.license.id),
                actor=self.admin,
            ).exists()
        )

    def test_member_deactivation_releases_license_revokes_devices_and_sessions(self):
        assignment = assign_license(self.license, self.member_a, self.admin)
        device, _raw = register_device(self.member_a, self.license, 'Notebook')
        security_version = self.member_a.security_version
        self._login_admin()

        response = self.client.post(reverse('portal:member_deactivate', args=[self.member_a.id]))

        self.assertRedirects(response, reverse('portal:team'))
        membership = Membership.objects.get(company=self.company, user=self.member_a)
        self.member_a.refresh_from_db()
        self.license.refresh_from_db()
        assignment.refresh_from_db()
        device.refresh_from_db()
        self.assertFalse(membership.active)
        self.assertFalse(self.member_a.is_active)
        self.assertEqual(self.member_a.security_version, security_version + 1)
        self.assertEqual(self.license.status, 'free')
        self.assertEqual(self.license.valid_from, self.valid_from)
        self.assertEqual(self.license.valid_until, self.valid_until)
        self.assertIsNotNone(assignment.ended_at)
        self.assertIsNotNone(device.revoked_at)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='company.member_deactivated',
                object_id=str(membership.id),
                actor=self.admin,
            ).exists()
        )


class CustomerAdminSelfActivationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-SELF-ACTIVATE',
            name='PromptMaster Pro Self Activation',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        feature, _ = Feature.objects.get_or_create(
            code=PRO_ACCESS_FEATURE,
            defaults={'name': 'PromptMaster Pro Runtime'},
        )
        ProductEntitlement.objects.create(
            product=self.product,
            feature=feature,
            enabled=True,
        )
        self.price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=self.now - timedelta(days=1),
        )
        self.company = Company.objects.create(
            customer_number='PM-C-SELF-ACTIVATE',
            name='Self Activate GmbH',
            email='admin-self@example.test',
        )
        self.admin = User.objects.create_user(
            'admin-self@example.test',
            'Self-Activate-Password-2026!',
            first_name='Admin',
            last_name='Self',
            email_verified_at=self.now,
        )
        self.member = User.objects.create_user(
            'member-self@example.test',
            'Self-Activate-Member-2026!',
            first_name='Member',
            last_name='Self',
            email_verified_at=self.now,
        )
        Membership.objects.create(
            company=self.company,
            user=self.admin,
            role='admin',
            active=True,
        )
        Membership.objects.create(
            company=self.company,
            user=self.member,
            role='member',
            active=True,
        )
        order = Order.objects.create(
            order_number='PM-O-SELF-ACTIVATE',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='self-activate-order',
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            price_version=self.price,
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
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        LicenseTerm.objects.create(
            license=self.license,
            order_item=item,
            valid_from=self.license.valid_from,
            valid_until=self.license.valid_until,
            paid_gross_amount=Decimal('35.88'),
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_company_admin_can_consume_one_free_seat_for_own_pro_use(self):
        self._login(self.admin)
        response = self.client.post(reverse('portal:activate_my_pro'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('proaccess:launch'))
        self.license.refresh_from_db()
        self.assertEqual(self.license.status, 'active')
        self.assertTrue(
            LicenseAssignment.objects.filter(
                license=self.license,
                user=self.admin,
                ended_at__isnull=True,
            ).exists()
        )

    def test_company_member_cannot_self_assign_a_free_company_seat(self):
        self._login(self.member)
        response = self.client.post(reverse('portal:activate_my_pro'))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            LicenseAssignment.objects.filter(
                license=self.license,
                user=self.member,
                ended_at__isnull=True,
            ).exists()
        )
