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

class PublicCheckoutFlowTests(TestCase):
    def setUp(self):
        now = timezone.now()
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
        for customer_type in ('company', 'private'):
            TaxRule.objects.create(
                country='DE',
                customer_type=customer_type,
                tax_rate=Decimal('19.00'),
                active=True,
            )
        for doc_type in ('terms', 'privacy', 'withdrawal'):
            LegalDocument.objects.create(
                doc_type=doc_type,
                version='public-checkout-v1',
                content=f'Public checkout {doc_type}',
                valid_from=now,
                active=True,
            )

    @staticmethod
    def company_payload(quantity='3', email='new-company@example.test'):
        return {
            'quantity': quantity,
            'customer_type': 'company',
            'first_name': 'Neue',
            'last_name': 'Kundin',
            'email': email,
            'phone': '+49 271 123456',
            'company_name': 'Neue Checkout GmbH',
            'legal_form': 'GmbH',
            'vat_id': 'DE123456789',
            'tax_number': '123/456/78901',
            'street': 'Marktstraße',
            'house_number': '12',
            'postal_code': '57072',
            'city': 'Siegen',
            'country': 'DE',
            'accept_terms': 'on',
            'accept_privacy': 'on',
        }

    @staticmethod
    def private_payload(quantity='2', email='new-private@example.test'):
        return {
            'quantity': quantity,
            'customer_type': 'private',
            'first_name': 'Private',
            'last_name': 'Kundin',
            'email': email,
            'phone': '',
            'company_name': '',
            'legal_form': '',
            'vat_id': '',
            'tax_number': '',
            'street': 'Privatweg',
            'house_number': '7',
            'postal_code': '57072',
            'city': 'Siegen',
            'country': 'DE',
            'accept_terms': 'on',
            'accept_privacy': 'on',
            'accept_withdrawal': 'on',
        }

    @patch('apps.payments.mollie.MollieClient.create_payment')
    def test_public_company_checkout_creates_customer_order_and_payment(self, create_payment):
        create_payment.return_value = {
            'id': 'tr_public_company',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/company'}},
        }
        response = self.client.post(
            '/api/v1/checkout/start/',
            self.company_payload(),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.example.test/company')

        user = User.objects.get(email='new-company@example.test')
        self.assertFalse(user.has_usable_password())
        self.assertIsNone(user.email_verified_at)
        self.assertTrue(user.two_factor_required)

        company = Company.objects.get(memberships__user=user, memberships__active=True)
        self.assertEqual(company.name, 'Neue Checkout GmbH')
        self.assertEqual(company.street, 'Marktstraße')
        self.assertEqual(company.vat_id, 'DE123456789')
        self.assertEqual(
            Membership.objects.get(company=company, user=user).role,
            'admin',
        )

        order = Order.objects.get(company=company)
        self.assertEqual(order.status, 'payment_open')
        self.assertEqual(order.items.get().quantity, 3)
        self.assertEqual(order.billing_snapshot['source'], 'public_checkout')
        self.assertEqual(order.billing_snapshot['company'], 'Neue Checkout GmbH')
        self.assertTrue(Payment.objects.filter(
            order=order,
            provider_payment_id='tr_public_company',
            amount=Decimal('107.64'),
        ).exists())
        self.assertEqual(
            user.legalacceptance_set.filter(order__isnull=True).count(),
            2,
        )
        self.assertEqual(
            user.legalacceptance_set.filter(order=order).count(),
            2,
        )
        self.assertEqual(
            create_payment.call_args.kwargs['redirect_url'],
            'http://testserver/checkout/success/',
        )

    @patch('apps.payments.mollie.MollieClient.create_payment')
    def test_public_private_checkout_creates_profile_and_withdrawal_acceptance(self, create_payment):
        create_payment.return_value = {
            'id': 'tr_public_private',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/private'}},
        }
        response = self.client.post(
            '/api/v1/checkout/start/',
            self.private_payload(),
        )
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email='new-private@example.test')
        profile = user.private_customer
        self.assertEqual(profile.street, 'Privatweg')
        self.assertEqual(profile.city, 'Siegen')
        order = Order.objects.get(private_user=user)
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(order.billing_snapshot['source'], 'public_checkout')
        self.assertEqual(
            user.legalacceptance_set.filter(order=order).count(),
            3,
        )

    @patch('apps.payments.mollie.MollieClient.create_payment')
    def test_public_checkout_existing_email_is_sent_to_login_without_duplicate(self, create_payment):
        User.objects.create_user(
            'existing@example.test',
            'Existing-Password-2026!',
            first_name='Existing',
            last_name='Customer',
        )
        response = self.client.post(
            '/api/v1/checkout/start/',
            self.company_payload(email='existing@example.test'),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/auth/login/?next='))
        self.assertEqual(User.objects.filter(email='existing@example.test').count(), 1)
        self.assertFalse(create_payment.called)

    def test_checkout_csrf_endpoint_supports_http_only_cookie_flow(self):
        client = self.client_class(enforce_csrf_checks=True)
        token_response = client.get('/api/v1/checkout/csrf/')
        self.assertEqual(token_response.status_code, 200)
        token = token_response.json()['csrfToken']
        self.assertTrue(token)
        response = client.post(
            '/api/v1/checkout/start/',
            self.company_payload(),
            HTTP_X_CSRFTOKEN=token,
        )
        # CSRF must pass; provider setup may fail because this test deliberately
        # does not mock Mollie credentials.
        self.assertNotEqual(response.status_code, 403)

    @patch('apps.payments.mollie.MollieClient.create_payment')
    def test_public_checkout_order_is_visible_in_customer_and_netstyle_backends(
        self,
        create_payment,
    ):
        create_payment.return_value = {
            'id': 'tr_cross_backend',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/cross'}},
        }
        response = self.client.post(
            '/api/v1/checkout/start/',
            self.company_payload(
                quantity='4',
                email='cross-backend@example.test',
            ),
        )
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email='cross-backend@example.test')
        company = Company.objects.get(
            memberships__user=user,
            memberships__active=True,
        )
        order = Order.objects.get(company=company)
        now = timezone.now()

        # The same order must be visible from the real customer portal.
        user.email_verified_at = now
        user.two_factor_required = False
        user.save(update_fields=[
            'email_verified_at',
            'two_factor_required',
            'updated_at',
        ])
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['authenticated_at'] = now.timestamp()
        session['last_activity_at'] = now.timestamp()
        session.save()
        portal_response = self.client.get('/portal/orders/')
        self.assertEqual(portal_response.status_code, 200)
        self.assertContains(portal_response, order.order_number)

        # Netstyle must see that exact same database order, not a copy.
        staff = User.objects.create_user(
            'checkout-auditor@example.test',
            'Checkout-Auditor-Password-2026!',
            first_name='Checkout',
            last_name='Auditor',
            email_verified_at=now,
            is_staff=True,
            is_superuser=True,
            two_factor_required=False,
        )
        self.client.force_login(staff)
        session = self.client.session
        session['security_version'] = staff.security_version
        session['authenticated_at'] = now.timestamp()
        session['last_activity_at'] = now.timestamp()
        session.save()
        admin_response = self.client.get(
            f'/ns-admin/customers/{company.id}/orders/'
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, order.order_number)
        self.assertEqual(
            Order.objects.filter(pk=order.pk, company=company).count(),
            1,
        )

    @patch('apps.payments.services._queue_after_commit')
    @patch('apps.payments.mollie.MollieClient.create_payment')
    def test_paid_public_checkout_activates_license_and_queues_account_activation(
        self,
        create_payment,
        queue_after_commit,
    ):
        from apps.payments.services import process_provider_state

        create_payment.return_value = {
            'id': 'tr_public_paid',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/paid'}},
        }
        self.client.post(
            '/api/v1/checkout/start/',
            self.private_payload(quantity='1', email='paid-public@example.test'),
        )
        user = User.objects.get(email='paid-public@example.test')
        order = Order.objects.get(private_user=user)

        process_provider_state(
            'tr_public_paid',
            {
                'id': 'tr_public_paid',
                'status': 'paid',
                'amount': {'value': '35.88', 'currency': 'EUR'},
                'amountRefunded': {'value': '0.00', 'currency': 'EUR'},
                'method': 'ideal',
            },
            chargebacks_payload={'_embedded': {'chargebacks': []}},
        )

        order.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(user.owned_licenses.count(), 1)
        self.assertEqual(user.owned_licenses.get().status, 'active')
        activation_calls = [
            call for call in queue_after_commit.call_args_list
            if call.args and call.args[0] == 'password_reset'
        ]
        self.assertEqual(len(activation_calls), 1)
        self.assertEqual(activation_calls[0].args[1], user.email)
        self.assertIn(
            '/auth/checkout-activation/',
            activation_calls[0].args[2]['url'],
        )

