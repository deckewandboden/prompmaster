from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company, Membership
from apps.integrations.models import IntegrationSecret, ServiceAccount
from apps.legal.models import DeletionRequest, LegalAcceptance, LegalDocument
from apps.licenses.models import License
from apps.notifications.models import EmailTemplate
from apps.ops.models import BackupRecord
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.support.models import SupportRequest


class AdminContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.staff = User.objects.create_superuser(
            'admin-contract@example.test',
            'Admin-Contract-Password-42!',
            first_name='Admin',
            last_name='Contract',
            two_factor_required=False,
        )
        self.client.force_login(self.staff)
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = True
        session.save()
        self.company = Company.objects.create(
            customer_number='PM-C-ADMIN-CONTRACT',
            name='Admin Contract GmbH',
            email='admin-contract-company@example.test',
            country='DE',
        )
        self.customer_user = User.objects.create_user(
            'admin-customer@example.test',
            'Admin-Customer-Password-42!',
            email_verified_at=self.now,
        )
        Membership.objects.create(company=self.company, user=self.customer_user, role='admin', active=True)
        product = Product.objects.create(code='ADMIN-PRO', name='Admin Pro')
        License.objects.create(
            company=self.company,
            product=product,
            status='payment_review',
            valid_from=self.now - timedelta(days=30),
            valid_until=self.now + timedelta(days=20),
        )
        self.order = Order.objects.create(
            order_number='PM-O-ADMIN-CONTRACT',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={},
            idempotency_key='admin-contract-order',
        )
        Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_admin_contract_failed',
            status='failed',
            amount=Decimal('35.88'),
            currency='EUR',
        )
        Payment.objects.create(
            order=self.order,
            provider_payment_id='tr_admin_contract_chargeback',
            status='charged_back',
            amount=Decimal('35.88'),
            currency='EUR',
        )
        SupportRequest.objects.create(
            user=self.customer_user,
            company=self.company,
            category='technical',
            subject='Admin dashboard support',
            message='Bitte prüfen.',
        )
        BackupRecord.objects.create(
            status='success',
            provider_ref='backup-admin-contract',
            size_bytes=1024,
            finished_at=self.now,
        )
        IntegrationSecret.objects.create(code='mollie_test', encrypted_value='encrypted', active=True)
        ServiceAccount.objects.create(name='admin-contract-service', token_hash='c' * 64, scopes=['ops.read'], active=True)
        EmailTemplate.objects.create(code='admin_contract_mail', subject='Test', body_text='Body', active=True)
        self.privacy_doc = LegalDocument.objects.create(
            doc_type='privacy',
            version='admin-contract-1',
            content='Datenschutz',
            valid_from=self.now - timedelta(days=1),
            active=True,
        )
        LegalAcceptance.objects.create(user=self.customer_user, document=self.privacy_doc)
        DeletionRequest.objects.create(user=self.customer_user, status='open')

    def test_required_admin_routes_exist(self):
        routes = [
            reverse('ns_admin:email_templates'),
            reverse('ns_admin:users'),
            reverse('ns_admin:customer_company', args=[self.company.id]),
            reverse('ns_admin:customer_privacy', args=[self.company.id]),
            reverse('ns_admin:customer_portal_preview', args=[self.company.id]),
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_customer_navigation_contains_all_required_subareas(self):
        response = self.client.get(reverse('ns_admin:customer_detail', args=[self.company.id]))
        self.assertEqual(response.status_code, 200)
        for label in (
            'Übersicht', 'Unternehmen', 'Benutzer', 'Lizenzen', 'Geräte',
            'Bestellungen', 'Zahlungen', 'E-Mail-Historie', 'Datenschutz', 'Audit',
        ):
            self.assertContains(response, label)

    def test_dashboard_contains_required_business_and_operational_sections(self):
        response = self.client.get(reverse('ns_admin:dashboard'))
        self.assertEqual(response.status_code, 200)
        for label in (
            'Kunden gesamt', 'Aktive Lizenzen', 'Ablauf ≤30 Tage', 'Umsatz 30 Tage',
            'Letzte Bestellungen', 'Produktmix', 'Umsatzentwicklung',
            'Fehlgeschlagene Zahlungen', 'Chargebacks / Zahlung prüfen',
            'Offene Kontaktanfragen', 'Status kompakt', 'Backup', 'Mollie',
        ):
            self.assertContains(response, label)
        self.assertContains(response, 'backup-admin-contract')
        self.assertContains(response, '2 Chargeback / Prüfung')

    def test_portal_preview_is_read_only_render_not_impersonation(self):
        before_user_id = self.client.session.get('_auth_user_id')
        response = self.client.get(reverse('ns_admin:customer_portal_preview', args=[self.company.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get('_auth_user_id'), before_user_id)
        self.assertEqual(str(self.staff.id), str(before_user_id))
        self.assertContains(response, self.company.name)
        self.assertNotEqual(str(self.customer_user.id), str(before_user_id))
