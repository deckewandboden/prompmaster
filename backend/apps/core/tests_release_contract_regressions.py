from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, TaxRule
from apps.catalog.services import create_price_version, current_price
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.licenses.models import License, LicenseAssignment, LicenseReminder, LicenseTerm
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.notifications.services import queue_email
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

class TenantHistoryReleaseRegressionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'tenant-history-staff@example.test',
            'Tenant-History-Staff-Password-2026!',
            is_staff=True,
        )
        role = Role.objects.create(code='tenant-history-gate', name='Tenant History Gate')
        permissions = []
        for code in ('customers.read', 'email.read', 'audit.read'):
            permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code})
            permissions.append(permission)
        role.permissions.set(permissions)
        UserRole.objects.create(user=self.staff, role=role)

        self.client.force_login(self.staff)
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = True
        session.save()

        self.company = Company.objects.create(
            customer_number='PM-C-HISTORY-A',
            name='History A GmbH',
            email='history-a@example.test',
            country='DE',
        )
        self.other_company = Company.objects.create(
            customer_number='PM-C-HISTORY-B',
            name='History B GmbH',
            email='history-b@example.test',
            country='DE',
        )
        self.company_member = User.objects.create_user(
            'history-member@example.test',
            'History-Member-Password-2026!',
        )
        self.membership = Membership.objects.create(
            company=self.company,
            user=self.company_member,
            role='member',
            active=True,
        )
        self.private_user = User.objects.create_user(
            'history-private@example.test',
            'History-Private-Password-2026!',
        )
        self.private_profile = PrivateCustomerProfile.objects.create(
            user=self.private_user,
            customer_number='PM-P-HISTORY-A',
            street='Historienweg',
            house_number='1',
            postal_code='57072',
            city='Siegen',
            country='DE',
        )

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_queue_persists_explicit_customer_scope(self, delay):
        EmailTemplate.objects.create(
            code='release-scope-gate',
            subject='Status {value}',
            body_text='Status {value}',
            active=True,
        )
        with self.captureOnCommitCallbacks(execute=True):
            message = queue_email(
                'release-scope-gate',
                'scope@example.test',
                {'value': 'Scoped'},
                scope_company='company-42',
                scope_user='user-42',
            )

        message.refresh_from_db()
        self.assertEqual(message.context['pm_scope_company_id'], 'company-42')
        self.assertEqual(message.context['pm_scope_user_id'], 'user-42')
        self.assertEqual(message.subject, 'Status Scoped')
        delay.assert_called_once_with(str(message.id))

    def test_company_email_history_uses_explicit_company_scope_only(self):
        shared_recipient = 'shared-recipient@example.test'
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='COMPANY-SCOPE-MARKER',
            context={'pm_scope_company_id': str(self.company.id)},
        )
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='OTHER-COMPANY-MARKER',
            context={'pm_scope_company_id': str(self.other_company.id)},
        )
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='UNSCOPED-MARKER',
            context={},
        )

        response = self.client.get(f'/ns-admin/customers/{self.company.id}/emails/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'COMPANY-SCOPE-MARKER')
        self.assertNotContains(response, 'OTHER-COMPANY-MARKER')
        self.assertNotContains(response, 'UNSCOPED-MARKER')

    def test_private_email_history_uses_explicit_user_scope_only(self):
        EmailMessage.objects.create(
            recipient=self.private_user.email,
            subject='PRIVATE-SCOPE-MARKER',
            context={'pm_scope_user_id': str(self.private_user.id)},
        )
        EmailMessage.objects.create(
            recipient=self.private_user.email,
            subject='WRONG-PRIVATE-SCOPE-MARKER',
            context={'pm_scope_user_id': str(self.company_member.id)},
        )
        EmailMessage.objects.create(
            recipient=self.private_user.email,
            subject='PRIVATE-UNSCOPED-MARKER',
            context={},
        )

        response = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/emails/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PRIVATE-SCOPE-MARKER')
        self.assertNotContains(response, 'WRONG-PRIVATE-SCOPE-MARKER')
        self.assertNotContains(response, 'PRIVATE-UNSCOPED-MARKER')

    def test_company_audit_excludes_global_identity_events(self):
        AuditEvent.objects.create(
            actor=self.company_member,
            action='AUTH-GLOBAL-MARKER',
            object_type='User',
            object_id=str(self.company_member.id),
            changes={},
        )
        AuditEvent.objects.create(
            actor=self.staff,
            action='MEMBERSHIP-TENANT-MARKER',
            object_type='Membership',
            object_id=str(self.membership.id),
            changes={},
        )

        response = self.client.get(f'/ns-admin/customers/{self.company.id}/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MEMBERSHIP-TENANT-MARKER')
        self.assertNotContains(response, 'AUTH-GLOBAL-MARKER')

