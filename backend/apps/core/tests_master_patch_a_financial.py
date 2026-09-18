from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company
from apps.licenses.models import License, LicenseTerm
from apps.orders.models import Order, OrderItem


class LicenseDetailFinancialRbacTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.staff = User.objects.create_user(
            'license-reader-financial@example.test',
            'Financial-Rbac-Password-42!',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-financial-rbac-2fa',
        )
        self.role = Role.objects.create(
            code='license-reader-financial',
            name='License Reader Financial',
        )
        licenses_read = Permission.objects.create(
            code='licenses.read',
            name='Lizenzen lesen',
        )
        self.role.permissions.add(licenses_read)
        UserRole.objects.create(user=self.staff, role=self.role)

        company = Company.objects.create(
            customer_number='PM-C-FIN-RBAC',
            name='Financial RBAC GmbH',
            email='financial-rbac@example.test',
        )
        product = Product.objects.create(
            code='FIN-RBAC-PRO',
            name='Financial RBAC Pro',
        )
        price = ProductPrice.objects.create(
            product=product,
            price_type='new',
            gross_amount=Decimal('987.65'),
            currency='EUR',
            valid_from=now - timedelta(days=2),
        )
        order = Order.objects.create(
            order_number='PM-O-FIN-RBAC-SECRET',
            company=company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('987.65'),
            tax_total=Decimal('157.70'),
            billing_snapshot={},
            idempotency_key='financial-rbac-order',
        )
        item = OrderItem.objects.create(
            order=order,
            product=product,
            price_version=price,
            quantity=1,
            unit_gross=Decimal('987.65'),
            unit_net=Decimal('829.96'),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=product.name,
        )
        self.license = License.objects.create(
            company=company,
            product=product,
            status='active',
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=364),
        )
        LicenseTerm.objects.create(
            license=self.license,
            order_item=item,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=364),
            paid_gross_amount=Decimal('987.65'),
            status='active',
        )

        self.client.force_login(self.staff)
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now.timestamp()
        session['last_activity_at'] = now.timestamp()
        session.save()

    def grant(self, code):
        permission, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'name': code},
        )
        self.role.permissions.add(permission)

    def test_license_reader_sees_only_license_domain_term_fields(self):
        url = f'/ns-admin/licenses/{self.license.id}/'

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lizenzperioden')
        self.assertNotContains(response, '<th>Bezahlt</th>', html=True)
        self.assertNotContains(response, '<th>Bestellung</th>', html=True)
        self.assertNotContains(response, 'PM-O-FIN-RBAC-SECRET')

        self.grant('payments.read')
        response = self.client.get(url)
        self.assertContains(response, '<th>Bezahlt</th>', html=True)
        self.assertNotContains(response, '<th>Bestellung</th>', html=True)
        self.assertNotContains(response, 'PM-O-FIN-RBAC-SECRET')

        self.grant('orders.read')
        response = self.client.get(url)
        self.assertContains(response, '<th>Bezahlt</th>', html=True)
        self.assertContains(response, '<th>Bestellung</th>', html=True)
        self.assertContains(response, 'PM-O-FIN-RBAC-SECRET')


    def test_payments_only_reader_gets_payment_navigation_without_orders_permission(self):
        self.grant('payments.read')
        response = self.client.get('/ns-admin/payments/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Zahlungen</span>', html=False)
        self.assertNotContains(response, 'Bestellungen &amp; Zahlungen')
