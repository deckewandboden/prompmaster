from django.test import TestCase
from apps.accounts.models import User, Role, Permission, UserRole
from apps.companies.models import Company, PrivateCustomerProfile


class AdminDataVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('restricted@example.test', 'Secure-Test-Password-42!', is_staff=True)
        self.role = Role.objects.create(code='restricted', name='Restricted')
        UserRole.objects.create(user=self.user, role=self.role)
        self.company = Company.objects.create(name='PRIVATE-CUSTOMER-42', customer_number='PRIVATE-42', email='private@example.test')
        self.private_user = User.objects.create_user(
            'private-scope@example.test',
            'Secure-Test-Password-42!',
        )
        self.private_profile = PrivateCustomerProfile.objects.create(
            user=self.private_user,
            customer_number='PRIVATE-PERMS-42',
        )
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

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

    def _grant(self, *codes):
        for code in codes:
            permission, _created = Permission.objects.get_or_create(
                code=code,
                defaults={'name': code},
            )
            self.role.permissions.add(permission)

    def _reset_permissions(self, *codes):
        self.role.permissions.clear()
        self._grant(*codes)

    def test_customer_domain_deep_links_require_customer_and_domain_permission(self):
        company_routes = {
            'licenses.read': f'/ns-admin/customers/{self.company.id}/licenses/',
            'orders.read': f'/ns-admin/customers/{self.company.id}/orders/',
            'payments.read': f'/ns-admin/customers/{self.company.id}/payments/',
            'email.read': f'/ns-admin/customers/{self.company.id}/emails/',
            'audit.read': f'/ns-admin/customers/{self.company.id}/audit/',
        }
        private_routes = {
            'licenses.read': f'/ns-admin/customers/private/{self.private_profile.id}/licenses/',
            'orders.read': f'/ns-admin/customers/private/{self.private_profile.id}/orders/',
            'payments.read': f'/ns-admin/customers/private/{self.private_profile.id}/payments/',
            'email.read': f'/ns-admin/customers/private/{self.private_profile.id}/emails/',
            'audit.read': f'/ns-admin/customers/private/{self.private_profile.id}/audit/',
        }

        for domain_permission, routes in (
            *[(permission, (company_routes[permission], private_routes[permission])) for permission in company_routes],
        ):
            with self.subTest(domain_permission=domain_permission, missing='customers.read'):
                self._reset_permissions(domain_permission)
                for path in routes:
                    self.assertEqual(self.client.get(path).status_code, 403)

            with self.subTest(domain_permission=domain_permission, missing=domain_permission):
                self._reset_permissions('customers.read')
                for path in routes:
                    self.assertEqual(self.client.get(path).status_code, 403)

            with self.subTest(domain_permission=domain_permission, allowed=True):
                self._reset_permissions('customers.read', domain_permission)
                for path in routes:
                    self.assertEqual(self.client.get(path).status_code, 200)

    def test_customer_subnavigation_hides_domains_without_domain_permission(self):
        self._reset_permissions('customers.read')

        company_response = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        self.assertEqual(company_response.status_code, 200)
        private_response = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/'
        )
        self.assertEqual(private_response.status_code, 200)

        company_paths = (
            f'/ns-admin/customers/{self.company.id}/licenses/',
            f'/ns-admin/customers/{self.company.id}/orders/',
            f'/ns-admin/customers/{self.company.id}/payments/',
            f'/ns-admin/customers/{self.company.id}/emails/',
            f'/ns-admin/customers/{self.company.id}/audit/',
        )
        private_paths = (
            f'/ns-admin/customers/private/{self.private_profile.id}/licenses/',
            f'/ns-admin/customers/private/{self.private_profile.id}/orders/',
            f'/ns-admin/customers/private/{self.private_profile.id}/payments/',
            f'/ns-admin/customers/private/{self.private_profile.id}/emails/',
            f'/ns-admin/customers/private/{self.private_profile.id}/audit/',
        )
        for path in company_paths:
            self.assertNotContains(company_response, path)
        for path in private_paths:
            self.assertNotContains(private_response, path)

        self._grant('licenses.read')
        company_response = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        private_response = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/'
        )
        self.assertContains(
            company_response,
            f'/ns-admin/customers/{self.company.id}/licenses/',
        )
        self.assertContains(
            private_response,
            f'/ns-admin/customers/private/{self.private_profile.id}/licenses/',
        )

