from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.legal.models import LegalDocument
from .models import User
from .totp import code, verify, new_secret
from .views import _default_post_login_url, _role_safe_next


class TotpTests(SimpleTestCase):
    def test_totp_at_known_time(self):
        s = new_secret()
        t = 1_000_000_000
        c = code(s, at=t)
        self.assertEqual(len(c), 6)
        self.assertTrue(verify(s, c, window=0, at=t))
        self.assertFalse(verify(s, '999999' if c != '999999' else '888888', window=0, at=t))


class DefaultPostLoginUrlTests(TestCase):
    def user(self, email, **extra):
        return User.objects.create_user(
            email=email,
            password='Login-Test-Password!',
            first_name='Test',
            last_name='User',
            **extra,
        )

    def test_staff_lands_in_netstyle_admin(self):
        user = self.user('staff@example.test', is_staff=True)
        self.assertEqual(_default_post_login_url(user), reverse('ns_admin:dashboard'))

    def test_active_company_customer_lands_in_portal(self):
        user = self.user('company@example.test')
        company = Company.objects.create(
            customer_number='C-LOGIN-ACTIVE',
            name='Login Active GmbH',
            email='company@example.test',
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        self.assertEqual(_default_post_login_url(user), reverse('portal:dashboard'))

    def test_private_customer_lands_in_portal(self):
        user = self.user('private@example.test')
        PrivateCustomerProfile.objects.create(user=user, customer_number='P-LOGIN-PRIVATE')
        self.assertEqual(_default_post_login_url(user), reverse('portal:dashboard'))

    @patch('apps.proaccess.services.active_product_assignment', return_value=object())
    def test_licensed_company_member_lands_directly_in_pro(self, _assignment):
        user = self.user('member-pro@example.test')
        company = Company.objects.create(
            customer_number='C-LOGIN-MEMBER-PRO',
            name='Login Member Pro GmbH',
            email='member-pro@example.test',
        )
        Membership.objects.create(company=company, user=user, role='member', active=True)
        self.assertEqual(_default_post_login_url(user), reverse('proaccess:launch'))

    @patch('apps.proaccess.services.active_product_assignment', return_value=object())
    def test_licensed_private_customer_lands_directly_in_pro(self, _assignment):
        user = self.user('private-pro@example.test')
        PrivateCustomerProfile.objects.create(
            user=user,
            customer_number='P-LOGIN-PRIVATE-PRO',
        )
        self.assertEqual(_default_post_login_url(user), reverse('proaccess:launch'))

    def test_identity_without_active_application_context_falls_back_home(self):
        user = self.user('inactive@example.test')
        company = Company.objects.create(
            customer_number='C-LOGIN-INACTIVE',
            name='Login Inactive GmbH',
            email='inactive@example.test',
            status='inactive',
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        self.assertEqual(_default_post_login_url(user), reverse('home'))


class FirstTimeMfaRoutingTests(TestCase):
    def _login_to_setup(self, user, password):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': user.email, 'password': password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:two_factor'))
        response = self.client.get(reverse('accounts:two_factor'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:two_factor_setup'))
        response = self.client.get(reverse('accounts:two_factor_setup'))
        self.assertEqual(response.status_code, 200)
        from apps.core.crypto import decrypt
        return decrypt(self.client.session['pending_totp_enc'])

    def test_first_time_staff_mfa_continues_to_netstyle_admin(self):
        password = 'Valid-Test-Passphrase-2026!'
        user = User.objects.create_user(
            email='first-staff@example.test',
            password=password,
            first_name='First',
            last_name='Staff',
            is_staff=True,
            is_superuser=True,
            two_factor_required=True,
        )
        secret = self._login_to_setup(user, password)
        response = self.client.post(
            reverse('accounts:two_factor_setup'),
            {'code': code(secret)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zum netstyle Admin-Backend')
        self.assertContains(response, reverse('ns_admin:dashboard'))

    def test_first_time_company_mfa_continues_to_customer_portal(self):
        password = 'Valid-Test-Passphrase-2026!'
        user = User.objects.create_user(
            email='first-company@example.test',
            password=password,
            first_name='First',
            last_name='Customer',
            two_factor_required=True,
        )
        company = Company.objects.create(
            customer_number='C-FIRST-MFA',
            name='First MFA GmbH',
            email=user.email,
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        secret = self._login_to_setup(user, password)
        response = self.client.post(
            reverse('accounts:two_factor_setup'),
            {'code': code(secret)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zum Kundenportal')
        self.assertContains(response, reverse('portal:dashboard'))


class RoleSafeLoginRoutingTests(TestCase):
    def test_staff_cannot_be_redirected_into_customer_portal(self):
        user = User.objects.create_user(
            'routing-staff@example.test',
            'Routing-Password-2026!',
            first_name='Route',
            last_name='Staff',
            is_staff=True,
        )
        self.assertEqual(_role_safe_next(user, '/portal/dashboard/'), '')
        self.assertEqual(_role_safe_next(user, '/ns-admin/'), '/ns-admin/')
        self.assertEqual(_role_safe_next(user, '/pro/'), '/pro/')

    def test_customer_cannot_be_redirected_into_netstyle_admin(self):
        user = User.objects.create_user(
            'routing-customer@example.test',
            'Routing-Password-2026!',
            first_name='Route',
            last_name='Customer',
        )
        company = Company.objects.create(
            customer_number='C-ROUTING',
            name='Routing GmbH',
            email=user.email,
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        self.assertEqual(_role_safe_next(user, '/ns-admin/'), '')
        self.assertEqual(_role_safe_next(user, '/portal/dashboard/'), '/portal/dashboard/')
        self.assertEqual(_role_safe_next(user, '/pro/'), '/pro/')


class SecurityDomainSeparationTests(TestCase):
    def test_staff_identity_cannot_open_customer_portal(self):
        user = User.objects.create_user(
            'domain-staff@example.test',
            'Domain-Separation-Password-2026!',
            first_name='Domain',
            last_name='Staff',
            is_staff=True,
        )
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()
        response = self.client.get(reverse('portal:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_customer_identity_cannot_open_netstyle_admin(self):
        user = User.objects.create_user(
            'domain-customer@example.test',
            'Domain-Separation-Password-2026!',
            first_name='Domain',
            last_name='Customer',
        )
        company = Company.objects.create(
            customer_number='C-DOMAIN-SEPARATION',
            name='Domain Separation GmbH',
            email=user.email,
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()
        response = self.client.get(reverse('ns_admin:dashboard'))
        self.assertEqual(response.status_code, 403)


class UnifiedLoginAndRegistrationFlowTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        now = timezone.now()
        for doc_type in ('terms', 'privacy'):
            LegalDocument.objects.create(
                doc_type=doc_type,
                version='login-flow-v1',
                content=f'Login flow {doc_type}',
                valid_from=now,
                active=True,
            )

    def test_login_page_offers_registration_and_password_reset(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Noch kein Konto? Konto erstellen')
        self.assertContains(response, reverse('accounts:password_reset'))

    @patch('apps.accounts.views.queue_email')
    def test_company_registration_preserves_checkout_target_through_mfa_setup(self, queue_email_mock):
        target = '/portal/licenses/buy/?quantity=3'
        response = self.client.post(
            reverse('accounts:register'),
            {
                'next': target,
                'customer_type': 'company',
                'first_name': 'Neue',
                'last_name': 'Admin',
                'email': 'new-admin-flow@example.test',
                'password': 'New-Admin-Flow-Password-2026!',
                'company_name': 'Neue Flow GmbH',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:two_factor_setup'))
        self.assertEqual(self.client.session.get('post_2fa_next'), target)

    @patch('apps.accounts.views.queue_email')
    def test_private_registration_preserves_checkout_target_without_mfa(self, queue_email_mock):
        target = '/portal/licenses/buy/?quantity=2'
        response = self.client.post(
            reverse('accounts:register'),
            {
                'next': target,
                'customer_type': 'private',
                'first_name': 'Private',
                'last_name': 'Buyer',
                'email': 'private-flow@example.test',
                'password': 'Private-Flow-Password-2026!',
                'company_name': '',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)


class LogoutWorkspaceRoutingTests(TestCase):
    def _session_login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_staff_logout_cancel_returns_to_netstyle_admin(self):
        user = User.objects.create_user(
            'logout-staff@example.test',
            'Logout-Staff-Password-2026!',
            first_name='Logout',
            last_name='Staff',
            is_staff=True,
        )
        self._session_login(user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/ns-admin/"')

    def test_customer_logout_cancel_returns_to_customer_portal(self):
        user = User.objects.create_user(
            'logout-customer@example.test',
            'Logout-Customer-Password-2026!',
            first_name='Logout',
            last_name='Customer',
        )
        company = Company.objects.create(
            customer_number='C-LOGOUT-CUSTOMER',
            name='Logout Customer GmbH',
            email=user.email,
        )
        Membership.objects.create(company=company, user=user, role='admin', active=True)
        self._session_login(user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/portal/dashboard/"')
