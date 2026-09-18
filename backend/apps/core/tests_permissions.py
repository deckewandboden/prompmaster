from django.test import TestCase
from apps.accounts.models import User, Role, Permission, UserRole
from apps.companies.models import Company, Membership, PrivateCustomerProfile


class AdminDataVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('restricted@example.test', 'Secure-Test-Password-42!', is_staff=True)
        self.role = Role.objects.create(code='restricted', name='Restricted')
        UserRole.objects.create(user=self.user, role=self.role)
        self.company = Company.objects.create(name='PRIVATE-CUSTOMER-42', customer_number='PRIVATE-42', email='private@example.test')
        self.private_user = User.objects.create_user('private-customer@example.test', 'Secure-Private-Password-42!')
        self.private_profile = PrivateCustomerProfile.objects.create(
            user=self.private_user,
            customer_number='PM-P-PERM-001',
            street='Testweg',
            house_number='1',
            postal_code='57072',
            city='Siegen',
            country='DE',
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

    def grant(self, code):
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code})
        self.role.permissions.add(permission)
        return permission

    def test_dashboard_without_business_permissions_contains_no_business_data(self):
        response = self.client.get('/ns-admin/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['customers'])
        self.assertIsNone(response.context['revenue30'])
        self.assertEqual(response.context['recent_orders'], [])
        self.assertNotContains(response, 'Umsatz 30 Tage')

    def test_search_respects_each_domain_permission(self):
        response = self.client.get('/ns-admin/search/', {'q': 'PRIVATE'})
        self.assertNotContains(response, self.company.name)
        for result in response.context['results'].values():
            self.assertEqual(list(result), [])
        permission = Permission.objects.create(code='customers.read', name='Customers')
        self.role.permissions.add(permission)
        response = self.client.get('/ns-admin/search/', {'q': 'PRIVATE'})
        self.assertContains(response, self.company.name)
        self.assertEqual(list(response.context['results']['payments']), [])

    def test_navigation_hides_unauthorized_admin_areas(self):
        response = self.client.get('/ns-admin/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/ns-admin/customers/"')
        self.assertNotContains(response, 'href="/ns-admin/licenses/"')
        self.assertNotContains(response, 'href="/ns-admin/ops/"')

        self.grant('customers.read')
        response = self.client.get('/ns-admin/')
        self.assertContains(response, 'href="/ns-admin/customers/"')
        self.assertNotContains(response, 'href="/ns-admin/licenses/"')

    def test_statistics_do_not_leak_unpermitted_domains(self):
        self.assertEqual(self.client.get('/ns-admin/statistics/').status_code, 403)

        self.grant('customers.read')
        response = self.client.get('/ns-admin/statistics/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kunden')
        self.assertNotContains(response, '<div>Lizenzen</div>', html=True)
        self.assertNotContains(response, 'Umsatz letzte 30 Tage')

    def test_customer_tabs_follow_domain_permissions(self):
        self.grant('customers.read')
        response = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Unternehmen<', html=False)
        self.assertNotContains(response, f'/ns-admin/customers/{self.company.id}/licenses/')
        self.assertNotContains(response, f'/ns-admin/customers/{self.company.id}/payments/')
        self.assertNotContains(response, f'/ns-admin/customers/{self.company.id}/audit/')

        self.grant('licenses.read')
        self.grant('payments.read')
        self.grant('audit.read')
        response = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        self.assertContains(response, f'/ns-admin/customers/{self.company.id}/licenses/')
        self.assertContains(response, f'/ns-admin/customers/{self.company.id}/payments/')
        self.assertContains(response, f'/ns-admin/customers/{self.company.id}/audit/')

    def test_customer_scoped_domain_routes_require_both_permissions(self):
        customers = self.grant('customers.read')
        routes = {
            'licenses.read': f'/ns-admin/customers/{self.company.id}/licenses/',
            'orders.read': f'/ns-admin/customers/{self.company.id}/orders/',
            'payments.read': f'/ns-admin/customers/{self.company.id}/payments/',
            'email.read': f'/ns-admin/customers/{self.company.id}/emails/',
            'legal.read': f'/ns-admin/customers/{self.company.id}/privacy/',
            'audit.read': f'/ns-admin/customers/{self.company.id}/audit/',
        }
        for code, url in routes.items():
            with self.subTest(code=code, phase='missing-domain'):
                self.assertEqual(self.client.get(url).status_code, 403)
            permission = self.grant(code)
            with self.subTest(code=code, phase='both'):
                self.assertEqual(self.client.get(url).status_code, 200)
            self.role.permissions.remove(permission)

        self.assertEqual(
            self.client.get(f'/ns-admin/customers/{self.company.id}/devices/').status_code,
            200,
        )

        self.role.permissions.remove(customers)
        self.grant('licenses.read')
        self.assertEqual(
            self.client.get(f'/ns-admin/customers/{self.company.id}/licenses/').status_code,
            403,
        )

    def test_private_customer_scoped_domain_routes_require_both_permissions(self):
        customers = self.grant('customers.read')
        routes = {
            'licenses.read': f'/ns-admin/customers/private/{self.private_profile.id}/licenses/',
            'orders.read': f'/ns-admin/customers/private/{self.private_profile.id}/orders/',
            'payments.read': f'/ns-admin/customers/private/{self.private_profile.id}/payments/',
            'email.read': f'/ns-admin/customers/private/{self.private_profile.id}/emails/',
            'audit.read': f'/ns-admin/customers/private/{self.private_profile.id}/audit/',
        }
        for code, url in routes.items():
            with self.subTest(code=code, phase='missing-domain'):
                self.assertEqual(self.client.get(url).status_code, 403)
            permission = self.grant(code)
            with self.subTest(code=code, phase='both'):
                self.assertEqual(self.client.get(url).status_code, 200)
            self.role.permissions.remove(permission)

        self.assertEqual(
            self.client.get(f'/ns-admin/customers/private/{self.private_profile.id}/devices/').status_code,
            200,
        )

        self.role.permissions.remove(customers)
        self.grant('payments.read')
        self.assertEqual(
            self.client.get(f'/ns-admin/customers/private/{self.private_profile.id}/payments/').status_code,
            403,
        )

    def test_company_update_requires_customers_write_and_is_audited(self):
        self.grant('customers.read')
        url = f'/ns-admin/customers/{self.company.id}/company/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Unternehmensdaten speichern')

        denied = self.client.post(url, {
            'name': 'Changed without write',
            'email': 'private@example.test',
            'street': '',
            'house_number': '',
            'postal_code': '',
            'city': '',
            'country': 'DE',
            'legal_form': '',
            'phone': '',
            'vat_id': '',
            'tax_number': '',
            'status': 'active',
        })
        self.assertEqual(denied.status_code, 403)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'PRIVATE-CUSTOMER-42')

        self.grant('customers.write')
        allowed = self.client.post(url, {
            'name': 'Changed with write',
            'email': 'private@example.test',
            'street': '',
            'house_number': '',
            'postal_code': '',
            'city': '',
            'country': 'DE',
            'legal_form': '',
            'phone': '',
            'vat_id': '',
            'tax_number': '',
            'status': 'active',
        })
        self.assertEqual(allowed.status_code, 302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'Changed with write')


