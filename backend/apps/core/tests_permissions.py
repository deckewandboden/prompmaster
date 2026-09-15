from django.test import TestCase
from apps.accounts.models import User, Role, Permission, UserRole
from apps.companies.models import Company


class AdminDataVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('restricted@example.test', 'Secure-Test-Password-42!', is_staff=True)
        self.role = Role.objects.create(code='restricted', name='Restricted')
        UserRole.objects.create(user=self.user, role=self.role)
        self.company = Company.objects.create(name='PRIVATE-CUSTOMER-42', customer_number='PRIVATE-42', email='private@example.test')
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

