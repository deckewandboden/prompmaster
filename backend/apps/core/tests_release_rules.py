from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.companies.services import create_invitation
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment
from apps.licenses.services import assign_license, block_license, unblock_license
from apps.orders.models import Order, OrderItem
from apps.payments.services import _activate_order

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


class AdminTransferContractTests(TestCase):
    staff_password = 'Support-Transfer-Password-42!'

    def setUp(self):
        self.company = Company.objects.create(
            customer_number='PM-C-TRANSFER',
            name='Transfer GmbH',
            email='transfer@example.test',
            country='DE',
        )
        self.old_admin = User.objects.create_user(
            'transfer-old@example.test',
            'Customer-Transfer-Password-42!',
            first_name='Alte',
            last_name='Admin',
        )
        self.member = User.objects.create_user(
            'transfer-new@example.test',
            'Customer-Member-Password-42!',
            first_name='Neue',
            last_name='Admin',
        )
        Membership.objects.create(company=self.company, user=self.old_admin, role='admin', active=True)
        Membership.objects.create(company=self.company, user=self.member, role='member', active=True)
        self.staff = User.objects.create_user(
            'support-transfer@example.test',
            self.staff_password,
            first_name='Netstyle',
            last_name='Support',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured',
        )
        self.support_role = Role.objects.create(code='support-transfer-test', name='Support Transfer Test')
        read_perm = Permission.objects.create(code='customers.read', name='Customers read')
        write_perm = Permission.objects.create(code='customers.write', name='Customers write')
        self.support_role.permissions.set([read_perm, write_perm])
        UserRole.objects.create(user=self.staff, role=self.support_role)
        self.transfer_url = reverse(
            'ns_admin:customer_admin_transfer',
            args=[self.company.id, self.member.id],
        )
        self.users_url = reverse('ns_admin:customer_users', args=[self.company.id])
        self._login_staff(self.staff, two_factor_ok=True)

    def _login_staff(self, user, *, two_factor_ok):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        if two_factor_ok:
            session['two_factor_ok'] = True
        else:
            session.pop('two_factor_ok', None)
        session.save()

    def assert_original_admin_unchanged(self):
        self.assertEqual(Membership.objects.get(company=self.company, user=self.old_admin).role, 'admin')
        self.assertEqual(Membership.objects.get(company=self.company, user=self.member).role, 'member')

    def test_support_transfer_requires_confirmation_password_and_2fa(self):
        response = self.client.get(self.transfer_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.member.full_name)
        self.assertContains(response, 'Administratorübertragung verbindlich bestätigen')

        response = self.client.post(self.transfer_url, {'password': self.staff_password})
        self.assertEqual(response.status_code, 200)
        self.assert_original_admin_unchanged()

        response = self.client.post(
            self.transfer_url,
            {'password': 'Falsches-Passwort-42!', 'confirm': 'on'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwort falsch')
        self.assert_original_admin_unchanged()

        self._login_staff(self.staff, two_factor_ok=False)
        response = self.client.post(
            self.transfer_url,
            {'password': self.staff_password, 'confirm': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/2fa/', response['Location'])
        self.assert_original_admin_unchanged()

    def test_support_can_transfer_admin_with_single_admin_audit_and_session_invalidation(self):
        old_version = self.old_admin.security_version
        new_version = self.member.security_version
        response = self.client.post(
            self.transfer_url,
            {'password': self.staff_password, 'confirm': 'on'},
        )
        self.assertRedirects(response, self.users_url)
        old_membership = Membership.objects.get(company=self.company, user=self.old_admin)
        new_membership = Membership.objects.get(company=self.company, user=self.member)
        self.old_admin.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(old_membership.role, 'member')
        self.assertEqual(new_membership.role, 'admin')
        self.assertEqual(Membership.objects.filter(company=self.company, active=True, role='admin').count(), 1)
        self.assertEqual(self.old_admin.security_version, old_version + 1)
        self.assertEqual(self.member.security_version, new_version + 1)
        self.assertTrue(self.member.two_factor_required)
        event = AuditEvent.objects.get(action='company.admin_transferred', object_id=str(self.company.id))
        self.assertEqual(event.actor_id, self.staff.id)
        self.assertEqual(event.changes['old_admin'], str(self.old_admin.id))
        self.assertEqual(event.changes['new_admin'], str(self.member.id))

    def test_cross_tenant_target_is_rejected(self):
        other_company = Company.objects.create(
            customer_number='PM-C-TRANSFER-OTHER',
            name='Other GmbH',
            email='other@example.test',
            country='DE',
        )
        other_user = User.objects.create_user('other-member@example.test', 'Other-Member-Password-42!')
        Membership.objects.create(company=other_company, user=other_user, role='member', active=True)
        url = reverse('ns_admin:customer_admin_transfer', args=[self.company.id, other_user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assert_original_admin_unchanged()

    def test_read_only_staff_sees_no_transfer_action_and_cannot_open_route(self):
        read_only = User.objects.create_user(
            'read-only-transfer@example.test',
            'Read-Only-Transfer-Password-42!',
            is_staff=True,
        )
        role = Role.objects.create(code='customer-reader-test', name='Customer Reader Test')
        role.permissions.add(Permission.objects.get(code='customers.read'))
        UserRole.objects.create(user=read_only, role=role)
        self._login_staff(read_only, two_factor_ok=True)
        response = self.client.get(self.users_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.transfer_url)
        response = self.client.get(self.transfer_url)
        self.assertEqual(response.status_code, 403)
        self.assert_original_admin_unchanged()

    def test_company_admin_self_service_transfer_uses_same_confirmation_contract(self):
        self.client.force_login(self.old_admin)
        session = self.client.session
        session['security_version'] = self.old_admin.security_version
        session['two_factor_ok'] = True
        session.save()
        url = reverse('portal:transfer_admin', args=[self.member.id])
        response = self.client.post(url, {'password': 'Customer-Transfer-Password-42!'})
        self.assertEqual(response.status_code, 200)
        self.assert_original_admin_unchanged()
        response = self.client.post(
            url,
            {'password': 'Customer-Transfer-Password-42!', 'confirm': 'on'},
        )
        self.assertRedirects(response, reverse('accounts:login'))
        self.assertEqual(Membership.objects.get(company=self.company, user=self.old_admin).role, 'member')
        self.assertEqual(Membership.objects.get(company=self.company, user=self.member).role, 'admin')
        event = AuditEvent.objects.get(action='company.admin_transferred', object_id=str(self.company.id))
        self.assertEqual(event.actor_id, self.old_admin.id)


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
