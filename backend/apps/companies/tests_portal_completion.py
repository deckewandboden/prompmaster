from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.support.models import SupportRequest
from .models import Company, Membership


class PortalCompletionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.company = Company.objects.create(
            customer_number='PM-C-PORTAL-COMPLETE',
            name='Portal Complete GmbH',
            email='portal-complete@example.test',
            street='Testweg',
            house_number='1',
            postal_code='57000',
            city='Siegen',
            country='DE',
        )
        self.admin = User.objects.create_user(
            'portal-complete-admin@example.test',
            'Portal-Complete-Admin-42!',
            first_name='Admin',
            last_name='Portal',
            email_verified_at=self.now,
        )
        self.member = User.objects.create_user(
            'portal-delete-member@example.test',
            'Portal-Delete-Member-42!',
            first_name='Delete',
            last_name='Member',
            email_verified_at=self.now,
        )
        Membership.objects.create(company=self.company, user=self.admin, role='admin', active=True)
        self.membership = Membership.objects.create(company=self.company, user=self.member, role='member', active=True)
        self.product = Product.objects.create(code='PRO-COMPLETE', name='PromptMaster Pro Complete')
        self.price = ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=self.now - timedelta(days=1),
        )
        self.order = Order.objects.create(
            order_number='PM-O-PORTAL-COMPLETE',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='portal-complete-order',
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
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=30),
            valid_until=self.now + timedelta(days=335),
        )
        self.term = LicenseTerm.objects.create(
            license=self.license,
            order_item=self.item,
            valid_from=self.license.valid_from,
            valid_until=self.license.valid_until,
            paid_gross_amount=Decimal('35.88'),
        )
        self.assignment = LicenseAssignment.objects.create(license=self.license, user=self.member)
        self.device = DeviceRegistration.objects.create(
            user=self.member,
            license=self.license,
            token_hash='b' * 64,
            display_name='Portal Delete Device',
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_portal_complete',
            status='paid',
            amount=Decimal('35.88'),
            currency='EUR',
            paid_at=self.now,
            processed_paid=True,
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_company_admin_delete_anonymizes_user_and_preserves_history(self):
        self._login(self.admin)
        old_user_id = self.member.id
        old_security_version = self.member.security_version
        response = self.client.post(reverse('portal:member_delete', args=[self.member.id]))
        self.assertRedirects(response, reverse('portal:team'))

        self.member.refresh_from_db()
        self.membership.refresh_from_db()
        self.assignment.refresh_from_db()
        self.license.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.member.id, old_user_id)
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.member.first_name, '')
        self.assertEqual(self.member.last_name, '')
        self.assertTrue(self.member.email.startswith('deleted+'))
        self.assertGreater(self.member.security_version, old_security_version)
        self.assertFalse(self.membership.active)
        self.assertIsNotNone(self.assignment.ended_at)
        self.assertEqual(self.license.status, 'free')
        self.assertIsNotNone(self.device.revoked_at)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertTrue(LicenseTerm.objects.filter(pk=self.term.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                actor=self.admin,
                action='company.member_deleted',
                object_id=str(self.membership.id),
            ).exists()
        )

    def test_orders_page_contains_product_payment_reference_and_license_id(self):
        self._login(self.admin)
        response = self.client.get(reverse('portal:orders'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertContains(response, self.product.name)
        self.assertContains(response, '× 1')
        self.assertContains(response, 'paid')
        self.assertContains(response, self.payment.provider_payment_id)
        self.assertContains(response, self.license.license_number)

    @patch('apps.companies.portal_completion_views.queue_email')
    def test_support_request_stores_minimal_tenant_scoped_license_context(self, queue_email):
        self._login(self.member)
        response = self.client.post(
            reverse('portal:help'),
            {
                'license': str(self.license.id),
                'category': 'license',
                'subject': 'Frage zu meiner Lizenz',
                'message': 'Bitte prüfen.',
            },
        )
        self.assertRedirects(response, reverse('portal:help'))
        row = SupportRequest.objects.get(user=self.member)
        self.assertEqual(row.context['user_id'], str(self.member.id))
        self.assertEqual(row.context['company_id'], str(self.company.id))
        self.assertEqual(row.context['license_id'], str(self.license.id))
        self.assertIn('submitted_at', row.context)
        self.assertNotIn('token', row.context)
        self.assertNotIn('password', row.context)
        self.assertEqual(queue_email.call_count, 2)

    @patch('apps.companies.portal_completion_views.queue_email')
    def test_support_license_context_cannot_cross_tenant(self, queue_email):
        other_company = Company.objects.create(
            customer_number='PM-C-PORTAL-OTHER',
            name='Other GmbH',
            email='other@example.test',
            country='DE',
        )
        other_license = License.objects.create(
            company=other_company,
            product=self.product,
            status='free',
            valid_from=self.now,
            valid_until=self.now + timedelta(days=365),
        )
        self._login(self.member)
        response = self.client.post(
            reverse('portal:help'),
            {
                'license': str(other_license.id),
                'category': 'license',
                'subject': 'Cross tenant',
                'message': 'Nein',
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SupportRequest.objects.filter(user=self.member).exists())
        queue_email.assert_not_called()