class SupportAdminTransferReauthTests(TestCase):
    password = 'Staff-Reauth-Password-42!'

    def setUp(self):
        self.staff = User.objects.create_user(
            'security-admin@example.test',
            self.password,
            first_name='Security',
            last_name='Admin',
            is_staff=True,
            is_superuser=True,
            two_factor_required=True,
            totp_secret_enc='configured-sensitive-action-secret',
        )
        self.company = Company.objects.create(
            name='Transfer Security GmbH',
            customer_number='PM-C-REAUTH-001',
            email='transfer@example.test',
        )
        self.old_admin = User.objects.create_user(
            'transfer-old@example.test',
            'Customer-Password-42!',
            first_name='Old',
            last_name='Admin',
            two_factor_required=True,
            totp_secret_enc='configured-customer-secret',
        )
        self.target = User.objects.create_user(
            'transfer-new@example.test',
            'Customer-Password-42!',
            first_name='New',
            last_name='Admin',
        )
        Membership.objects.create(
            company=self.company,
            user=self.old_admin,
            role='admin',
            active=True,
        )
        Membership.objects.create(
            company=self.company,
            user=self.target,
            role='member',
            active=True,
        )
        self.url = (
            f'/ns-admin/customers/{self.company.id}/users/'
            f'{self.target.id}/transfer-admin/'
        )
        self.client.force_login(self.staff)
        self._set_security_session(two_factor_ok=True)

    def _set_security_session(self, *, two_factor_ok):
        self.staff.refresh_from_db()
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = two_factor_ok
        session.save()

    def _post(self, password):
        return self.client.post(
            self.url,
            {
                'password': password,
                'identity_verified': 'on',
                'note': 'Regression test',
            },
        )

    def _assert_unchanged(self):
        old_link = Membership.objects.get(company=self.company, user=self.old_admin)
        new_link = Membership.objects.get(company=self.company, user=self.target)
        self.assertEqual(old_link.role, 'admin')
        self.assertEqual(new_link.role, 'member')

    def test_support_transfer_rejects_missing_or_wrong_staff_password(self):
        self.assertEqual(self._post('').status_code, 403)
        self._assert_unchanged()
        self.assertEqual(self._post('wrong-password').status_code, 403)
        self._assert_unchanged()

    def test_support_transfer_requires_completed_two_factor_session(self):
        self._set_security_session(two_factor_ok=False)
        response = self._post(self.password)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/2fa/', response['Location'])
        self._assert_unchanged()

    def test_support_transfer_requires_two_factor_configuration(self):
        self.staff.two_factor_required = False
        self.staff.totp_secret_enc = ''
        self.staff.save(
            update_fields=['two_factor_required', 'totp_secret_enc', 'updated_at']
        )
        self._set_security_session(two_factor_ok=True)
        response = self._post(self.password)
        self.assertEqual(response.status_code, 403)
        self._assert_unchanged()

    def test_support_transfer_succeeds_after_password_and_two_factor_reauth(self):
        response = self._post(self.password)
        self.assertEqual(response.status_code, 302)
        old_link = Membership.objects.get(company=self.company, user=self.old_admin)
        new_link = Membership.objects.get(company=self.company, user=self.target)
        self.assertEqual(old_link.role, 'member')
        self.assertEqual(new_link.role, 'admin')
        self.assertEqual(
            Membership.objects.filter(
                company=self.company,
                role='admin',
                active=True,
            ).count(),
            1,
        )
