"""Cross-feature checkout acceptance: coupons must not bypass signed legal offers.

All payment calls are mocked. No real provider, email or production service is used.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.companies.models import Company, Membership
from apps.legal.models import LegalAcceptance
from apps.licenses.models import License
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.vouchers.models import VoucherRedemption
from apps.vouchers.services import issue_vouchers


@override_settings(
    LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=True,
    LEGAL_TRANSLATIONS_PUBLIC_ENABLED=False,
)
class SignedVoucherCheckoutIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        call_command(
            'seed_legal_documents_2026', vat_id='DE123456789',
            stdout=StringIO(),
        )
        cls.staff = User.objects.create_user(
            'signed-voucher-staff@example.test',
            'Synthetic-Staff-Password-2026!',
            is_staff=True, is_superuser=True, email_verified_at=now,
        )
        cls.buyer = User.objects.create_user(
            'signed-voucher-buyer@example.test',
            'Synthetic-Buyer-Password-2026!',
            email_verified_at=now,
        )
        cls.company = Company.objects.create(
            name='Signed Voucher QA GmbH', customer_number='SV-2026-QA',
            email=cls.buyer.email, street='Testweg', postal_code='57072',
            city='Siegen', country='DE',
        )
        Membership.objects.create(
            company=cls.company, user=cls.buyer, role='admin',
        )
        cls.product = Product.objects.create(
            code='PRO', name='PROMPTFINISHER Pro',
            default_license_days=365, default_device_limit=2,
            reminder_1_days=60, reminder_2_days=30,
            critical_warning_days=7,
        )
        ProductPrice.objects.create(
            product=cls.product, price_type='new', gross_amount=Decimal('35.88'),
            currency='EUR', valid_from=now,
        )
        TaxRule.objects.create(
            country='DE', customer_type='company',
            tax_rate=Decimal('19.00'), active=True,
        )

    def setUp(self):
        self.client.force_login(self.buyer)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = self.buyer.security_version
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session['two_factor_ok'] = True
        session.save()
        self.voucher, self.code = issue_vouchers(
            actor=self.staff,
            title='Signed legal + voucher integration',
            kind='percent', product=self.product,
            percent_off=25, max_redemptions=2,
            bound_company=self.company,
            starts_at=timezone.now() - timedelta(minutes=1),
            expires_at=timezone.now() + timedelta(days=2),
        )[0]

    def _checkout_form(self, token):
        return {
            'quantity': '2',
            'voucher_code': self.code,
            'accept_terms': 'on',
            'accept_privacy': 'on',
            'accept_license': 'on',
            'legal_snapshot_token': token,
        }

    def _signed_offer(self):
        response = self.client.get('/portal/licenses/buy/')
        self.assertEqual(response.status_code, 200)
        offer = response.context['legal_snapshot']
        self.assertTrue(offer and offer['token'])
        return offer

    @patch('apps.companies.portal.MollieClient')
    @patch('apps.companies.portal.mollie_runtime_ready', return_value=True)
    def test_discounted_buy_preserves_signed_documents_and_reserved_quota(
        self, _ready, client_class,
    ):
        offer = self._signed_offer()
        client_class.return_value.create_payment.return_value = {
            'id': 'tr_signed_voucher_company_qa',
            'status': 'open',
            '_links': {
                'checkout': {'href': 'https://checkout.example.test/signed-voucher'}
            },
        }
        response = self.client.post(
            '/portal/licenses/buy/', self._checkout_form(offer['token']),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'], 'https://checkout.example.test/signed-voucher',
        )
        order = Order.objects.get()
        self.assertEqual(order.gross_total, Decimal('53.82'))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(order.billing_snapshot['legal_offer']['verification'],
                         'signed_session_bound_document_offer')
        self.assertEqual(
            set(order.billing_snapshot['legal_offer']['documents']),
            {'terms', 'privacy', 'license'},
        )
        self.assertEqual(LegalAcceptance.objects.filter(order=order).count(), 3)
        self.assertEqual(
            VoucherRedemption.objects.get(order=order).status, 'reserved',
        )
        self.voucher.refresh_from_db()
        self.assertEqual(self.voucher.used_count, 1)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(client_class.return_value.create_payment.call_count, 1)
        # The accepted offer is one-use and cannot be replayed after handoff.
        self.assertEqual(
            self.client.get(offer['documents']['terms']['url']).status_code,
            409,
        )

    @patch('apps.companies.portal.MollieClient')
    @patch('apps.companies.portal.mollie_runtime_ready', return_value=True)
    def test_tampered_or_missing_legal_offer_cannot_reserve_voucher(
        self, _ready, client_class,
    ):
        offer = self._signed_offer()
        bad = ('a' if offer['token'][0] != 'a' else 'b') + offer['token'][1:]
        for token in ('', bad):
            with self.subTest(token_present=bool(token)):
                response = self.client.post(
                    '/portal/licenses/buy/', self._checkout_form(token),
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Order.objects.exists())
                self.assertFalse(VoucherRedemption.objects.exists())
                self.voucher.refresh_from_db()
                self.assertEqual(self.voucher.used_count, 0)
        client_class.return_value.create_payment.assert_not_called()

    @patch('apps.companies.portal.MollieClient')
    @patch('apps.companies.portal.mollie_runtime_ready', return_value=True)
    def test_signed_discounted_renewal_requires_valid_offer(
        self, _ready, client_class,
    ):
        now = timezone.now()
        ProductPrice.objects.create(
            product=self.product, price_type='renewal',
            gross_amount=Decimal('35.88'), currency='EUR',
            valid_from=now - timedelta(minutes=2),
        )
        license_obj = License.objects.create(
            company=self.company, product=self.product, status='active',
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=60),
        )
        voucher, code = issue_vouchers(
            actor=self.staff, title='Signed renewal and discount QA',
            kind='percent', product=self.product, percent_off=25,
            max_redemptions=1, bound_company=self.company,
            allow_renewal=True, starts_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=2),
        )[0]
        url = f'/portal/licenses/{license_obj.pk}/renew/'
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        offer = page.context['legal_snapshot']
        payload = {
            'voucher_code': code, 'accept_terms': 'on',
            'accept_privacy': 'on', 'accept_license': 'on',
            'legal_snapshot_token': offer['token'],
        }
        forged = dict(payload)
        token = payload['legal_snapshot_token']
        forged['legal_snapshot_token'] = ('b' if token[0] != 'b' else 'c') + token[1:]
        for attempt in ({**payload, 'legal_snapshot_token': ''}, forged):
            with self.subTest(token_present=bool(attempt['legal_snapshot_token'])):
                blocked = self.client.post(url, attempt)
                self.assertEqual(blocked.status_code, 200)
                self.assertFalse(Order.objects.exists())
                self.assertFalse(VoucherRedemption.objects.exists())
                self.assertFalse(LegalAcceptance.objects.exists())
                self.assertFalse(Payment.objects.exists())
                voucher.refresh_from_db()
                self.assertEqual(voucher.used_count, 0)
        client_class.return_value.create_payment.assert_not_called()

        client_class.return_value.create_payment.return_value = {
            'id': 'tr_signed_renewal_discount_qa', 'status': 'open',
            '_links': {
                'checkout': {'href': 'https://checkout.example.test/signed-renewal'}
            },
        }
        result = self.client.post(url, payload)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            result['Location'], 'https://checkout.example.test/signed-renewal',
        )
        order = Order.objects.get(company=self.company)
        self.assertEqual(order.gross_total, Decimal('26.91'))
        self.assertEqual(order.items.get().target_license_id, license_obj.pk)
        self.assertEqual(order.items.get().quantity, 1)
        self.assertEqual(order.billing_snapshot['legal_offer']['verification'],
                         'signed_session_bound_document_offer')
        self.assertEqual(LegalAcceptance.objects.filter(order=order).count(), 3)
        self.assertEqual(VoucherRedemption.objects.get(
            order=order, voucher=voucher,
        ).status, 'reserved')
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(
            client_class.return_value.create_payment.call_args.kwargs['amount'],
            Decimal('26.91'),
        )
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)
        self.assertEqual(
            self.client.get(offer['documents']['terms']['url']).status_code,
            409,
        )
