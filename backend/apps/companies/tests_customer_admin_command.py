from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.companies.models import Company, Membership
from apps.notifications.models import EmailMessage


class CreateCustomerAdminCommandTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            customer_number='PRESENT-001',
            name='Presentation Customer GmbH',
            email='customer@example.test',
            status='active',
        )

    def test_creates_direct_customer_admin_without_email(self):
        out = StringIO()
        call_command(
            'create_customer_admin',
            company_name=self.company.name,
            email='customer.admin@example.test',
            first_name='Customer',
            last_name='Admin',
            password='Presentation-Admin-2026!',
            stdout=out,
        )

        membership = Membership.objects.select_related('user').get(
            company=self.company,
            active=True,
            role='admin',
        )
        user = membership.user
        self.assertEqual(user.email, 'customer.admin@example.test')
        self.assertEqual(user.first_name, 'Customer')
        self.assertEqual(user.last_name, 'Admin')
        self.assertTrue(user.check_password('Presentation-Admin-2026!'))
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.email_verified_at)
        self.assertTrue(user.two_factor_required)
        self.assertFalse(user.is_staff)
        self.assertEqual(EmailMessage.objects.count(), 0)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='customer_admin.direct_created',
                object_id=str(self.company.pk),
            ).exists()
        )
        self.assertIn('E-Mail-Versand: NEIN', out.getvalue())

    def test_refuses_to_replace_another_company_admin(self):
        call_command(
            'create_customer_admin',
            company_name=self.company.name,
            email='first.admin@example.test',
            first_name='First',
            last_name='Admin',
            password='First-Admin-Password-2026!',
        )

        with self.assertRaises(CommandError):
            call_command(
                'create_customer_admin',
                company_name=self.company.name,
                email='second.admin@example.test',
                first_name='Second',
                last_name='Admin',
                password='Second-Admin-Password-2026!',
            )

        self.assertEqual(
            Membership.objects.filter(
                company=self.company,
                active=True,
                role='admin',
            ).count(),
            1,
        )
        self.assertEqual(EmailMessage.objects.count(), 0)
