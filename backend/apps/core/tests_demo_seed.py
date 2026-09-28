import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User, UserRole
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseUpgradeRequest
from apps.notifications.models import EmailMessage
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.support.models import SupportMessage, SupportRequest


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
            'DEMO-1004': 25,
            'DEMO-1005': 40,
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

        expected_staff_roles = {
            'superadmin': 2,
            'support': 2,
            'ops': 2,
            'prompt_manager': 2,
        }
        for role_code, expected_count in expected_staff_roles.items():
            users = User.objects.filter(
                email__startswith=f'demo.{role_code.replace("_manager", "s")}',
                is_staff=True,
            )
            role_users = UserRole.objects.filter(
                role__code=role_code,
                user__email__endswith='@promptmaster.invalid',
                user__is_staff=True,
            ).select_related('user')
            self.assertEqual(role_users.count(), expected_count)
            for link in role_users:
                self.assertTrue(link.user.two_factor_required)
                self.assertTrue(link.user.is_active)

        self.assertEqual(
            PrivateCustomerProfile.objects.filter(customer_number__startswith='DEMO-P-').count(),
            3,
        )

        company_members = list(
            User.objects.filter(
                company_memberships__company__customer_number__startswith='DEMO-',
                company_memberships__active=True,
            ).distinct()
        )
        full_names = [(user.first_name, user.last_name) for user in company_members]
        self.assertEqual(len(full_names), len(set(full_names)))
        self.assertFalse(
            any(user.email.startswith('demo.kunde') for user in company_members)
        )
        self.assertEqual(
            len({user.email for user in company_members}),
            len(company_members),
        )

        paid_demo_orders = Order.objects.filter(
            order_number__startswith='DEMO-',
            status='paid',
        )
        revenue_months = {
            (order.created_at.year, order.created_at.month)
            for order in paid_demo_orders
        }
        self.assertGreaterEqual(len(revenue_months), 6)

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
            'support_messages': SupportMessage.objects.filter(support_request__subject__startswith='[DEMO]').count(),
            'mail': EmailMessage.objects.filter(subject__startswith='[DEMO]').count(),
        }

        self.assertEqual(first_counts['companies'], 5)
        self.assertEqual(first_counts['memberships'], 91)
        self.assertEqual(first_counts['licenses'], 76)
        self.assertEqual(first_counts['orders'], 24)
        self.assertEqual(first_counts['payments'], 24)
        self.assertGreaterEqual(first_counts['devices'], 13)
        self.assertEqual(first_counts['support'], 8)
        self.assertEqual(first_counts['support_messages'], 17)
        self.assertEqual(first_counts['mail'], 4)
        private_two = SupportRequest.objects.get(subject='[DEMO] DEMO-P-2002 – Privatanfrage')
        self.assertEqual(private_two.status, 'in_progress')
        self.assertIn('lande ich', private_two.message)
        self.assertEqual(private_two.messages.count(), 3)
        self.assertEqual(
            list(private_two.messages.values_list('sender_type', 'visibility')),
            [
                ('staff', 'customer'),
                ('customer', 'customer'),
                ('staff', 'internal'),
            ],
        )
        self.assertEqual(
            Invitation.objects.filter(company__customer_number='DEMO-1002', accepted_at__isnull=True).count(),
            1,
        )
        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company__customer_number__startswith='DEMO-',
                status='pending',
            ).count(),
            5,
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
        self.assertTrue(
            Payment.objects.filter(provider_payment_id='tr_demo_0004_chargeback', status='chargeback').exists()
        )
        self.assertTrue(
            License.objects.filter(
                owner_user__private_customer__customer_number='DEMO-P-2001',
                status='active',
            ).exists()
        )
        self.assertTrue(
            License.objects.filter(
                owner_user__private_customer__customer_number='DEMO-P-2003',
                status='expired',
            ).exists()
        )
        self.assertTrue(
            Payment.objects.filter(
                provider_payment_id='tr_demo_private_0003_failed',
                status='failed',
            ).exists()
        )

        self.seed()
        second_counts = {
            'companies': Company.objects.filter(customer_number__startswith='DEMO-').count(),
            'memberships': Membership.objects.filter(company__customer_number__startswith='DEMO-').count(),
            'licenses': License.objects.filter(license_number__startswith='PM-DEMO-').count(),
            'orders': Order.objects.filter(order_number__startswith='DEMO-').count(),
            'payments': Payment.objects.filter(provider_payment_id__startswith='tr_demo_').count(),
            'support': SupportRequest.objects.filter(subject__startswith='[DEMO]').count(),
            'support_messages': SupportMessage.objects.filter(support_request__subject__startswith='[DEMO]').count(),
            'mail': EmailMessage.objects.filter(subject__startswith='[DEMO]').count(),
        }
        self.assertEqual(first_counts['companies'], second_counts['companies'])
        self.assertEqual(first_counts['memberships'], second_counts['memberships'])
        self.assertEqual(first_counts['licenses'], second_counts['licenses'])
        self.assertEqual(first_counts['orders'], second_counts['orders'])
        self.assertEqual(first_counts['payments'], second_counts['payments'])
        self.assertEqual(first_counts['support'], second_counts['support'])
        self.assertEqual(first_counts['support_messages'], second_counts['support_messages'])
        self.assertEqual(first_counts['mail'], second_counts['mail'])


class DemoDataProductionGuardTests(TestCase):
    @override_settings(ENVIRONMENT='production')
    def test_seed_refuses_production(self):
        with self.assertRaisesMessage(CommandError, 'niemals'):
            call_command('seed_demo_data', stdout=io.StringIO())

    @override_settings(ENVIRONMENT='production')
    def test_explicit_presentation_mode_seeds_only_demo_customer_estate(self):
        call_command('seed_defaults', verbosity=0, stdout=io.StringIO())
        User.objects.create_superuser(
            email='real.staff@example.test',
            password='Production-Test-Admin-2026!',
            first_name='Real',
            last_name='Staff',
        )

        output = io.StringIO()
        call_command(
            'seed_demo_data',
            allow_production_presentation=True,
            stdout=output,
        )

        self.assertEqual(
            Company.objects.filter(customer_number__startswith='DEMO-').count(),
            5,
        )
        self.assertFalse(
            User.objects.filter(
                email__startswith='demo.superadmin',
                is_staff=True,
            ).exists()
        )
        self.assertIn(
            'keine Demo-Staffkonten und keine Rechtstexte verändert',
            output.getvalue(),
        )
