from datetime import timedelta
from unittest.mock import patch
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.companies.services import create_invitation
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment, LicenseReminder
from apps.licenses.services import assign_license, block_license, unblock_license
from apps.orders.models import Order, OrderItem
from apps.payments.services import _activate_order
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.notifications.tasks import _sync_reminder_delivery, schedule_license_reminders

class ReleaseRuleFixture(TestCase):
    def setUp(self):
        self.now=timezone.now(); self.product=Product.objects.create(code='PRO',name='PromptMaster Pro',default_license_days=365,default_device_limit=2,reminder_1_days=60,reminder_2_days=30,critical_warning_days=7)
        self.price=ProductPrice.objects.create(product=self.product,price_type='new',gross_amount=Decimal('35.88'),currency='EUR',valid_from=self.now-timedelta(days=1))
        self.user=User.objects.create_user('kunde@example.test','ReleaseRulePassword-123!',first_name='Klara',last_name='Kunde',email_verified_at=self.now)
        PrivateCustomerProfile.objects.create(user=self.user,customer_number='PM-P-TEST-001',street='Testweg',house_number='1',postal_code='57000',city='Siegen',country='DE')
    def make_order(self,quantity=1,target_license=None,suffix='1'):
        order=Order.objects.create(order_number=f'PM-O-TEST-{suffix}',private_user=self.user,status='draft',currency='EUR',gross_total=Decimal('35.88')*quantity,tax_total=Decimal('5.73')*quantity,billing_snapshot={'customer_type':'private'},idempotency_key=f'test-key-{suffix}')
        OrderItem.objects.create(order=order,product=self.product,price_version=self.price,quantity=quantity,unit_gross=Decimal('35.88'),unit_net=Decimal('30.15'),tax_rate=Decimal('19.00'),product_name_snapshot=self.product.name,target_license=target_license)
        return order

class LicenseLifetimeTests(ReleaseRuleFixture):
    def test_new_purchase_creates_exactly_365_day_licenses(self):
        order=self.make_order(quantity=3,suffix='new'); _activate_order(order,self.now); licenses=list(License.objects.filter(owner_user=self.user)); self.assertEqual(len(licenses),3)
        for lic in licenses: self.assertEqual(lic.valid_until-lic.valid_from,timedelta(days=365)); self.assertEqual(lic.status,'active')
    def test_renewal_before_expiry_adds_365_days_to_existing_end(self):
        old_end=self.now+timedelta(days=100); lic=License.objects.create(owner_user=self.user,product=self.product,status='active',valid_from=self.now-timedelta(days=265),valid_until=old_end); LicenseAssignment.objects.create(license=lic,user=self.user); _activate_order(self.make_order(target_license=lic,suffix='renew-before'),self.now); lic.refresh_from_db(); self.assertEqual(lic.valid_until,old_end+timedelta(days=365))
    def test_renewal_after_expiry_restarts_at_payment_time(self):
        lic=License.objects.create(owner_user=self.user,product=self.product,status='expired',valid_from=self.now-timedelta(days=500),valid_until=self.now-timedelta(days=10)); _activate_order(self.make_order(target_license=lic,suffix='renew-after'),self.now); lic.refresh_from_db(); self.assertEqual(lic.valid_until,self.now+timedelta(days=365))
    def test_paid_activation_is_idempotent(self):
        order=self.make_order(quantity=2,suffix='idempotent'); _activate_order(order,self.now); n=License.objects.filter(owner_user=self.user).count(); _activate_order(order,self.now+timedelta(seconds=5)); self.assertEqual(License.objects.filter(owner_user=self.user).count(),n)

