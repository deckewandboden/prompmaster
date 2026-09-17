from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, TaxRule
from apps.catalog.services import create_price_version, current_price
from apps.companies.models import PrivateCustomerProfile
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.notifications.tasks import sync_license_states
from apps.orders.models import Order
from apps.orders.services import create_order


class PriceAndRenewalContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-PRICE-CONTRACT',
            name='PromptMaster Pro Price Contract',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.new_price = create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            currency='EUR',
            valid_from=self.now - timedelta(days=2),
        )
        self.renewal_price = create_price_version(
            product=self.product,
            price_type='renewal',
            gross_amount=Decimal('31.44'),
            currency='EUR',
            valid_from=self.now - timedelta(days=2),
        )
        self.user = User.objects.create_user(
            'price-contract@example.test',
            'ReleaseRulePassword-123!',
            first_name='Paula',
            last_name='Preis',
            email_verified_at=self.now,
        )
        PrivateCustomerProfile.objects.create(
            user=self.user,
            customer_number='PM-P-PRICE-001',
            street='Preisweg',
            house_number='1',
            postal_code='57000',
            city='Siegen',
            country='DE',
        )
        TaxRule.objects.create(
            country='DE',
            customer_type='private',
            tax_rate=Decimal('19.00'),
            active=True,
        )

    def test_price_versioning_closes_old_version_without_overwriting_it(self):
        switch_at = self.now + timedelta(days=1)
        newer = create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('39.90'),
            currency='EUR',
            valid_from=switch_at,
        )

        self.new_price.refresh_from_db()
        self.assertEqual(self.new_price.gross_amount, Decimal('35.88'))
        self.assertEqual(self.new_price.valid_until, switch_at)
        self.assertEqual(current_price(self.product, 'new', at=self.now).pk, self.new_price.pk)
        self.assertEqual(
            current_price(self.product, 'new', at=switch_at + timedelta(seconds=1)).pk,
            newer.pk,
        )

    def test_checkout_uses_separate_new_and_renewal_prices(self):
        license_obj = License.objects.create(
            owner_user=self.user,
            product=self.product,
            status='expired',
            valid_from=self.now - timedelta(days=400),
            valid_until=self.now - timedelta(days=35),
        )

        new_order = create_order(
            user=self.user,
            product=self.product,
            quantity=1,
            idempotency_key='price-contract-new',
        )
        renewal_order = create_order(
            user=self.user,
            product=self.product,
            quantity=1,
            target_license=license_obj,
            idempotency_key='price-contract-renewal',
        )

        new_item = new_order.items.get()
        renewal_item = renewal_order.items.get()
        self.assertEqual(new_item.price_version_id, self.new_price.id)
        self.assertEqual(new_item.unit_gross, Decimal('35.88'))
        self.assertEqual(new_order.gross_total, Decimal('35.88'))
        self.assertEqual(renewal_item.price_version_id, self.renewal_price.id)
        self.assertEqual(renewal_item.unit_gross, Decimal('31.44'))
        self.assertEqual(renewal_order.gross_total, Decimal('31.44'))

    def test_order_price_snapshot_survives_later_price_change(self):
        order = create_order(
            user=self.user,
            product=self.product,
            quantity=1,
            idempotency_key='price-contract-snapshot',
        )
        item = order.items.get()
        original_price_id = item.price_version_id

        create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('39.90'),
            currency='EUR',
            valid_from=self.now + timedelta(days=1),
        )

        item.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(item.price_version_id, original_price_id)
        self.assertEqual(item.unit_gross, Decimal('35.88'))
        self.assertEqual(order.gross_total, Decimal('35.88'))
        self.assertEqual(item.price_version.gross_amount, Decimal('35.88'))

    def test_expiry_does_not_auto_renew_or_delete_customer_data(self):
        order = create_order(
            user=self.user,
            product=self.product,
            quantity=1,
            idempotency_key='price-contract-expiry',
        )
        order_item = order.items.get()
        valid_from = self.now - timedelta(days=366)
        valid_until = self.now - timedelta(days=1)
        license_obj = License.objects.create(
            owner_user=self.user,
            product=self.product,
            status='active',
            valid_from=valid_from,
            valid_until=valid_until,
        )
        LicenseAssignment.objects.create(license=license_obj, user=self.user)
        LicenseTerm.objects.create(
            license=license_obj,
            order_item=order_item,
            valid_from=valid_from,
            valid_until=valid_until,
            paid_gross_amount=Decimal('35.88'),
            status='active',
        )
        terms_before = LicenseTerm.objects.filter(license=license_obj).count()

        changed = sync_license_states.run()

        license_obj.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual(license_obj.status, 'expired')
        self.assertEqual(license_obj.valid_until, valid_until)
        self.assertEqual(LicenseTerm.objects.filter(license=license_obj).count(), terms_before)
        self.assertTrue(self.user.is_active)
        self.assertTrue(PrivateCustomerProfile.objects.filter(user=self.user).exists())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
