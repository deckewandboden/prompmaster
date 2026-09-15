from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.catalog.services import create_price_version, current_price
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.companies.services import create_invitation, transfer_admin
from apps.devices.models import DeviceRegistration
from apps.devices.services import register_device
from apps.licenses.models import License, LicenseAssignment
from apps.licenses.services import assign_license, block_license, unblock_license
from apps.orders.models import Order, OrderItem
from apps.support.models import SupportRequest
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

class PriceVersioningTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            code='PRICE-VERSION-TEST',
            name='Price Version Test',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.start = timezone.now().replace(microsecond=0)

    def test_new_price_closes_previous_stream_and_time_lookup_is_stable(self):
        first = create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            valid_from=self.start,
        )
        second_start = self.start + timedelta(days=30)
        second = create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('39.90'),
            valid_from=second_start,
        )

        first.refresh_from_db()
        self.assertEqual(first.valid_until, second_start)
        self.assertEqual(
            current_price(self.product, 'new', self.start + timedelta(days=1)).pk,
            first.pk,
        )
        self.assertEqual(
            current_price(self.product, 'new', second_start + timedelta(seconds=1)).pk,
            second.pk,
        )

    def test_backdated_overlapping_price_version_is_rejected(self):
        create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('35.88'),
            valid_from=self.start,
        )
        create_price_version(
            product=self.product,
            price_type='new',
            gross_amount=Decimal('39.90'),
            valid_from=self.start + timedelta(days=30),
        )
        with self.assertRaises(ValidationError):
            create_price_version(
                product=self.product,
                price_type='new',
                gross_amount=Decimal('37.50'),
                valid_from=self.start + timedelta(days=15),
            )


class CompanyAdminTransferTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            customer_number='PM-C-ADMIN-XFER',
            name='Admin Transfer GmbH',
            email='company@example.test',
            country='DE',
        )
        self.old_admin = User.objects.create_user(
            'old-admin@example.test',
            'Transfer-Password-42!',
            first_name='Old',
            last_name='Admin',
            two_factor_required=True,
            totp_secret_enc='configured-for-middleware-test',
        )
        self.new_admin = User.objects.create_user(
            'new-admin@example.test',
            'Transfer-Password-42!',
            first_name='New',
            last_name='Admin',
            two_factor_required=False,
        )
        Membership.objects.create(
            company=self.company, user=self.old_admin, role='admin', active=True
        )
        Membership.objects.create(
            company=self.company, user=self.new_admin, role='member', active=True
        )

    def test_transfer_keeps_exactly_one_admin_and_invalidates_both_security_sessions(self):
        old_version = self.old_admin.security_version
        new_version = self.new_admin.security_version

        transfer_admin(self.company, self.old_admin, self.new_admin)

        old_link = Membership.objects.get(company=self.company, user=self.old_admin)
        new_link = Membership.objects.get(company=self.company, user=self.new_admin)
        self.old_admin.refresh_from_db()
        self.new_admin.refresh_from_db()

        self.assertEqual(old_link.role, 'member')
        self.assertEqual(new_link.role, 'admin')
        self.assertTrue(self.new_admin.two_factor_required)
        self.assertGreater(self.old_admin.security_version, old_version)
        self.assertGreater(self.new_admin.security_version, new_version)
        self.assertEqual(
            Membership.objects.filter(
                company=self.company, role='admin', active=True
            ).count(),
            1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    company=self.company,
                    user=User.objects.create_user(
                        'third-admin@example.test',
                        'Transfer-Password-42!',
                        first_name='Third',
                        last_name='Admin',
                    ),
                    role='admin',
                    active=True,
                )

    def test_transfer_view_requires_password_and_completed_second_factor(self):
        self.client.force_login(self.old_admin)
        session = self.client.session
        session['security_version'] = self.old_admin.security_version
        session['two_factor_ok'] = False
        session.save()

        url = f'/portal/team/{self.new_admin.id}/transfer-admin/'
        response = self.client.post(url, {'password': 'Transfer-Password-42!'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/auth/2fa/'))
        self.assertEqual(
            Membership.objects.get(company=self.company, user=self.old_admin).role,
            'admin',
        )

        session = self.client.session
        session['two_factor_ok'] = True
        session.save()
        response = self.client.post(url, {'password': 'Transfer-Password-42!'})
        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            Membership.objects.get(company=self.company, user=self.old_admin).role,
            'member',
        )
        self.assertEqual(
            Membership.objects.get(company=self.company, user=self.new_admin).role,
            'admin',
        )

class PortalLicenseDetailIsolationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PORTAL-DETAIL-PRO',
            name='Portal Detail Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-DETAIL-A',
            name='Detail A GmbH',
            email='detail-a@example.test',
        )
        self.other_company = Company.objects.create(
            customer_number='PM-C-DETAIL-B',
            name='Detail B GmbH',
            email='detail-b@example.test',
        )
        self.member = User.objects.create_user(
            'detail-member@example.test',
            'Detail-Password-42!',
            first_name='Detail',
            last_name='Member',
            email_verified_at=self.now,
        )
        Membership.objects.create(
            company=self.company,
            user=self.member,
            role='member',
            active=True,
        )
        self.assigned = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        LicenseAssignment.objects.create(license=self.assigned, user=self.member)
        self.unassigned_same_tenant = License.objects.create(
            company=self.company,
            product=self.product,
            status='free',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        self.foreign = License.objects.create(
            company=self.other_company,
            product=self.product,
            status='free',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        self.client.force_login(self.member)
        session = self.client.session
        session['security_version'] = self.member.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_member_can_open_only_own_assigned_license(self):
        response = self.client.get(f'/portal/licenses/{self.assigned.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assigned.license_number)

        self.assertEqual(
            self.client.get(
                f'/portal/licenses/{self.unassigned_same_tenant.id}/'
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f'/portal/licenses/{self.foreign.id}/').status_code,
            404,
        )

class SupportContextIsolationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='SUPPORT-CONTEXT-PRO',
            name='Support Context Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-SUPPORT-A',
            name='Support A GmbH',
            email='support-a@example.test',
        )
        self.other_company = Company.objects.create(
            customer_number='PM-C-SUPPORT-B',
            name='Support B GmbH',
            email='support-b@example.test',
        )
        self.member = User.objects.create_user(
            'support-member@example.test',
            'Support-Password-42!',
            first_name='Support',
            last_name='Member',
            email_verified_at=self.now,
        )
        Membership.objects.create(
            company=self.company,
            user=self.member,
            role='member',
            active=True,
        )
        self.assigned = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        LicenseAssignment.objects.create(license=self.assigned, user=self.member)
        self.unassigned = License.objects.create(
            company=self.company,
            product=self.product,
            status='free',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        self.foreign = License.objects.create(
            company=self.other_company,
            product=self.product,
            status='free',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        self.client.force_login(self.member)
        session = self.client.session
        session['security_version'] = self.member.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_support_license_choices_are_tenant_and_assignment_scoped(self):
        response = self.client.get('/portal/help/')
        self.assertEqual(response.status_code, 200)
        choices = list(response.context['form'].fields['license'].queryset)
        self.assertEqual([row.pk for row in choices], [self.assigned.pk])

    def test_foreign_or_unassigned_license_cannot_be_injected_into_support_request(self):
        for license_obj in (self.unassigned, self.foreign):
            response = self.client.post(
                '/portal/help/',
                {
                    'category': 'license',
                    'license': str(license_obj.pk),
                    'subject': 'Lizenzfrage',
                    'message': 'Bitte prüfen.',
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn('license', response.context['form'].errors)
        self.assertFalse(SupportRequest.objects.filter(user=self.member).exists())

    @patch('apps.companies.portal.queue_email')
    def test_visible_license_context_is_persisted_and_audited(self, _queue_email):
        response = self.client.post(
            '/portal/help/',
            {
                'category': 'license',
                'license': str(self.assigned.pk),
                'subject': 'Lizenzfrage',
                'message': 'Bitte prüfen.',
            },
        )
        self.assertEqual(response.status_code, 302)
        row = SupportRequest.objects.get(user=self.member)
        self.assertEqual(row.company, self.company)
        self.assertEqual(row.license, self.assigned)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='support.created',
                object_id=str(row.id),
            ).exists()
        )

class NetstyleDeviceRevokeTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.product = Product.objects.create(
            code='DEVICE-REVOKE-PRO',
            name='Device Revoke Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-DEV-A',
            name='Device A GmbH',
            email='device-a@example.test',
        )
        self.other_company = Company.objects.create(
            customer_number='PM-C-DEV-B',
            name='Device B GmbH',
            email='device-b@example.test',
        )
        self.member = User.objects.create_user(
            'device-member@example.test',
            'Device-Password-42!',
            first_name='Device',
            last_name='Member',
            email_verified_at=now,
        )
        self.other_member = User.objects.create_user(
            'device-other@example.test',
            'Device-Password-42!',
            first_name='Other',
            last_name='Member',
            email_verified_at=now,
        )
        Membership.objects.create(company=self.company, user=self.member, role='member')
        Membership.objects.create(company=self.other_company, user=self.other_member, role='member')
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=364),
        )
        self.foreign_license = License.objects.create(
            company=self.other_company,
            product=self.product,
            status='active',
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=364),
        )
        LicenseAssignment.objects.create(license=self.license, user=self.member)
        LicenseAssignment.objects.create(license=self.foreign_license, user=self.other_member)
        self.device = DeviceRegistration.objects.create(
            user=self.member,
            license=self.license,
            token_hash='a' * 64,
            display_name='Managed device',
            last_seen_at=now,
        )
        self.foreign_device = DeviceRegistration.objects.create(
            user=self.other_member,
            license=self.foreign_license,
            token_hash='b' * 64,
            display_name='Foreign device',
            last_seen_at=now,
        )

        self.staff = User.objects.create_user(
            'support-device@example.test',
            'Device-Password-42!',
            first_name='Support',
            last_name='Agent',
            is_staff=True,
            two_factor_required=True,
            email_verified_at=now,
        )
        role = Role.objects.create(code='device-support-test', name='Device Support')
        role.permissions.add(
            Permission.objects.create(code='customers.read.device-test', name='Customer read alias')
        )
        # Use the canonical permission codes expected by the view.
        customers_read, _ = Permission.objects.get_or_create(code='customers.read', defaults={'name': 'customers.read'})
        devices_write, _ = Permission.objects.get_or_create(code='devices.write', defaults={'name': 'devices.write'})
        role.permissions.set([customers_read, devices_write])
        UserRole.objects.create(user=self.staff, role=role)
        self.client.force_login(self.staff)
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_authorized_staff_can_revoke_tenant_device_but_not_cross_tenant(self):
        foreign_url = (
            f'/ns-admin/customers/{self.company.id}/devices/'
            f'{self.foreign_device.id}/revoke/'
        )
        self.assertEqual(self.client.post(foreign_url).status_code, 404)
        self.foreign_device.refresh_from_db()
        self.assertIsNone(self.foreign_device.revoked_at)

        url = (
            f'/ns-admin/customers/{self.company.id}/devices/'
            f'{self.device.id}/revoke/'
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.revoked_at)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='device.revoked',
                object_id=str(self.device.id),
            ).exists()
        )