class LicenseBlockTests(ReleaseRuleFixture):
    def test_block_revokes_devices_and_unblock_restores_active_state(self):
        order = self.make_order(suffix='block')
        _activate_order(order, self.now)
        license_obj = License.objects.get(owner_user=self.user)
        device, _raw = register_device(self.user, license_obj, 'Browser')

        block_license(license_obj, self.user)
        license_obj.refresh_from_db()
        device.refresh_from_db()
        self.assertEqual(license_obj.status, 'blocked')
        self.assertIsNotNone(device.revoked_at)
        self.assertTrue(AuditEvent.objects.filter(action='license.blocked', object_id=str(license_obj.id)).exists())

        unblock_license(license_obj, self.user)
        license_obj.refresh_from_db()
        self.assertEqual(license_obj.status, 'active')
        self.assertTrue(AuditEvent.objects.filter(action='license.unblocked', object_id=str(license_obj.id)).exists())

    def test_payment_review_cannot_be_overridden_by_manual_block(self):
        order = self.make_order(suffix='payment-review')
        _activate_order(order, self.now)
        license_obj = License.objects.get(owner_user=self.user)
        license_obj.status = 'payment_review'
        license_obj.save(update_fields=['status', 'updated_at'])
        with self.assertRaises(ValidationError):
            block_license(license_obj, self.user)


class DeviceLimitTests(ReleaseRuleFixture):
    def test_third_device_is_blocked(self):
        order=self.make_order(suffix='device'); _activate_order(order,self.now); lic=License.objects.get(owner_user=self.user); register_device(self.user,lic,'Gerät 1'); register_device(self.user,lic,'Gerät 2')
        with self.assertRaises(ValidationError): register_device(self.user,lic,'Gerät 3')

class InvitationRulesTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('admin@example.test','ReleaseRulePassword-123!',first_name='Ada',last_name='Admin'); self.company=Company.objects.create(customer_number='PM-C-TEST-001',name='Test GmbH',email='firma@example.test',country='DE'); Membership.objects.create(company=self.company,user=self.admin,role='admin',active=True)
    def test_invitation_is_valid_for_24_hours(self):
        before=timezone.now(); inv,raw=create_invitation(company=self.company,actor=self.admin,email='neu@example.test'); after=timezone.now(); self.assertTrue(raw); self.assertGreaterEqual(inv.expires_at,before+timedelta(hours=24)); self.assertLessEqual(inv.expires_at,after+timedelta(hours=24,seconds=1)); self.assertTrue(inv.is_valid())
    def test_new_invitation_revokes_previous(self):
        first,_=create_invitation(company=self.company,actor=self.admin,email='neu@example.test'); second,_=create_invitation(company=self.company,actor=self.admin,email='neu@example.test'); first.refresh_from_db(); self.assertIsNotNone(first.revoked_at); self.assertIsNone(second.revoked_at); self.assertEqual(Invitation.objects.filter(company=self.company,email='neu@example.test',accepted_at__isnull=True,revoked_at__isnull=True).count(),1)


class ReminderContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-REMINDER',
            name='PromptMaster Pro Reminder Test',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-REMINDER',
            name='Reminder GmbH',
            email='reminder@example.test',
            country='DE',
        )
        self.admin = User.objects.create_user(
            'reminder-admin@example.test',
            'Reminder-Admin-Password-42!',
            first_name='Reminder',
            last_name='Admin',
        )
        self.member = User.objects.create_user(
            'reminder-member@example.test',
            'Reminder-Member-Password-42!',
            first_name='Reminder',
            last_name='Member',
        )
        Membership.objects.create(company=self.company, user=self.admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member, role='member', active=True)
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

    def test_partial_failure_reuses_same_message_rows_without_duplicate_recipient_mail(self):
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


