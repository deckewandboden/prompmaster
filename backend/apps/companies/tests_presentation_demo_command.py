from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company, Membership
from apps.licenses.models import License, LicenseAssignment, LicenseUpgradeRequest
from apps.notifications.models import EmailMessage
from apps.orders.models import Order


@override_settings(ENVIRONMENT='development')
class CompanyPresentationDemoCommandTests(TestCase):
    def setUp(self):
        call_command('seed_defaults', verbosity=0, stdout=StringIO())
        self.company = Company.objects.create(
            customer_number='PRESENT-001',
            name='Presentation Customer GmbH',
            email='customer@example.test',
            status='active',
        )
        self.admin = User.objects.create_user(
            email='customer.admin@example.test',
            password='Presentation-Admin-2026!',
            first_name='Customer',
            last_name='Admin',
            is_active=True,
            email_verified_at=timezone.now(),
            two_factor_required=True,
        )
        Membership.objects.create(
            company=self.company,
            user=self.admin,
            role='admin',
            active=True,
        )

    def test_creates_realistic_12_person_scenario_without_email(self):
        before = EmailMessage.objects.count()
        out = StringIO()
        call_command(
            'seed_company_presentation_demo',
            company_name=self.company.name,
            confirm_presentation_demo=True,
            stdout=out,
        )

        self.assertEqual(Membership.objects.filter(company=self.company).count(), 12)
        self.assertEqual(Membership.objects.filter(company=self.company, active=True).count(), 12)

        product = Product.objects.get(code='PRO')
        licenses = License.objects.filter(company=self.company, product=product)
        self.assertEqual(licenses.count(), 10)
        self.assertEqual(licenses.filter(status='free').count(), 1)

        assignments = LicenseAssignment.objects.filter(
            license__company=self.company,
            license__product=product,
            ended_at__isnull=True,
        )
        self.assertEqual(assignments.count(), 9)

        pro_user_ids = assignments.values_list('user_id', flat=True)
        self.assertEqual(
            Membership.objects.filter(company=self.company, active=True)
            .exclude(user_id__in=pro_user_ids)
            .count(),
            3,
        )
        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company=self.company,
                product=product,
                status='pending',
            ).count(),
            1,
        )
        self.assertEqual(Order.objects.filter(company=self.company).count(), 3)
        addon = Order.objects.get(order_number__endswith='ADDON')
        self.assertEqual(addon.items.get().quantity, 2)
        self.assertEqual(EmailMessage.objects.count(), before)
        self.assertIn('Benutzer gesamt: 12', out.getvalue())
        self.assertIn('Nachgebuchte PRO-Lizenzen: 2', out.getvalue())
        self.assertIn('E-Mail-Versand: NEIN', out.getvalue())

    def test_is_idempotent_and_does_not_duplicate_members_or_assets(self):
        for _ in range(2):
            call_command(
                'seed_company_presentation_demo',
                company_name=self.company.name,
                confirm_presentation_demo=True,
                stdout=StringIO(),
            )
        self.assertEqual(Membership.objects.filter(company=self.company).count(), 12)
        self.assertEqual(License.objects.filter(company=self.company).count(), 10)
        self.assertEqual(Order.objects.filter(company=self.company).count(), 3)

    def test_refuses_company_with_additional_real_member(self):
        user = User.objects.create_user(
            email='real.member@example.test',
            password='Real-Member-Password-2026!',
            first_name='Real',
            last_name='Member',
        )
        Membership.objects.create(company=self.company, user=user, role='member', active=True)
        with self.assertRaisesMessage(CommandError, 'weitere echte Benutzer'):
            call_command(
                'seed_company_presentation_demo',
                company_name=self.company.name,
                confirm_presentation_demo=True,
                stdout=StringIO(),
            )

    @override_settings(ENVIRONMENT='production')
    def test_production_requires_explicit_allow_flag(self):
        with self.assertRaisesMessage(CommandError, '--allow-production'):
            call_command(
                'seed_company_presentation_demo',
                company_name=self.company.name,
                confirm_presentation_demo=True,
                stdout=StringIO(),
            )
