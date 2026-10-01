import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.companies.models import Company, Invitation, Membership
from apps.licenses.models import License, LicenseAssignment, LicenseUpgradeRequest
from apps.notifications.models import EmailMessage
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment


@override_settings(ENVIRONMENT='staging')
class NetstylePresentationDemoTests(TestCase):
    def setUp(self):
        call_command('seed_defaults', verbosity=0, stdout=io.StringIO())

    def seed(self):
        output = io.StringIO()
        call_command(
            'seed_netstyle_presentation_demo',
            confirm='NETSTYLE-PRESENTATION-DEMO',
            stdout=output,
        )
        return output.getvalue()

    def test_netstyle_presentation_contract(self):
        before_mail = EmailMessage.objects.count()
        output = self.seed()

        company = Company.objects.get(customer_number='DEMO-NETSTYLE')
        self.assertEqual(company.name, 'netstyle Informationstechnik GmbH')
        self.assertEqual(company.street, 'Am Bühl')
        self.assertEqual(company.house_number, '2')
        self.assertEqual(company.postal_code, '57223')
        self.assertEqual(company.city, 'Kreuztal')
        self.assertEqual(company.vat_id, 'DE815319970')
        self.assertEqual(company.tax_number, '342/5876/0379')

        memberships = Membership.objects.filter(company=company, active=True)
        self.assertEqual(memberships.count(), 12)
        self.assertEqual(memberships.filter(role='admin').count(), 1)

        rainer = User.objects.get(email='rspickermann@netstyle.de')
        self.assertEqual(rainer.first_name, 'Rainer')
        self.assertEqual(rainer.last_name, 'Spickermann')
        self.assertTrue(rainer.is_active)
        self.assertFalse(rainer.is_staff)
        self.assertTrue(rainer.two_factor_required)
        self.assertEqual(
            memberships.get(role='admin').user_id,
            rainer.id,
        )

        licenses = License.objects.filter(
            company=company,
            license_number__startswith='PM-DEMO-NS-',
        )
        self.assertEqual(licenses.count(), 10)
        self.assertEqual(licenses.filter(status='active').count(), 9)
        self.assertEqual(licenses.filter(status='free').count(), 1)
        self.assertEqual(
            LicenseAssignment.objects.filter(
                license__in=licenses,
                ended_at__isnull=True,
            ).count(),
            9,
        )
        assigned_users = set(
            LicenseAssignment.objects.filter(
                license__in=licenses,
                ended_at__isnull=True,
            ).values_list('user_id', flat=True)
        )
        self.assertEqual(memberships.exclude(user_id__in=assigned_users).count(), 3)

        orders = Order.objects.filter(
            company=company,
            order_number__startswith='DEMO-NS-O-',
        ).order_by('order_number')
        self.assertEqual(orders.count(), 3)
        self.assertEqual(
            list(
                OrderItem.objects.filter(order__in=orders)
                .order_by('order__order_number')
                .values_list('quantity', flat=True)
            ),
            [1, 7, 2],
        )
        self.assertEqual(
            Payment.objects.filter(
                order__in=orders,
                provider='demo',
                status='paid',
            ).count(),
            3,
        )

        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company=company,
                status='pending',
            ).count(),
            1,
        )
        self.assertFalse(
            Invitation.objects.filter(
                company=company,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertEqual(EmailMessage.objects.count(), before_mail)
        self.assertIn('E-Mail-Versand: keiner', output)
        self.assertIn('Payment-Provider: keiner', output)

    def test_seed_is_idempotent(self):
        self.seed()
        rainer = User.objects.get(email='rspickermann@netstyle.de')
        first_password_hash = rainer.password
        self.seed()
        rainer.refresh_from_db()
        self.assertEqual(rainer.password, first_password_hash)

        company = Company.objects.get(customer_number='DEMO-NETSTYLE')
        self.assertEqual(Membership.objects.filter(company=company, active=True).count(), 12)
        self.assertEqual(
            License.objects.filter(
                company=company,
                license_number__startswith='PM-DEMO-NS-',
            ).count(),
            10,
        )
        self.assertEqual(
            Order.objects.filter(
                company=company,
                order_number__startswith='DEMO-NS-O-',
            ).count(),
            3,
        )
        self.assertEqual(
            LicenseUpgradeRequest.objects.filter(
                company=company,
                status='pending',
            ).count(),
            1,
        )

    @override_settings(ENVIRONMENT='production')
    def test_production_requires_explicit_presentation_flag(self):
        with self.assertRaisesMessage(CommandError, '--allow-production-presentation'):
            call_command(
                'seed_netstyle_presentation_demo',
                confirm='NETSTYLE-PRESENTATION-DEMO',
                stdout=io.StringIO(),
            )

    @override_settings(ENVIRONMENT='production')
    def test_explicit_production_presentation_mode_never_sends_mail(self):
        before_mail = EmailMessage.objects.count()
        call_command(
            'seed_netstyle_presentation_demo',
            confirm='NETSTYLE-PRESENTATION-DEMO',
            allow_production_presentation=True,
            stdout=io.StringIO(),
        )
        self.assertEqual(EmailMessage.objects.count(), before_mail)
        self.assertEqual(
            Membership.objects.filter(
                company__customer_number='DEMO-NETSTYLE',
                active=True,
            ).count(),
            12,
        )
