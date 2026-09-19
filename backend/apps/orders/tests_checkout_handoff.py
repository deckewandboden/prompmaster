from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.companies.models import Company, Membership
from apps.legal.models import LegalDocument
from apps.orders.models import Order
from apps.orders.services import MAX_PURCHASE_QUANTITY
from apps.payments.models import Payment


class PurchaseHandoffTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user(
            'checkout-admin@example.test',
            'Checkout-Flow-Password-2026!',
            first_name='Checkout',
            last_name='Admin',
            email_verified_at=now,
        )
        self.company = Company.objects.create(
            customer_number='C-CHECKOUT-HANDOFF',
            name='Checkout Handoff GmbH',
            email=self.user.email,
            street='Testweg',
            house_number='7',
            postal_code='57072',
            city='Siegen',
            country='DE',
        )
        Membership.objects.create(
            company=self.company,
            user=self.user,
            role='admin',
            active=True,
        )
        self.product = Product.objects.create(
            code='PRO',
            name='PromptMaster Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        ProductPrice.objects.create(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=now,
        )
        TaxRule.objects.create(
            country='DE',
            customer_type='company',
            tax_rate=Decimal('19.00'),
            active=True,
        )
        for doc_type in ('terms', 'privacy'):
            LegalDocument.objects.create(
                doc_type=doc_type,
                version='checkout-handoff-v1',
                content=f'Checkout handoff {doc_type}',
                valid_from=now,
                active=True,
            )

        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['authenticated_at'] = now.timestamp()
        session['last_activity_at'] = now.timestamp()
        session.save()

    def test_marketing_quantity_is_prefilled_and_clamped_to_backend_limit(self):
        response = self.client.get('/portal/licenses/buy/?quantity=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['quantity'], 7)
        self.assertContains(response, 'value="7"')

        response = self.client.get('/portal/licenses/buy/?quantity=999999')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['form'].initial['quantity'],
            MAX_PURCHASE_QUANTITY,
        )

        response = self.client.get('/portal/licenses/buy/?quantity=invalid')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['quantity'], 1)

    @patch('apps.companies.portal.MollieClient.create_payment')
    def test_checkout_creates_order_and_payment_for_selected_quantity(self, create_payment):
        create_payment.return_value = {
            'id': 'tr_checkout_handoff',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/pay'}},
        }
        response = self.client.post(
            '/portal/licenses/buy/?quantity=7',
            {
                'quantity': '7',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.example.test/pay')

        order = Order.objects.get(company=self.company)
        self.assertEqual(order.status, 'payment_open')
        self.assertEqual(order.gross_total, Decimal('251.16'))
        self.assertEqual(order.items.get().quantity, 7)

        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.provider_payment_id, 'tr_checkout_handoff')
        self.assertEqual(payment.amount, Decimal('251.16'))
        self.assertEqual(create_payment.call_args.kwargs['amount'], Decimal('251.16'))


class PublicCatalogPurchaseLimitTests(TestCase):
    def test_public_catalog_matches_server_purchase_limit(self):
        response = self.client.get('/catalog.json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['maxQuantity'], MAX_PURCHASE_QUANTITY)
