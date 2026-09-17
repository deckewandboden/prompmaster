from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment
from apps.orders.models import Order
from apps.payments.models import Payment
from .models import Company, Membership


class PortalContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(code='PRO', name='PromptMaster Pro')
        self.company = Company.objects.create(
            customer_number='PM-C-PORTAL',
            name='Portal GmbH',
            email='portal@example.test',
            country='DE',
        )
        self.admin = User.objects.create_user(
            'portal-admin@example.test',
            'Portal-Admin-Password-42!',
            first_name='Ada',
            last_name='Admin',
            email_verified_at=self.now,
        )
        self.member = User.objects.create_user(
            'portal-member@example.test',
            'Portal-Member-Password-42!',
            first_name='Mia',
            last_name='Member',
            email_verified_at=self.now,
        )
        Membership.objects.create(company=self.company, user=self.admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member, role='member', active=True)
        self.active_license = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now,
            valid_until=self.now + timedelta(days=365),
        )
        self.assignment = LicenseAssignment.objects.create(
            license=self.active_license,
            user=self.member,
        )
        self.free_license = License.objects.create(
            company=self.company,
            product=self.product,
            status='free',
            valid_from=self.now,
            valid_until=self.now + timedelta(days=365),
        )
        DeviceRegistration.objects.create(
            user=self.member,
            license=self.active_license,
            token_hash='a' * 64,
            display_name='Portal Notebook',
            os_family='Windows',
            browser_family='Edge',
            last_seen_at=self.now,
        )
        order = Order.objects.create(
            order_number='PM-O-PORTAL',
            company=self.company,
            status='failed',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='portal-dashboard-payment',
        )
        Payment.objects.create(
            order=order,
            provider_payment_id='tr_portal_failed',
            status='failed',
            amount=Decimal('35.88'),
            currency='EUR',
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_required_license_routes_exist_for_company_admin(self):
        self._login(self.admin)
        detail = self.client.get(reverse('portal:license_detail', args=[self.active_license.id]))
        renew_index = self.client.get(reverse('portal:renew_index'))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(renew_index.status_code, 200)
        self.assertContains(detail, self.active_license.license_number)
        self.assertContains(detail, self.member.email)
        self.assertContains(renew_index, self.active_license.license_number)

    def test_member_cannot_open_unassigned_company_license_detail(self):
        self._login(self.member)
        self.assertEqual(
            self.client.get(reverse('portal:license_detail', args=[self.free_license.id])).status_code,
            404,
        )
        response = self.client.get(reverse('portal:license_detail', args=[self.active_license.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Zuweisung verwalten')

    def test_dashboard_contains_required_operational_information_for_admin(self):
        self._login(self.admin)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1/2')
        self.assertContains(response, '1 freie Lizenz')
        self.assertContains(response, self.member.email)
        self.assertContains(response, 'Zahlung prüfen')
        self.assertContains(response, 'Unternehmensdaten unvollständig')
        self.assertNotContains(response, 'PromptMaster Pro starten')

    def test_member_dashboard_does_not_expose_team_or_company_warning(self):
        self._login(self.member)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.admin.email)
        self.assertNotContains(response, 'Unternehmensdaten unvollständig')
        self.assertContains(response, 'PromptMaster Pro starten')
