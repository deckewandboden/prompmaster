from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company, Invitation, Membership
from apps.core.security import token_hash
from apps.devices.models import DeviceRegistration
from apps.licenses.models import (
    License,
    LicenseAssignment,
    LicenseAssignmentLink,
    LicenseUpgradeRequest,
)
from apps.support.models import SupportMessage, SupportRequest


class CustomerPortalTenantIsolationTests(TestCase):
    password = 'Portal-Tenant-Audit-2026!'

    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            code='PORTAL-AUDIT-PRO',
            name='Portal Audit Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.company_a = Company.objects.create(
            customer_number='PORTAL-A-001',
            name='Portal A GmbH',
            email='a@example.test',
        )
        self.company_b = Company.objects.create(
            customer_number='PORTAL-B-001',
            name='Portal B GmbH',
            email='b@example.test',
        )
        self.admin_a = self._user('admin-a@example.test', 'Admin', 'A')
        self.member_a = self._user('member-a@example.test', 'Member', 'A')
        self.admin_b = self._user('admin-b@example.test', 'Admin', 'B')
        self.member_b = self._user('member-b@example.test', 'Member', 'B')
        self.staff = self._user('support@example.test', 'Netstyle', 'Support', is_staff=True)

        Membership.objects.create(
            company=self.company_a, user=self.admin_a, role='admin', active=True
        )
        Membership.objects.create(
            company=self.company_a, user=self.member_a, role='member', active=True
        )
        Membership.objects.create(
            company=self.company_b, user=self.admin_b, role='admin', active=True
        )
        Membership.objects.create(
            company=self.company_b, user=self.member_b, role='member', active=True
        )

        self.license_a = License.objects.create(
            company=self.company_a,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        self.license_b = License.objects.create(
            company=self.company_b,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=364),
        )
        LicenseAssignment.objects.create(license=self.license_a, user=self.member_a)
        LicenseAssignment.objects.create(license=self.license_b, user=self.member_b)

        self.device_a = DeviceRegistration.objects.create(
            user=self.member_a,
            license=self.license_a,
            token_hash='a' * 64,
            display_name='A Notebook',
            last_seen_at=self.now,
        )
        self.device_b = DeviceRegistration.objects.create(
            user=self.member_b,
            license=self.license_b,
            token_hash='b' * 64,
            display_name='B Notebook',
            last_seen_at=self.now,
        )

        self.support_a_member = SupportRequest.objects.create(
            user=self.member_a,
            company=self.company_a,
            license=self.license_a,
            category='technical',
            subject='A member request',
            message='Original A member message',
        )
        self.support_a_admin = SupportRequest.objects.create(
            user=self.admin_a,
            company=self.company_a,
            category='other',
            subject='A admin request',
            message='Original A admin message',
        )
        self.support_b_member = SupportRequest.objects.create(
            user=self.member_b,
            company=self.company_b,
            license=self.license_b,
            category='technical',
            subject='B member request',
            message='Original B member message',
        )
        SupportMessage.objects.create(
            support_request=self.support_a_member,
            author_user=self.staff,
            sender_type='staff',
            visibility='customer',
            body='Visible staff reply for A',
        )
        SupportMessage.objects.create(
            support_request=self.support_a_member,
            author_user=self.staff,
            sender_type='staff',
            visibility='internal',
            body='INTERNAL STAFF NOTE MUST NEVER LEAK',
        )

        self.invitation_b = Invitation.objects.create(
            company=self.company_b,
            email='invite-b@example.test',
            first_name='Invite',
            last_name='B',
            token_hash='c' * 64,
            expires_at=self.now + timedelta(hours=24),
            invited_by=self.admin_b,
        )

        self.upgrade_b = LicenseUpgradeRequest.objects.create(
            user=self.member_b,
            company=self.company_b,
            product=self.product,
            status='pending',
            note='B requests Pro',
        )
        self.assignment_raw_b = 'portal-audit-assignment-token-b'
        self.assignment_link_b = LicenseAssignmentLink.objects.create(
            company=self.company_b,
            license=self.license_b,
            target_user=self.member_b,
            token_hash=token_hash(self.assignment_raw_b),
            expires_at=self.now + timedelta(hours=24),
            created_by=self.admin_b,
        )

    def _user(self, email, first, last, **extra):
        return User.objects.create_user(
            email,
            self.password,
            first_name=first,
            last_name=last,
            email_verified_at=self.now,
            **extra,
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['authenticated_at'] = self.now.timestamp()
        session['last_activity_at'] = self.now.timestamp()
        session.save()

    def test_company_admin_cannot_cross_tenant_boundaries_by_direct_url(self):
        self._login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('portal:license_detail', args=[self.license_b.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('portal:renew', args=[self.license_b.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('portal:team_member', args=[self.member_b.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse('portal:device_revoke', args=[self.device_b.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('portal:support_detail', args=[self.support_b_member.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('portal:invitation_revoke', args=[self.invitation_b.pk])
            ).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(
                reverse('portal:resolve_upgrade', args=[self.upgrade_b.pk, 'approve'])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('portal:member_assign', args=[self.member_a.pk]),
                {'license_id': str(self.license_b.pk)},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    'portal:member_release',
                    args=[self.member_b.pk, self.license_b.pk],
                )
            ).status_code,
            404,
        )

    def test_company_member_cannot_reach_company_admin_and_billing_actions(self):
        self._login(self.member_a)

        for url in (
            reverse('portal:team'),
            reverse('portal:company'),
            reverse('portal:orders'),
            reverse('portal:buy'),
            reverse('portal:renew_index'),
            reverse('portal:renew', args=[self.license_a.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

        self.assertEqual(
            self.client.post(
                reverse('portal:device_revoke', args=[self.device_a.pk])
            ).status_code,
            403,
        )

    def test_support_conversation_is_tenant_scoped_and_internal_notes_are_hidden(self):
        self._login(self.admin_a)
        admin_view = self.client.get(
            reverse('portal:support_detail', args=[self.support_a_member.pk])
        )
        self.assertEqual(admin_view.status_code, 200)
        self.assertContains(admin_view, 'Original A member message')
        self.assertContains(admin_view, 'Visible staff reply for A')
        self.assertNotContains(admin_view, 'INTERNAL STAFF NOTE MUST NEVER LEAK')

        self._login(self.member_a)
        member_view = self.client.get(
            reverse('portal:support_detail', args=[self.support_a_member.pk])
        )
        self.assertEqual(member_view.status_code, 200)
        self.assertContains(member_view, 'Visible staff reply for A')
        self.assertNotContains(member_view, 'INTERNAL STAFF NOTE MUST NEVER LEAK')
        self.assertEqual(
            self.client.get(
                reverse('portal:support_detail', args=[self.support_a_admin.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('portal:support_detail', args=[self.support_b_member.pk])
            ).status_code,
            404,
        )

    def test_assignment_capability_cannot_be_consumed_by_another_tenant_user(self):
        self._login(self.member_a)
        response = self.client.post(
            reverse('portal:claim_assignment_link', args=[self.assignment_raw_b])
        )
        self.assertEqual(response.status_code, 200)
        self.assignment_link_b.refresh_from_db()
        self.assertIsNone(self.assignment_link_b.used_at)
        self.assertFalse(
            LicenseAssignment.objects.filter(
                license=self.license_b,
                user=self.member_a,
                ended_at__isnull=True,
            ).exists()
        )

    @patch('apps.companies.portal.queue_email', side_effect=RuntimeError('mail unavailable'))
    def test_support_request_survives_notification_failure(self, _queue_email):
        self._login(self.member_a)

        response = self.client.post(
            reverse('portal:help'),
            {
                'category': 'technical',
                'license': str(self.license_a.pk),
                'subject': 'Persist despite mail failure',
                'message': 'The customer request must not be lost.',
            },
        )
        support = SupportRequest.objects.get(subject='Persist despite mail failure')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('portal:support_detail', args=[support.pk]),
        )
        self.assertEqual(support.user_id, self.member_a.pk)
        self.assertEqual(support.company_id, self.company_a.pk)
        self.assertEqual(support.license_id, self.license_a.pk)