class TenantIsolationTests(TestCase):
    def test_company_license_cannot_be_assigned_cross_tenant(self):
        now=timezone.now(); product=Product.objects.create(code='PRO',name='PromptMaster Pro',default_license_days=365,default_device_limit=2,reminder_1_days=60,reminder_2_days=30,critical_warning_days=7); a=Company.objects.create(customer_number='PM-C-A',name='A GmbH',email='a@example.test'); b=Company.objects.create(customer_number='PM-C-B',name='B GmbH',email='b@example.test'); admin=User.objects.create_user('a-admin@example.test','ReleaseRulePassword-123!',first_name='A',last_name='Admin'); other=User.objects.create_user('b-user@example.test','ReleaseRulePassword-123!',first_name='B',last_name='User'); Membership.objects.create(company=a,user=admin,role='admin',active=True); Membership.objects.create(company=b,user=other,role='admin',active=True); price=ProductPrice.objects.create(product=product,price_type='new',gross_amount=Decimal('35.88'),currency='EUR',valid_from=now-timedelta(days=1)); order=Order.objects.create(order_number='PM-O-TENANT',company=a,status='draft',currency='EUR',gross_total=Decimal('35.88'),tax_total=Decimal('5.73'),billing_snapshot={},idempotency_key='tenant-test-key'); OrderItem.objects.create(order=order,product=product,price_version=price,quantity=1,unit_gross=Decimal('35.88'),unit_net=Decimal('30.15'),tax_rate=Decimal('19.00'),product_name_snapshot=product.name); _activate_order(order,now); lic=License.objects.get(company=a)
        with self.assertRaises(ValidationError): assign_license(lic,other,admin)

class UpgradeAndDeepLinkTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PRO-UPGRADE', name='PromptMaster Pro Upgrade Test', default_license_days=365,
            default_device_limit=2, reminder_1_days=60, reminder_2_days=30, critical_warning_days=7,
        )
        self.price = ProductPrice.objects.create(
            product=self.product, price_type='new', gross_amount=Decimal('35.88'), currency='EUR',
            valid_from=self.now - timedelta(days=1),
        )
        self.company = Company.objects.create(customer_number='PM-C-UPGRADE', name='Upgrade GmbH', email='upgrade@example.test')
        self.admin = User.objects.create_user('upgrade-admin@example.test','ReleaseRulePassword-123!',first_name='Ada',last_name='Admin')
        self.member = User.objects.create_user('upgrade-member@example.test','ReleaseRulePassword-123!',first_name='Mara',last_name='Member')
        self.other = User.objects.create_user('upgrade-other@example.test','ReleaseRulePassword-123!',first_name='Otto',last_name='Other')
        Membership.objects.create(company=self.company, user=self.admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member, role='member', active=True)
        Membership.objects.create(company=self.company, user=self.other, role='member', active=True)
        order = Order.objects.create(
            order_number='PM-O-UPGRADE', company=self.company, status='draft', currency='EUR',
            gross_total=Decimal('35.88'), tax_total=Decimal('5.73'), billing_snapshot={}, idempotency_key='upgrade-seat'
        )
        OrderItem.objects.create(
            order=order, product=self.product, price_version=self.price, quantity=1,
            unit_gross=Decimal('35.88'), unit_net=Decimal('30.15'), tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
        )
        _activate_order(order, self.now)
        self.license = License.objects.get(company=self.company, product=self.product)

    def test_member_upgrade_request_can_be_approved_with_free_license(self):
        from apps.licenses.services import request_product_upgrade, resolve_product_upgrade
        request_row, created = request_product_upgrade(
            user=self.member, company=self.company, product=self.product, note='Bitte freischalten.'
        )
        self.assertTrue(created)
        resolved = resolve_product_upgrade(upgrade_request=request_row, actor=self.admin, approve=True)
        self.assertEqual(resolved.status, 'approved')
        self.assertTrue(
            LicenseAssignment.objects.filter(license=self.license, user=self.member, ended_at__isnull=True).exists()
        )

    def test_assignment_deep_link_is_target_bound_and_single_use(self):
        from apps.licenses.services import create_assignment_link, consume_assignment_link
        link, raw = create_assignment_link(
            company=self.company, target_user=self.member, license_obj=self.license, actor=self.admin
        )
        self.assertTrue(link.is_valid())
        with self.assertRaises(ValidationError):
            consume_assignment_link(raw_token=raw, user=self.other)
        assignment = consume_assignment_link(raw_token=raw, user=self.member)
        self.assertEqual(assignment.user, self.member)
        link.refresh_from_db()
        self.assertIsNotNone(link.used_at)
        with self.assertRaises(ValidationError):
            consume_assignment_link(raw_token=raw, user=self.member)
