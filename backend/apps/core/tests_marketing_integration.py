from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.prompts.models import PromptApplication


class PublicMarketingCatalogTests(TestCase):
    def setUp(self):
        self.free = Product.objects.create(
            code='FREE', name='PromptMaster Free', active=True, visible=True,
            purchasable=False, default_license_days=365, default_device_limit=1,
            reminder_1_days=60, reminder_2_days=30, critical_warning_days=7,
        )
        self.pro = Product.objects.create(
            code='PRO', name='PromptMaster Pro', active=True, visible=True,
            purchasable=True, default_license_days=365, default_device_limit=2,
            reminder_1_days=60, reminder_2_days=30, critical_warning_days=7,
        )
        ProductPrice.objects.create(
            product=self.pro, price_type='new', gross_amount=Decimal('35.88'),
            currency='EUR', valid_from=timezone.now(), active=True,
        )
        TaxRule.objects.create(country='DE', customer_type='company', tax_rate=Decimal('19.00'), active=True)
        PromptApplication.objects.create(code='copilot_chat', name='Copilot Chat', sort_order=0)
        PromptApplication.objects.create(code='outlook', name='Outlook', sort_order=1)

    def test_public_catalog_matches_marketing_contract(self):
        response = self.client.get('/catalog.json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['priceBasis'], 'gross')
        self.assertEqual(payload['taxBasisPoints'], 1900)
        self.assertEqual(payload['freeUrl'], '/free/')
        self.assertTrue(payload['checkoutEnabled'])
        self.assertTrue(payload['loginEnabled'])
        self.assertEqual(payload['proApplicationCount'], 2)
        self.assertEqual(payload['proApplicationNames'], ['Copilot Chat', 'Outlook'])
        pro = next(p for p in payload['products'] if p['id'] == 'PROMPTMASTER_PRO')
        self.assertEqual(pro['monthlyGrossCents'], 299)
        self.assertEqual(pro['annualGrossCents'], 3588)
        self.assertEqual(pro['termMonths'], 12)
