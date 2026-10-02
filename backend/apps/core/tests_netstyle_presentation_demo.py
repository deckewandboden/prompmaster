from unittest.mock import patch
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
        self.assertTrue(rainer.has_usable_password())
        self.assertNotIn('unverändert (bereits gesetzt)', output)
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
                provider='mollie',
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
        self.assertIn('Provider-Aufrufe: keine', output)

    def test_company_scoped_mail_is_persisted_as_suppressed(self):
        from apps.notifications.services import queue_email

        self.seed()
        company = Company.objects.get(customer_number='DEMO-NETSTYLE')
        rainer = User.objects.get(email='rspickermann@netstyle.de')

        with patch('apps.notifications.tasks.send_email_message.delay') as delay:
            message = queue_email(
                'support_confirmation',
                rainer.email,
                {'subject': 'Präsentationsprobe'},
                scope_company=company,
                scope_user=rainer,
            )

        self.assertEqual(message.status, 'suppressed')
        self.assertIn('presentation demo tenant', message.error.lower())
        self.assertEqual(
            str(message.context.get('pm_scope_company_id')),
            str(company.id),
        )
        self.assertEqual(
            str(message.context.get('pm_scope_user_id')),
            str(rainer.id),
        )
        delay.assert_not_called()

        # User-scoped account mail must also remain inside the presentation
        # tenant even when the caller does not explicitly pass the company.
        with patch('apps.notifications.tasks.send_email_message.delay') as user_delay:
            user_scoped = queue_email(
                'support_confirmation',
                rainer.email,
                {'subject': 'Benutzerbezogene Präsentationsprobe'},
                scope_user=rainer,
            )

        self.assertEqual(user_scoped.status, 'suppressed')
        user_delay.assert_not_called()

    def test_automatic_license_reminders_are_suppressed(self):
        from apps.notifications.services import reminder_recipient_scopes

        self.seed()
        license_obj = (
            License.objects.filter(
                company__customer_number='DEMO-NETSTYLE',
                assignments__ended_at__isnull=True,
            )
            .select_related('company')
            .first()
        )
        self.assertIsNotNone(license_obj)
        self.assertEqual(reminder_recipient_scopes(license_obj), {})

    def test_seed_is_idempotent(self):
        self.seed()
        rainer = User.objects.get(email='rspickermann@netstyle.de')
        first_password_hash = rainer.password
        rainer.totp_secret_enc = 'already-configured-presentation-mfa'
        rainer.last_totp_step = 42
        rainer.save(update_fields=['totp_secret_enc', 'last_totp_step', 'updated_at'])

        self.seed()
        rainer.refresh_from_db()
        self.assertEqual(rainer.password, first_password_hash)
        self.assertEqual(rainer.totp_secret_enc, 'already-configured-presentation-mfa')
        self.assertEqual(rainer.last_totp_step, 42)

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

    def test_existing_demo_admin_is_replaced_safely(self):
        company = Company.objects.create(
            customer_number='DEMO-NETSTYLE',
            name='Altbestand Demo',
            email='old.demo@promptmaster.invalid',
            country='DE',
        )
        old_admin = User.objects.create_user(
            email='old.demo.admin@promptmaster.invalid',
            password='OldDemoPassword123!',
            first_name='Alt',
            last_name='Admin',
        )
        Membership.objects.create(
            company=company,
            user=old_admin,
            role='admin',
            active=True,
        )

        self.seed()

        company.refresh_from_db()
        admins = Membership.objects.filter(company=company, active=True, role='admin')
        self.assertEqual(admins.count(), 1)
        self.assertEqual(admins.get().user.email, 'rspickermann@netstyle.de')
        self.assertFalse(
            Membership.objects.get(company=company, user=old_admin).active
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
