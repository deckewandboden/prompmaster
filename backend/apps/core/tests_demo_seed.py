import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User, UserRole
from apps.companies.models import Company, Invitation, Membership
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseUpgradeRequest
from apps.notifications.models import EmailMessage
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.support.models import SupportRequest


@override_settings(ENVIRONMENT='staging')
class DemoDataSeedTests(TestCase):
    def seed(self):
        output = io.StringIO()
        call_command('seed_demo_data', stdout=output)
        return output.getvalue()

    def test_seed_creates_three_customer_sizes_and_internal_roles(self):
        output = self.seed()

        expected = {
            'DEMO-1001': 3,
            'DEMO-1002': 8,
            'DEMO-1003': 15,
        }
        for customer_number, employee_count in expected.items():
            company = Company.objects.get(customer_number=customer_number)
            self.assertEqual(
                Membership.objects.filter(company=company, active=True).count(),
                employee_count,
            )
            self.assertEqual(
                Membership.objects.filter(company=company, active=True, role='admin').count(),
                1,
            )

        staff_roles = {
            'demo.support@promptmaster.invalid': 'support',
            'demo.ops@promptmaster.invalid': 'ops',
            'demo.prompts@promptmaster.invalid': 'prompt_manager',
        }
        for email, role_code in staff_roles.items():
            user = User.objects.get(email=email)
            self.assertTrue(user.is_staff)
            self.assertTrue(user.two_factor_required)
            self.assertEqual(
                list(UserRole.objects.filter(user=user).values_list('role__code', flat=True)),
                [role_code],
            )

        self.assertIn('TEMPORÄRE DEMO-ZUGÄNGE', output)
        self.assertIn('Der vorhandene echte Superadmin bleibt unverändert', output)

    def test_seed_populates_cross_function_states_and_is_idempotent(self):
        self.seed()
        first_counts = {
            'companies': Company.objects.filter(customer_number__startswith='DEMO-').count(),
            'memberships': Membership.objects.filter(company__customer_number__startswith='DEMO-').count(),
            'licenses': License.objects.filter(license_number__startswith='PM-DEMO-').count(),
            'orders': Order.objects.filter(order_number__startswith='DEMO-').count(),
            'payments': Payment.objects.filter(provider_payment_id__startswith='tr_demo_').count(),
            'devices': DeviceRegistration.objects.filter(license__license_number__startswith='PM-DEMO-').count(),
            'support': SupportRequest.objects.filter(subject__startswith='[DEMO]').count(),
            'mail': EmailMessage.objects.filter(subject__startswith='[DEMO]').count(),
        }

        self.assertEqual(first_counts['companies'], 3)
        self.assertEqual(first_counts['memberships'], 26)
        self.assertEqual(first_counts['licenses'], 23)
        self.assertEqual(first_counts['orders'], 5)
        self.assertEqual(first_counts['payments'], 5)
        self.assertGreaterEqual(first_counts['devices'], 6)
        self.assertEqual(first_counts['support'], 3)
        self.assertEqual(first_counts['mail'], 3)
        self.assertEqual(
            Invitation.objects.filter(company__customer_number='DEMO-1002', accepted_at__isnull=True).count(),
            1,
        )
        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company__customer_number__startswith='DEMO-',
                status='pending',
            ).count(),
            3,
        )
        self.assertTrue(
            License.objects.filter(
                company__customer_number='DEMO-1003',
                status='expired',
            ).exists()
        )
        self.assertTrue(
            Payment.objects.filter(provider_payment_id='tr_demo_0002_open', status='open').exists()
        )
        self.assertTrue(
            Payment.objects.filter(provider_payment_id='tr_demo_0003_failed', status='failed').exists()
        )

        self.seed()
        second_counts = {
            'companies': Company.objects.filter(customer_number__startswith='DEMO-').count(),
            'memberships': Membership.objects.filter(company__customer_number__startswith='DEMO-').count(),
            'licenses': License.objects.filter(license_number__startswith='PM-DEMO-').count(),
            'orders': Order.objects.filter(order_number__startswith='DEMO-').count(),
            'payments': Payment.objects.filter(provider_payment_id__startswith='tr_demo_').count(),
            'support': SupportRequest.objects.filter(subject__startswith='[DEMO]').count(),
            'mail': EmailMessage.objects.filter(subject__startswith='[DEMO]').count(),
        }
        self.assertEqual(first_counts['companies'], second_counts['companies'])
        self.assertEqual(first_counts['memberships'], second_counts['memberships'])
        self.assertEqual(first_counts['licenses'], second_counts['licenses'])
        self.assertEqual(first_counts['orders'], second_counts['orders'])
        self.assertEqual(first_counts['payments'], second_counts['payments'])
        self.assertEqual(first_counts['support'], second_counts['support'])
        self.assertEqual(first_counts['mail'], second_counts['mail'])


class DemoDataProductionGuardTests(TestCase):
    @override_settings(ENVIRONMENT='production')
    def test_seed_refuses_production(self):
        with self.assertRaisesMessage(CommandError, 'niemals'):
            call_command('seed_demo_data', stdout=io.StringIO())
