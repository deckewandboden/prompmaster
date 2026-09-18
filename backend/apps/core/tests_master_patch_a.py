from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.core.sensitive import SENSITIVE_REAUTH_SESSION_KEY
from apps.orders.models import Order
from apps.payments.models import Payment


class MasterPatchARbacTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'customer-reader@example.test',
            'Reader-Password-42!',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-reader-2fa',
        )
        self.role = Role.objects.create(code='customer-reader', name='Customer Reader')
        self.customers_read = Permission.objects.create(
            code='customers.read', name='Kunden lesen'
        )
        self.role.permissions.add(self.customers_read)
        UserRole.objects.create(user=self.staff, role=self.role)

        self.company = Company.objects.create(
            customer_number='PM-C-PATCH-A',
            name='Patch A GmbH',
            email='patch-a@example.test',
        )
        self.company_admin = User.objects.create_user(
            'company-admin-patch-a@example.test',
            'Customer-Password-42!',
        )
        Membership.objects.create(
            company=self.company,
            user=self.company_admin,
            role='admin',
            active=True,
        )
        self.private_user = User.objects.create_user(
            'private-patch-a@example.test',
            'Customer-Password-42!',
        )
        self.private_profile = PrivateCustomerProfile.objects.create(
            user=self.private_user,
            customer_number='PM-P-PATCH-A',
        )
        self.internal = User.objects.create_user(
            'internal-secret-patch-a@example.test',
            'Internal-Password-42!',
            is_staff=True,
        )
        self.order = Order.objects.create(
            order_number='PM-O-PATCH-A',
            company=self.company,
            status='paid',
            currency='EUR',
            gross_total=Decimal('19.90'),
            tax_total=Decimal('3.18'),
            billing_snapshot={},
            idempotency_key='patch-a-order',
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider='mollie',
            provider_payment_id='tr_patch_a_sensitive',
            status='failed',
            amount=Decimal('19.90'),
            currency='EUR',
        )

        self.client.force_login(self.staff)
        session = self.client.session
        session['security_version'] = self.staff.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()

    def grant(self, code):
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'name': code})
        self.role.permissions.add(permission)

    def test_customer_only_reader_does_not_see_or_compute_license_or_order_aggregates(self):
        company_detail = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        self.assertEqual(company_detail.status_code, 200)
        self.assertNotContains(company_detail, '<span>Lizenzen</span>', html=True)
        self.assertNotContains(company_detail, '<span>Bestellungen</span>', html=True)
        self.assertIsNone(company_detail.context['license_count'])
        self.assertIsNone(company_detail.context['order_count'])

        private_detail = self.client.get(
            f'/ns-admin/customers/private/{self.private_profile.id}/'
        )
        self.assertEqual(private_detail.status_code, 200)
        self.assertNotContains(private_detail, '<span>Lizenzen</span>', html=True)
        self.assertNotContains(private_detail, '<span>Bestellungen</span>', html=True)
        self.assertIsNone(private_detail.context['license_count'])
        self.assertIsNone(private_detail.context['order_count'])
        self.assertContains(private_detail, 'Aktive Geräte')

        preview = self.client.get(
            f'/ns-admin/customers/{self.company.id}/portal-preview/'
        )
        self.assertEqual(preview.status_code, 200)
        self.assertNotContains(preview, '<div>Lizenzen</div>', html=True)
        self.assertNotContains(preview, '<span>Bestellungen</span>', html=True)
        self.assertIsNone(preview.context['license_total'])
        self.assertIsNone(preview.context['order_count'])
        self.assertContains(preview, '<div>Geräte</div>', html=True)

    def test_domain_aggregates_appear_only_after_matching_permissions(self):
        self.grant('licenses.read')
        self.grant('orders.read')
        response = self.client.get(f'/ns-admin/customers/{self.company.id}/')
        self.assertContains(response, '<span>Lizenzen</span>', html=True)
        self.assertContains(response, '<span>Bestellungen</span>', html=True)
        self.assertIsNotNone(response.context['license_count'])
        self.assertEqual(response.context['order_count'], 1)

    def test_customer_search_does_not_query_expose_internal_staff_without_roles_read(self):
        response = self.client.get('/ns-admin/search/', {'q': 'patch-a'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.private_user.email)
        self.assertNotContains(response, self.internal.email)
        self.assertNotIn(self.internal, list(response.context['results']['users']))

        self.grant('roles.read')
        response = self.client.get('/ns-admin/search/', {'q': 'patch-a'})
        self.assertContains(response, self.internal.email)
        self.assertIn(self.internal, list(response.context['results']['users']))

    def test_order_reader_cannot_load_payment_details_without_payments_read(self):
        self.grant('orders.read')

        detail = self.client.get(f'/ns-admin/orders/{self.order.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context['can_payments'])
        self.assertNotContains(detail, self.payment.provider_payment_id)
        self.assertNotContains(detail, '<h2>Zahlungen</h2>', html=True)

        dashboard = self.client.get('/ns-admin/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertFalse(dashboard.context['rights']['payments'])
        self.assertIsNone(dashboard.context['failed_payment_count'])
        self.assertIsNone(dashboard.context['chargeback_count'])

        self.grant('payments.read')
        detail = self.client.get(f'/ns-admin/orders/{self.order.id}/')
        self.assertTrue(detail.context['can_payments'])
        self.assertContains(detail, self.payment.provider_payment_id)

        dashboard = self.client.get('/ns-admin/')
        self.assertTrue(dashboard.context['rights']['payments'])
        self.assertEqual(dashboard.context['failed_payment_count'], 1)
        self.assertEqual(dashboard.context['chargeback_count'], 0)


class MasterPatchASensitiveActionTests(TestCase):
    password = 'Sensitive-Operator-Password-42!'

    def setUp(self):
        self.operator = User.objects.create_superuser(
            'sensitive-operator@example.test',
            self.password,
            two_factor_required=True,
            totp_secret_enc='configured-sensitive-operator-secret',
        )
        self.target = User.objects.create_user(
            'sensitive-target@example.test',
            'Target-Password-42!',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-target-secret',
        )
        self.target.recovery_codes.create(code_hash=make_password('target-recovery'))
        self.client.force_login(self.operator)
        self._bind_session()

    def _bind_session(self, *, grant_at=None):
        self.operator.refresh_from_db()
        session = self.client.session
        session['security_version'] = self.operator.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        if grant_at is None:
            session.pop(SENSITIVE_REAUTH_SESSION_KEY, None)
        else:
            session[SENSITIVE_REAUTH_SESSION_KEY] = grant_at
        session.save()

    def test_sensitive_form_requires_step_up_then_allows_short_lived_grant(self):
        response = self.client.get('/ns-admin/api/service-accounts/new/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/ns-admin/security/reauth/', response['Location'])

        wrong = self.client.post(
            '/ns-admin/security/reauth/',
            {'password': 'wrong-password'},
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertNotIn(SENSITIVE_REAUTH_SESSION_KEY, self.client.session)

        allowed = self.client.post(
            '/ns-admin/security/reauth/',
            {'password': self.password},
        )
        self.assertEqual(allowed.status_code, 302)
        self.assertIn('/ns-admin/api/service-accounts/new/', allowed['Location'])
        self.assertIn(SENSITIVE_REAUTH_SESSION_KEY, self.client.session)

        page = self.client.get('/ns-admin/api/service-accounts/new/')
        self.assertEqual(page.status_code, 200)

    def test_expired_step_up_grant_is_rejected(self):
        expired = (timezone.now() - timedelta(seconds=301)).timestamp()
        self._bind_session(grant_at=expired)
        response = self.client.get('/ns-admin/roles/assign/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/ns-admin/security/reauth/', response['Location'])

    def test_high_risk_post_is_not_executed_before_step_up(self):
        url = f'/ns-admin/roles/users/{self.target.id}/reset-2fa/'
        response = self.client.post(
            url,
            HTTP_REFERER='http://testserver/ns-admin/roles/',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/ns-admin/security/reauth/', response['Location'])
        self.target.refresh_from_db()
        self.assertEqual(self.target.totp_secret_enc, 'configured-target-secret')
        self.assertTrue(self.target.recovery_codes.filter(used_at__isnull=True).exists())

        self.client.post('/ns-admin/security/reauth/', {'password': self.password})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.totp_secret_enc, '')
        self.assertFalse(self.target.recovery_codes.exists())