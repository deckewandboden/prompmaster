from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.companies.models import Company
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.notifications.services import _render_context
from apps.support.models import SupportMessage, SupportRequest


class SupportReplyAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='support.admin@example.test',
            password='Secret123!',
            first_name='Support',
            last_name='Admin',
            totp_secret_enc='configured-support-admin-secret',
        )
        self.customer = User.objects.create_user(
            email='customer@example.test',
            password='Secret123!',
            first_name='Mara',
            last_name='Lorenz',
        )
        self.company = Company.objects.create(
            customer_number='SUPPORT-TEST-001',
            name='Support Test GmbH',
            email='office@example.test',
            country='DE',
        )
        self.request_obj = SupportRequest.objects.create(
            user=self.customer,
            company=self.company,
            category='technical',
            subject='Testanfrage',
            message='Ursprüngliche Kundenfrage',
            status='new',
        )
        EmailTemplate.objects.update_or_create(
            code='support_reply',
            defaults={
                'subject': 'PromptMaster: {subject}',
                'body_text': (
                    'Antwort: {reply}\nStatus: {status}\nVorgang: {support_id}\nBearbeitet von: {responder}'
                ),
                'active': True,
            },
        )
        self.client.force_login(self.admin)
        session = self.client.session
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()

    def test_staff_reply_is_persisted_mailed_audited_and_visible(self):
        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[self.request_obj.id]),
            {'message': 'Bitte Cache leeren und erneut anmelden.'},
        )
        self.assertEqual(response.status_code, 302)

        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.status, 'in_progress')

        message = SupportMessage.objects.get(support_request=self.request_obj)
        self.assertEqual(message.sender_type, 'staff')
        self.assertEqual(message.visibility, 'customer')
        self.assertEqual(message.author_user, self.admin)
        self.assertEqual(message.body, 'Bitte Cache leeren und erneut anmelden.')
        self.assertIsNotNone(message.notification_email_id)

        email = EmailMessage.objects.get(pk=message.notification_email_id)
        self.assertEqual(email.template.code, 'support_reply')
        self.assertEqual(email.recipient, self.customer.email)
        self.assertEqual(email.status, 'queued')
        self.assertEqual(email.context['message'], message.body)
        self.assertEqual(email.context['reply'], message.body)

        self.assertTrue(
            AuditEvent.objects.filter(
                action='support.reply_sent',
                object_type='SupportRequest',
                object_id=str(self.request_obj.id),
            ).exists()
        )

        detail = self.client.get(
            reverse('ns_admin:support_request_detail', args=[self.request_obj.id])
        )
        self.assertContains(detail, 'Antwort schreiben')
        self.assertContains(detail, 'Verlauf')
        self.assertContains(detail, 'Ursprüngliche Kundenfrage')
        self.assertContains(detail, 'Bitte Cache leeren und erneut anmelden.')
        self.assertContains(detail, 'Warteschlange')

    def test_empty_reply_is_rejected(self):
        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[self.request_obj.id]),
            {'message': '   '},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SupportMessage.objects.filter(support_request=self.request_obj).exists()
        )
        self.assertFalse(
            EmailMessage.objects.filter(template__code='support_reply').exists()
        )

    def test_reply_requires_support_write_permission(self):
        with patch('apps.core.admin_views.has_perm', return_value=False):
            response = self.client.post(
                reverse('ns_admin:support_request_reply', args=[self.request_obj.id]),
                {'message': 'Diese Antwort darf nicht gespeichert werden.'},
            )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            SupportMessage.objects.filter(support_request=self.request_obj).exists()
        )

    def test_license_and_support_templates_keep_action_and_reply_layout_contract(self):
        from django.conf import settings
        from pathlib import Path

        templates = Path(settings.BASE_DIR) / 'templates' / 'ns_admin'
        license_detail = (templates / 'license_detail.html').read_text(encoding='utf-8')
        support_detail = (templates / 'support_detail.html').read_text(encoding='utf-8')

        self.assertIn('card-action-row end', license_detail)
        self.assertIn('Zuweisung freigeben', license_detail)
        self.assertIn("support_request_reply", support_detail)
        self.assertIn('Antwort schreiben', support_detail)
        self.assertIn('support-thread-entry', support_detail)
