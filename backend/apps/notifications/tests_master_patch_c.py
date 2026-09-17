from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company, Invitation, Membership
from apps.core.security import token_hash
from apps.licenses.models import License, LicenseAssignment, LicenseReminder

from .models import EmailMessage, EmailTemplate
from .services import message_scope_active, queue_email
from .tasks import (
    _recover_succeeded_refunds,
    schedule_license_reminders,
    send_email_message,
)


class NotificationSecurityTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.admin = User.objects.create_user(
            'notify-admin@example.test',
            'Notify-Password-42!',
            email_verified_at=self.now,
        )
        self.member = User.objects.create_user(
            'notify-member@example.test',
            'Notify-Password-42!',
            email_verified_at=self.now,
        )
        self.company = Company.objects.create(
            customer_number='PM-C-NOTIFY',
            name='Notify GmbH',
            email='notify-company@example.test',
            status='active',
        )
        self.admin_membership = Membership.objects.create(
            company=self.company,
            user=self.admin,
            role='admin',
            active=True,
        )
        self.member_membership = Membership.objects.create(
            company=self.company,
            user=self.member,
            role='member',
            active=True,
        )
        self.product = Product.objects.create(
            code='NOTIFY-PRO',
            name='Notify Pro',
            default_license_days=365,
            default_device_limit=2,
            reminder_1_days=60,
            reminder_2_days=30,
            critical_warning_days=7,
        )
        self.license = License.objects.create(
            company=self.company,
            product=self.product,
            status='active',
            valid_from=self.now - timedelta(days=335),
            valid_until=self.now + timedelta(days=30),
        )
        LicenseAssignment.objects.create(license=self.license, user=self.member)
        for code in ('invite', 't30'):
            EmailTemplate.objects.create(
                code=code,
                subject=f'{code} Nachricht',
                body_text='{url}' if code == 'invite' else 'Lizenz {license} endet am {expiry}.',
                active=True,
            )

    def test_revoked_invitation_is_suppressed_and_capability_url_is_encrypted_at_rest(self):
        raw = 'invite-notification-secret-token'
        invitation = Invitation.objects.create(
            company=self.company,
            email='invitee@example.test',
            token_hash=token_hash(raw),
            expires_at=self.now + timedelta(hours=24),
            invited_by=self.admin,
        )
        with self.captureOnCommitCallbacks(execute=False):
            message = queue_email(
                'invite',
                invitation.email,
                {'url': f'https://promptmaster.example/auth/invite/{raw}/'},
                scope_company=self.company.id,
            )
        message.refresh_from_db()
        stored_url = message.context['url']
        self.assertTrue(stored_url.startswith('pm_enc:v1:'))
        self.assertNotIn(raw, stored_url)
        self.assertTrue(message_scope_active(message))

        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=['revoked_at', 'updated_at'])
        self.assertFalse(message_scope_active(message))

    def test_removed_company_recipient_cannot_receive_prequeued_reminder(self):
        reminder = LicenseReminder.objects.create(
            license=self.license,
            kind='t30',
            target_valid_until=self.license.valid_until,
            status='queued',
        )
        with self.captureOnCommitCallbacks(execute=False):
            message = queue_email(
                't30',
                self.member.email,
                {
                    'license': self.license.license_number,
                    'expiry': timezone.localtime(self.license.valid_until).strftime('%d.%m.%Y'),
                    'reminder_id': str(reminder.id),
                },
                scope_company=self.company.id,
                scope_user=self.member.id,
            )
        self.assertTrue(message_scope_active(message))

        self.member_membership.active = False
        self.member_membership.save(update_fields=['active', 'updated_at'])
        self.assertFalse(message_scope_active(message))

    def test_recent_sending_claim_collapses_duplicate_worker_delivery(self):
        message = EmailMessage.objects.create(
            template=EmailTemplate.objects.get(code='t30'),
            recipient=self.admin.email,
            subject='Reminder',
            status='sending',
            context={
                'license': self.license.license_number,
                'expiry': '01.01.2099',
                'pm_scope_company_id': str(self.company.id),
                'pm_scope_user_id': str(self.admin.id),
            },
        )
        result = send_email_message.run(str(message.id))
        self.assertEqual(result, 'already-sending')
        message.refresh_from_db()
        self.assertEqual(message.status, 'sending')
        self.assertEqual(message.retry_count, 0)

    def test_reminder_scheduling_is_idempotent_and_binds_each_recipient_user(self):
        with self.captureOnCommitCallbacks(execute=False):
            first = schedule_license_reminders.run()
        self.assertEqual(first, 1)
        reminder = LicenseReminder.objects.get(
            license=self.license,
            kind='t30',
            target_valid_until=self.license.valid_until,
        )
        messages = EmailMessage.objects.filter(context__reminder_id=str(reminder.id)).order_by('recipient')
        self.assertEqual(messages.count(), 2)
        scope_by_recipient = {
            row.recipient: row.context.get('pm_scope_user_id')
            for row in messages
        }
        self.assertEqual(scope_by_recipient[self.admin.email], str(self.admin.id))
        self.assertEqual(scope_by_recipient[self.member.email], str(self.member.id))

        with self.captureOnCommitCallbacks(execute=False):
            second = schedule_license_reminders.run()
        self.assertEqual(second, 0)
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(reminder.id)).count(),
            2,
        )

    def test_refund_recovery_isolates_one_failure_and_attempts_later_rows(self):
        recovery_values = MagicMock()
        recovery_values.__getitem__.return_value = ['refund-bad', 'refund-good']
        recovery_queryset = MagicMock()
        recovery_queryset.values_list.return_value = recovery_values
        rows = {
            'refund-bad': SimpleNamespace(provider_refund_id='re_bad'),
            'refund-good': SimpleNamespace(provider_refund_id='re_good'),
        }

        def fake_filter(**kwargs):
            if kwargs.get('status') == 'succeeded':
                return recovery_queryset
            row_queryset = MagicMock()
            row_queryset.first.return_value = rows.get(kwargs.get('pk'))
            return row_queryset

        with patch('apps.payments.models.Refund.objects.filter', side_effect=fake_filter):
            with patch(
                'apps.payments.services.mark_refund_success',
                side_effect=[RuntimeError('broken refund row'), None],
            ) as finalize:
                failures = _recover_succeeded_refunds()

        self.assertEqual(finalize.call_count, 2)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], 'refund-bad')
