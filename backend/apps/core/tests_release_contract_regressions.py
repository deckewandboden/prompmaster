from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, TaxRule
from apps.catalog.services import create_price_version, current_price
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.licenses.models import License, LicenseAssignment, LicenseReminder, LicenseTerm
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.notifications.tasks import (
    _sync_reminder_delivery,
    schedule_license_reminders,
    sync_license_states,
)
from apps.orders.models import Order
from apps.orders.services import create_order


class PriceAndRenewalReleaseRegressionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-PRICE-RELEASE-GATE',
            name='PromptMaster Pro Price Release Gate',
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
            'price-release-gate@example.test',
            'Price-Release-Gate-Password-2026!',
            first_name='Paula',
            last_name='Preis',
            email_verified_at=self.now,
        )
        PrivateCustomerProfile.objects.create(
            user=self.user,
            customer_number='PM-P-PRICE-GATE',
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

    def test_price_versioning_closes_previous_version_without_overwriting_history(self):
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
            idempotency_key='price-release-gate-new',
        )
        renewal_order = create_order(
            user=self.user,
            product=self.product,
            quantity=1,
            target_license=license_obj,
            idempotency_key='price-release-gate-renewal',
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
            idempotency_key='price-release-gate-snapshot',
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
            idempotency_key='price-release-gate-expiry',
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


class ReminderIdempotencyReleaseRegressionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-REMINDER-RELEASE-GATE',
            name='PromptMaster Pro Reminder Release Gate',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-REMINDER-GATE',
            name='Reminder Gate GmbH',
            email='reminder-gate@example.test',
            country='DE',
        )
        self.admin = User.objects.create_user(
            'reminder-gate-admin@example.test',
            'Reminder-Gate-Admin-Password-2026!',
            first_name='Reminder',
            last_name='Admin',
        )
        self.member = User.objects.create_user(
            'reminder-gate-member@example.test',
            'Reminder-Gate-Member-Password-2026!',
            first_name='Reminder',
            last_name='Member',
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
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=320),
            valid_until=self.now + timedelta(days=45),
        )
        LicenseAssignment.objects.create(license=self.license, user=self.member)
        self.template = EmailTemplate.objects.create(
            code='t60',
            subject='Lizenz {license} läuft aus',
            body_text='Ablauf: {expiry}',
            active=True,
        )

    def test_partial_failure_reuses_same_rows_without_duplicate_recipient_mail(self):
        reminder = LicenseReminder.objects.create(
            license=self.license,
            kind='t60',
            target_valid_until=self.license.valid_until,
            status='error',
            error='Teilfehler',
        )
        sent = EmailMessage.objects.create(
            template=self.template,
            recipient=self.admin.email,
            subject='Admin reminder',
            status='sent',
            sent_at=self.now,
            context={'reminder_id': str(reminder.id)},
        )
        failed = EmailMessage.objects.create(
            template=self.template,
            recipient=self.member.email,
            subject='Member reminder',
            status='failed',
            error='SMTP temporary failure',
            context={'reminder_id': str(reminder.id)},
        )

        with patch('apps.notifications.tasks.send_email_message.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                queued = schedule_license_reminders.run()

        self.assertEqual(queued, 1)
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(reminder.id)).count(),
            2,
        )
        sent.refresh_from_db()
        failed.refresh_from_db()
        reminder.refresh_from_db()
        self.assertEqual(sent.status, 'sent')
        self.assertEqual(failed.status, 'queued')
        self.assertEqual(reminder.status, 'queued')
        delay.assert_called_once_with(str(failed.id))

        with patch('apps.notifications.tasks.send_email_message.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                queued_again = schedule_license_reminders.run()

        self.assertEqual(queued_again, 0)
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(reminder.id)).count(),
            2,
        )
        delay.assert_not_called()

    def test_delivery_sync_tolerates_historical_duplicate_failure_after_success(self):
        reminder = LicenseReminder.objects.create(
            license=self.license,
            kind='t60',
            target_valid_until=self.license.valid_until,
            status='error',
        )
        admin_sent = EmailMessage.objects.create(
            template=self.template,
            recipient=self.admin.email,
            subject='Admin reminder',
            status='sent',
            sent_at=self.now,
            context={'reminder_id': str(reminder.id)},
        )
        EmailMessage.objects.create(
            template=self.template,
            recipient=self.admin.email,
            subject='Legacy duplicate',
            status='failed',
            error='legacy duplicate',
            context={'reminder_id': str(reminder.id)},
        )
        EmailMessage.objects.create(
            template=self.template,
            recipient=self.member.email,
            subject='Member reminder',
            status='sent',
            sent_at=self.now,
            context={'reminder_id': str(reminder.id)},
        )

        _sync_reminder_delivery(admin_sent)

        reminder.refresh_from_db()
        self.assertEqual(reminder.status, 'sent')
        self.assertIsNotNone(reminder.sent_at)
        self.assertEqual(reminder.error, '')

    def test_product_configured_reminder_windows_drive_t60_and_t30(self):
        self.product.reminder_1_days = 45
        self.product.reminder_2_days = 15
        self.product.save(update_fields=['reminder_1_days', 'reminder_2_days', 'updated_at'])
        self.license.valid_until = self.now + timedelta(days=45)
        self.license.save(update_fields=['valid_until', 'updated_at'])
        EmailTemplate.objects.create(
            code='t30',
            subject='T30 {license}',
            body_text='Ablauf: {expiry}',
            active=True,
        )

        with patch('apps.notifications.tasks.send_email_message.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                schedule_license_reminders.run()

        self.assertTrue(
            LicenseReminder.objects.filter(
                license=self.license,
                kind='t60',
                target_valid_until=self.license.valid_until,
            ).exists()
        )

        self.license.valid_until = timezone.now() + timedelta(days=15)
        self.license.save(update_fields=['valid_until', 'updated_at'])
        with patch('apps.notifications.tasks.send_email_message.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                schedule_license_reminders.run()

        self.assertTrue(
            LicenseReminder.objects.filter(
                license=self.license,
                kind='t30',
                target_valid_until=self.license.valid_until,
            ).exists()
        )
