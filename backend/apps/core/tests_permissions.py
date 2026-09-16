from django.test import TestCase
from apps.accounts.models import User, Role, Permission, UserRole
from apps.audit.models import AuditEvent
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.notifications.models import EmailMessage


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

        for domain_permission in company_routes:
            routes = (
                company_routes[domain_permission],
                private_routes[domain_permission],
            )
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

    def test_customer_summaries_do_not_leak_ungranted_domains(self):
        self._reset_permissions('customers.read')

        responses = (
            self.client.get(f'/ns-admin/customers/{self.company.id}/'),
            self.client.get(f'/ns-admin/customers/{self.company.id}/portal-preview/'),
            self.client.get(f'/ns-admin/customers/private/{self.private_profile.id}/'),
            self.client.get(f'/ns-admin/customers/private/{self.private_profile.id}/portal-preview/'),
        )
        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '>Lizenzen<', html=False)
            self.assertNotContains(response, '>Bestellungen<', html=False)
            self.assertNotContains(response, '>Aktive Lizenzen<', html=False)
            self.assertNotContains(response, '>Freie Lizenzen<', html=False)

        self._grant('licenses.read', 'orders.read')
        company_detail = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        private_detail = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/'
        )
        company_preview = self.client.get(
            f'/ns-admin/customers/{self.company.id}/portal-preview/'
        )
        private_preview = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/portal-preview/'
        )

        for response in (company_detail, private_detail):
            self.assertContains(response, 'Lizenzen')
            self.assertContains(response, 'Bestellungen')
        for response in (company_preview, private_preview):
            self.assertContains(response, 'Aktive Lizenzen')
            self.assertContains(response, 'Freie Lizenzen')
            self.assertContains(response, 'Bestellungen')

    def test_company_audit_excludes_identity_global_events(self):
        company_member = User.objects.create_user(
            'company-audit-member@example.test',
            'Secure-Test-Password-42!',
        )
        membership = Membership.objects.create(
            company=self.company,
            user=company_member,
            role='member',
            active=True,
        )
        AuditEvent.objects.create(
            actor=company_member,
            action='AUTH-GLOBAL-MARKER',
            object_type='User',
            object_id=str(company_member.id),
            changes={},
        )
        AuditEvent.objects.create(
            actor=self.user,
            action='MEMBERSHIP-TENANT-MARKER',
            object_type='Membership',
            object_id=str(membership.id),
            changes={},
        )

        self._reset_permissions('customers.read', 'audit.read')
        response = self.client.get(f'/ns-admin/customers/{self.company.id}/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MEMBERSHIP-TENANT-MARKER')
        self.assertNotContains(response, 'AUTH-GLOBAL-MARKER')

    def test_customer_email_history_uses_explicit_scope(self):
        other_company = Company.objects.create(
            name='OTHER-CUSTOMER-42',
            customer_number='OTHER-42',
            email='other@example.test',
        )
        shared_recipient = 'shared-recipient@example.test'
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='COMPANY-SCOPE-MARKER',
            context={'pm_scope_company_id': str(self.company.id)},
        )
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='OTHER-COMPANY-MARKER',
            context={'pm_scope_company_id': str(other_company.id)},
        )
        EmailMessage.objects.create(
            recipient=shared_recipient,
            subject='UNSCOPED-MARKER',
            context={},
        )
        EmailMessage.objects.create(
            recipient=self.private_user.email,
            subject='PRIVATE-SCOPE-MARKER',
            context={'pm_scope_user_id': str(self.private_user.id)},
        )
        EmailMessage.objects.create(
            recipient=self.private_user.email,
            subject='WRONG-PRIVATE-SCOPE-MARKER',
            context={'pm_scope_user_id': str(self.user.id)},
        )

        self._reset_permissions('customers.read', 'email.read')

        company_response = self.client.get(
            f'/ns-admin/customers/{self.company.id}/emails/'
        )
        self.assertEqual(company_response.status_code, 200)
        self.assertContains(company_response, 'COMPANY-SCOPE-MARKER')
        self.assertNotContains(company_response, 'OTHER-COMPANY-MARKER')
        self.assertNotContains(company_response, 'UNSCOPED-MARKER')

        private_response = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/emails/'
        )
        self.assertEqual(private_response.status_code, 200)
        self.assertContains(private_response, 'PRIVATE-SCOPE-MARKER')
        self.assertNotContains(private_response, 'WRONG-PRIVATE-SCOPE-MARKER')

