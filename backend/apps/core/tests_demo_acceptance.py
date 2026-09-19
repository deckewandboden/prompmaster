from __future__ import annotations

import io
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.devices.models import DeviceRegistration
from apps.legal.models import DeletionRequest, LegalAcceptance
from apps.core.crypto import encrypt
from apps.licenses.models import License, LicenseAssignment, LicenseAssignmentLink, LicenseUpgradeRequest
from apps.accounts.totp import new_secret
from apps.payments.models import Payment
from apps.support.models import SupportRequest


@override_settings(ENVIRONMENT='staging')
class DemoEstateFunctionalAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        output = io.StringIO()
        call_command('seed_demo_data', stdout=output)
        cls.seed_output = output.getvalue()
        cls.credentials = {}
        for line in cls.seed_output.splitlines():
            if '@promptmaster.invalid' not in line or '|' not in line:
                continue
            parts = [part.strip() for part in line.split('|')]
            if len(parts) >= 4 and '@promptmaster.invalid' in parts[1]:
                cls.credentials[parts[1]] = parts[2]

    def _session_as(self, user):
        self.client.force_login(user)
        if user.two_factor_required and not user.totp_secret_enc:
            user.totp_secret_enc = encrypt(new_secret())
            user.save(update_fields=['totp_secret_enc', 'updated_at'])
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()

    def _staff(self, role_code, ordinal=1):
        link = (
            UserRole.objects.filter(
                role__code=role_code,
                user__email__endswith='@promptmaster.invalid',
                user__is_staff=True,
            )
            .select_related('user')
            .order_by('user__email')[ordinal - 1]
        )
        return link.user

    def test_all_seeded_login_credentials_authenticate(self):
        expected_login_identities = 8 + (5 * 3) + 3
        self.assertEqual(len(self.credentials), expected_login_identities)
        for email, password in self.credentials.items():
            user = User.objects.get(email=email)
            self.assertTrue(user.check_password(password), email)
            self.assertTrue(user.is_active, email)

    def test_two_netstyle_identities_per_canonical_role_enforce_rbac(self):
        matrix = {
            'superadmin': {
                'allow': [
                    '/ns-admin/', '/ns-admin/customers/', '/ns-admin/licenses/',
                    '/ns-admin/orders/', '/ns-admin/payments/', '/ns-admin/ops/',
                    '/ns-admin/support/', '/ns-admin/prompt-studio/',
                    '/ns-admin/roles/', '/ns-admin/settings/',
                ],
                'deny': [],
            },
            'support': {
                'allow': ['/ns-admin/', '/ns-admin/customers/', '/ns-admin/licenses/', '/ns-admin/orders/', '/ns-admin/payments/', '/ns-admin/support/'],
                'deny': ['/ns-admin/ops/', '/ns-admin/prompt-studio/', '/ns-admin/roles/', '/ns-admin/settings/'],
            },
            'ops': {
                'allow': ['/ns-admin/', '/ns-admin/ops/', '/ns-admin/api/', '/ns-admin/audit/'],
                'deny': ['/ns-admin/customers/', '/ns-admin/licenses/', '/ns-admin/orders/', '/ns-admin/payments/', '/ns-admin/support/', '/ns-admin/prompt-studio/', '/ns-admin/roles/'],
            },
            'prompt_manager': {
                'allow': ['/ns-admin/', '/ns-admin/prompt-studio/', '/ns-admin/prompt-studio/quality/', '/ns-admin/content/faqs/'],
                'deny': ['/ns-admin/customers/', '/ns-admin/licenses/', '/ns-admin/orders/', '/ns-admin/payments/', '/ns-admin/ops/', '/ns-admin/support/', '/ns-admin/roles/'],
            },
        }
        for role_code, checks in matrix.items():
            for ordinal in (1, 2):
                user = self._staff(role_code, ordinal)
                self._session_as(user)
                for path in checks['allow']:
                    with self.subTest(role=role_code, ordinal=ordinal, allow=path):
                        self.assertEqual(self.client.get(path).status_code, 200)
                for path in checks['deny']:
                    with self.subTest(role=role_code, ordinal=ordinal, deny=path):
                        self.assertEqual(self.client.get(path).status_code, 403)
                self.client.logout()

    def test_all_five_company_admins_can_use_complete_customer_portal(self):
        routes = (
            '/portal/dashboard/', '/portal/team/', '/portal/team/invitations/',
            '/portal/team/invite/', '/portal/licenses/', '/portal/licenses/buy/',
            '/portal/licenses/renew/', '/portal/devices/', '/portal/orders/',
            '/portal/company/', '/portal/profile/', '/portal/security/', '/portal/help/',
        )
        for number in range(1001, 1006):
            company = Company.objects.get(customer_number=f'DEMO-{number}')
            admin = Membership.objects.get(company=company, active=True, role='admin').user
            self._session_as(admin)
            for path in routes:
                with self.subTest(company=company.customer_number, route=path):
                    self.assertEqual(self.client.get(path).status_code, 200)
            self.client.logout()

    @patch('apps.companies.portal.queue_email')
    def test_company_admin_mutations_invite_assign_release_support_and_member_lifecycle(self, _mail):
        company = Company.objects.get(customer_number='DEMO-1001')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        member = (
            Membership.objects.filter(company=company, active=True, role='member')
            .select_related('user')
            .order_by('-user__email')
            .first()
            .user
        )
        free_license = License.objects.filter(company=company, status='free').order_by('license_number').first()
        self.assertIsNotNone(free_license)
        self._session_as(admin)

        response = self.client.post(
            '/portal/team/invite/',
            {'first_name': 'Neue', 'last_name': 'Demo', 'email': 'demo.neu1001@promptmaster.invalid'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Invitation.objects.filter(
                company=company,
                email='demo.neu1001@promptmaster.invalid',
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).exists()
        )

        response = self.client.post(
            f'/portal/team/{member.id}/assign/',
            {'license_id': str(free_license.id)},
        )
        self.assertEqual(response.status_code, 302)
        assignment = LicenseAssignment.objects.get(
            license=free_license,
            user=member,
            ended_at__isnull=True,
        )

        response = self.client.post(
            '/portal/help/',
            {
                'category': 'technical',
                'license': str(free_license.id),
                'subject': 'Demo Funktionsprüfung',
                'message': 'Automatischer End-to-End-Funktionstest des Kundenportals.',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            SupportRequest.objects.filter(
                company=company,
                user=admin,
                subject='Demo Funktionsprüfung',
            ).exists()
        )

        response = self.client.post(
            f'/portal/team/{member.id}/licenses/{free_license.id}/release/'
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        free_license.refresh_from_db()
        self.assertIsNotNone(assignment.ended_at)
        self.assertEqual(free_license.status, 'free')

        response = self.client.post(f'/portal/team/{member.id}/deactivate/')
        self.assertEqual(response.status_code, 302)
        membership = Membership.objects.get(company=company, user=member)
        member.refresh_from_db()
        self.assertFalse(membership.active)
        self.assertFalse(member.is_active)

        response = self.client.post(f'/portal/team/{member.id}/reactivate/')
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        member.refresh_from_db()
        self.assertTrue(membership.active)
        self.assertTrue(member.is_active)

    def test_company_tenant_isolation_uses_real_demo_companies(self):
        company_a = Company.objects.get(customer_number='DEMO-1001')
        company_b = Company.objects.get(customer_number='DEMO-1002')
        admin_a = Membership.objects.get(company=company_a, active=True, role='admin').user
        foreign_member = Membership.objects.filter(company=company_b, active=True, role='member').first().user
        self._session_as(admin_a)
        self.assertEqual(self.client.get(f'/portal/team/{foreign_member.id}/').status_code, 404)

    @patch('apps.companies.portal.queue_email')
    def test_three_private_customers_cover_active_expiring_and_expired_states(self, _mail):
        profiles = {
            profile.customer_number: profile
            for profile in PrivateCustomerProfile.objects.select_related('user').filter(
                customer_number__startswith='DEMO-P-'
            )
        }
        self.assertEqual(set(profiles), {'DEMO-P-2001', 'DEMO-P-2002', 'DEMO-P-2003'})
        expected_status = {
            'DEMO-P-2001': 'active',
            'DEMO-P-2002': 'active',
            'DEMO-P-2003': 'expired',
        }
        routes = (
            '/portal/dashboard/', '/portal/licenses/', '/portal/licenses/buy/',
            '/portal/licenses/renew/', '/portal/devices/', '/portal/orders/',
            '/portal/profile/', '/portal/security/', '/portal/help/',
        )
        for number, profile in profiles.items():
            self._session_as(profile.user)
            for path in routes:
                with self.subTest(private=number, route=path):
                    self.assertEqual(self.client.get(path).status_code, 200)
            license_obj = License.objects.get(owner_user=profile.user, product__code='PRO')
            self.assertEqual(license_obj.status, expected_status[number])
            response = self.client.post(
                '/portal/help/',
                {
                    'category': 'other',
                    'license': str(license_obj.id),
                    'subject': f'Privatfunktion {number}',
                    'message': 'Automatischer Privatkunden-Funktionstest.',
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(
                SupportRequest.objects.filter(
                    user=profile.user,
                    subject=f'Privatfunktion {number}',
                ).exists()
            )
            self.client.logout()


    @patch('apps.companies.portal.queue_email')
    def test_company_invitation_resend_and_revoke_with_demo_admin(self, _mail):
        company = Company.objects.get(customer_number='DEMO-1002')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        invitation = Invitation.objects.get(
            company=company,
            email='demo.einladung@promptmaster.invalid',
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        self._session_as(admin)

        response = self.client.post(f'/portal/team/invitations/{invitation.id}/resend/')
        self.assertEqual(response.status_code, 302)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)

        replacement = Invitation.objects.get(
            company=company,
            email=invitation.email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        self.assertNotEqual(replacement.id, invitation.id)

        response = self.client.post(f'/portal/team/invitations/{replacement.id}/revoke/')
        self.assertEqual(response.status_code, 302)
        replacement.refresh_from_db()
        self.assertIsNotNone(replacement.revoked_at)

    @patch('apps.companies.portal.queue_email')
    def test_assignment_link_is_created_and_consumed_by_exact_demo_member(self, _mail):
        company = Company.objects.get(customer_number='DEMO-1004')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        target = User.objects.get(email='demo.kunde4.user25@promptmaster.invalid')
        free_license = License.objects.filter(
            company=company,
            status='free',
        ).order_by('license_number').first()
        self.assertIsNotNone(free_license)
        self.assertFalse(
            LicenseAssignment.objects.filter(user=target, ended_at__isnull=True).exists()
        )

        self._session_as(admin)
        response = self.client.post(
            f'/portal/team/{target.id}/assignment-link/',
            {'license_id': str(free_license.id)},
        )
        self.assertEqual(response.status_code, 200)
        claim_url = response.context['claim_url']
        token = claim_url.rstrip('/').split('/')[-1]
        link = LicenseAssignmentLink.objects.get(
            company=company,
            license=free_license,
            target_user=target,
            used_at__isnull=True,
        )

        self.client.logout()
        self._session_as(target)
        response = self.client.post(f'/portal/licenses/claim/{token}/')
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        free_license.refresh_from_db()
        self.assertIsNotNone(link.used_at)
        self.assertEqual(free_license.status, 'active')
        self.assertTrue(
            LicenseAssignment.objects.filter(
                license=free_license,
                user=target,
                ended_at__isnull=True,
            ).exists()
        )

    @patch('apps.companies.portal.queue_email')
    def test_demo_upgrade_approval_assigns_free_seat(self, _mail):
        company = Company.objects.get(customer_number='DEMO-1005')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        upgrade = (
            LicenseUpgradeRequest.objects.filter(company=company, status='pending')
            .select_related('user')
            .first()
        )
        self.assertIsNotNone(upgrade)
        self.assertFalse(
            LicenseAssignment.objects.filter(user=upgrade.user, ended_at__isnull=True).exists()
        )
        self._session_as(admin)
        response = self.client.post(
            f'/portal/licenses/upgrade-requests/{upgrade.id}/approve/'
        )
        self.assertEqual(response.status_code, 302)
        upgrade.refresh_from_db()
        self.assertEqual(upgrade.status, 'approved')
        self.assertIsNotNone(upgrade.assigned_license_id)
        self.assertTrue(
            LicenseAssignment.objects.filter(
                license_id=upgrade.assigned_license_id,
                user=upgrade.user,
                ended_at__isnull=True,
            ).exists()
        )

    def test_demo_admin_can_revoke_company_device(self):
        company = Company.objects.get(customer_number='DEMO-1001')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        device = (
            DeviceRegistration.objects.filter(
                license__company=company,
                revoked_at__isnull=True,
            )
            .order_by('created_at')
            .first()
        )
        self.assertIsNotNone(device)
        self._session_as(admin)
        response = self.client.post(f'/portal/devices/{device.id}/revoke/')
        self.assertEqual(response.status_code, 302)
        device.refresh_from_db()
        self.assertIsNotNone(device.revoked_at)


    def test_demo_company_profile_update_and_admin_transfer(self):
        company = Company.objects.get(customer_number='DEMO-1001')
        admin_membership = Membership.objects.get(
            company=company,
            active=True,
            role='admin',
        )
        admin = admin_membership.user
        target_membership = (
            Membership.objects.filter(company=company, active=True, role='member')
            .select_related('user')
            .order_by('user__email')
            .first()
        )
        self._session_as(admin)

        response = self.client.post(
            '/portal/company/',
            {
                'name': company.name,
                'legal_form': company.legal_form,
                'email': company.email,
                'phone': '+49 271 5550199',
                'street': company.street,
                'house_number': company.house_number,
                'postal_code': company.postal_code,
                'city': company.city,
                'country': company.country,
                'vat_id': company.vat_id,
                'tax_number': company.tax_number,
            },
        )
        self.assertEqual(response.status_code, 302)
        company.refresh_from_db()
        self.assertEqual(company.phone, '+49 271 5550199')

        response = self.client.post(
            f'/portal/team/{target_membership.user_id}/transfer-admin/',
            {'password': self.credentials[admin.email]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/auth/login/')
        admin_membership.refresh_from_db()
        target_membership.refresh_from_db()
        target_membership.user.refresh_from_db()
        self.assertEqual(admin_membership.role, 'member')
        self.assertEqual(target_membership.role, 'admin')
        self.assertTrue(target_membership.user.two_factor_required)

    def test_private_profile_export_and_deletion_request_are_real(self):
        profile = PrivateCustomerProfile.objects.select_related('user').get(
            customer_number='DEMO-P-2001'
        )
        user = profile.user
        self._session_as(user)

        response = self.client.post(
            '/portal/profile/',
            {
                'first_name': 'Petra',
                'last_name': 'Privat-Test',
                'address-street': 'Neuer Privatweg',
                'address-house_number': '11',
                'address-postal_code': '57072',
                'address-city': 'Siegen',
                'address-country': 'DE',
            },
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(user.last_name, 'Privat-Test')
        self.assertEqual(profile.street, 'Neuer Privatweg')

        response = self.client.get('/portal/privacy/export/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['user']['email'], user.email)
        self.assertEqual(payload['private_customer']['customer_number'], 'DEMO-P-2001')
        self.assertNotIn('password', payload['user'])
        self.assertNotIn('token_hash', str(payload).lower())
        self.assertNotIn('totp_secret', str(payload).lower())

        response = self.client.post(
            '/portal/privacy/deletion-request/',
            {'confirm': '1'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DeletionRequest.objects.filter(user=user, status='open').exists()
        )

    @patch('apps.companies.portal.MollieClient.create_payment')
    def test_demo_company_purchase_and_private_renewal_reach_secure_checkout(self, create_payment):
        create_payment.side_effect = [
            {
                'id': 'tr_demo_company_acceptance',
                'status': 'open',
                '_links': {
                    'checkout': {
                        'href': 'https://checkout.example.test/company'
                    }
                },
            },
            {
                'id': 'tr_demo_private_acceptance',
                'status': 'open',
                '_links': {
                    'checkout': {
                        'href': 'https://checkout.example.test/private'
                    }
                },
            },
        ]

        company = Company.objects.get(customer_number='DEMO-1001')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        self._session_as(admin)
        response = self.client.post(
            '/portal/licenses/buy/?quantity=2',
            {
                'quantity': '2',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.example.test/company')
        company_payment = Payment.objects.get(
            provider_payment_id='tr_demo_company_acceptance'
        )
        self.assertEqual(company_payment.order.company, company)
        self.assertEqual(company_payment.order.items.get().quantity, 2)
        self.assertEqual(
            LegalAcceptance.objects.filter(
                user=admin,
                order=company_payment.order,
            ).count(),
            2,
        )

        self.client.logout()
        private = PrivateCustomerProfile.objects.select_related('user').get(
            customer_number='DEMO-P-2001'
        )
        private_license = License.objects.get(
            owner_user=private.user,
            product__code='PRO',
        )
        self._session_as(private.user)
        response = self.client.post(
            f'/portal/licenses/{private_license.id}/renew/',
            {
                'accept_terms': 'on',
                'accept_privacy': 'on',
                'accept_withdrawal': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.example.test/private')
        private_payment = Payment.objects.get(
            provider_payment_id='tr_demo_private_acceptance'
        )
        self.assertEqual(private_payment.order.private_user, private.user)
        self.assertEqual(
            private_payment.order.items.get().target_license,
            private_license,
        )
        self.assertEqual(
            LegalAcceptance.objects.filter(
                user=private.user,
                order=private_payment.order,
            ).count(),
            3,
        )

    def test_demo_license_upgrade_requests_exist_for_every_company(self):
        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company__customer_number__startswith='DEMO-',
                status='pending',
            ).values('company_id').distinct().count(),
            5,
        )
