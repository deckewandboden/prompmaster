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
