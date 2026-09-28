from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.companies.models import Company, Membership
from apps.notifications.models import EmailMessage, EmailTemplate

from .models import SupportMessage, SupportRequest


class NetstyleSupportBackendTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            customer_number='SUPPORT-TEST-001',
            name='Support Test GmbH',
            email='support-customer@example.test',
            status='active',
        )
        self.customer = User.objects.create_user(
            'support-customer@example.test',
            'Support-Customer-Password-2026!',
            first_name='Klara',
            last_name='Kunde',
        )
        Membership.objects.create(
            company=self.company,
            user=self.customer,
            role='admin',
            active=True,
        )
        self.support_request = SupportRequest.objects.create(
            user=self.customer,
            company=self.company,
            category='technical',
            subject='PromptMaster startet nicht',
            message='Beim Start erscheint eine Fehlermeldung.',
            status='new',
        )
        EmailTemplate.objects.create(
            code='support_reply',
            subject='Antwort auf Ihre PromptMaster-Anfrage: {subject}',
            body_text=(
                'Antwort: {reply}\n'
                'Status: {status}\n'
                'Bearbeiter: {responder}\n'
                'Vorgang: {support_id}'
            ),
            active=True,
        )
        self.superadmin = User.objects.create_user(
            'support-admin@example.test',
            'Support-Admin-Password-2026!',
            first_name='Netstyle',
            last_name='Support',
            is_staff=True,
            is_superuser=True,
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_customer_reply_is_persisted_audited_and_queued_for_email(self, delay):
        self._login(self.superadmin)

        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[self.support_request.pk]),
            {
                'visibility': 'customer',
                'body': 'Wir haben den Fehler geprüft und korrigiert.',
                'status_after_message': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('ns_admin:support_request_detail', args=[self.support_request.pk]),
        )

        reply = SupportMessage.objects.get(support_request=self.support_request)
        self.assertEqual(reply.sender_type, 'staff')
        self.assertEqual(reply.visibility, 'customer')
        self.assertEqual(reply.author_user, self.superadmin)
        self.assertEqual(
            reply.body,
            'Wir haben den Fehler geprüft und korrigiert.',
        )

        self.support_request.refresh_from_db()
        self.assertEqual(self.support_request.status, 'in_progress')

        email = EmailMessage.objects.get(recipient=self.customer.email)
        reply.refresh_from_db()
        self.assertEqual(reply.notification_email_id, email.id)
        self.assertEqual(email.status, 'queued')
        self.assertEqual(email.context['pm_scope_company_id'], str(self.company.id))
        self.assertEqual(email.context['pm_scope_user_id'], str(self.customer.id))

        self.assertTrue(
            AuditEvent.objects.filter(
                action='support.reply_created',
                object_type='SupportMessage',
                object_id=str(reply.id),
            ).exists()
        )

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_demo_customer_reply_never_queues_email(self, delay):
        demo = User.objects.create_user(
            'demo.support@promptmaster.invalid',
            'Demo-Support-Password-2026!',
            first_name='Demo',
            last_name='Kunde',
        )
        Membership.objects.create(
            company=self.company,
            user=demo,
            role='member',
            active=True,
        )
        request_obj = SupportRequest.objects.create(
            user=demo,
            company=self.company,
            category='other',
            subject='Demo Support',
            message='Nur eine Demo-Anfrage.',
        )

        self._login(self.superadmin)
        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[request_obj.pk]),
            {
                'visibility': 'customer',
                'body': 'Demo-Antwort ohne Mailversand.',
                'status_after_message': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        reply = SupportMessage.objects.get(support_request=request_obj)
        self.assertIsNone(reply.notification_email_id)
        self.assertFalse(
            EmailMessage.objects.filter(recipient=demo.email).exists()
        )
        delay.assert_not_called()

    @patch('apps.notifications.tasks.send_email_message.delay')
    def test_internal_note_stays_internal_and_does_not_change_new_status(self, delay):
        self._login(self.superadmin)

        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[self.support_request.pk]),
            {
                'visibility': 'internal',
                'body': 'Intern mit Technik abstimmen.',
                'status_after_message': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        note = SupportMessage.objects.get(support_request=self.support_request)
        self.assertEqual(note.visibility, 'internal')
        self.assertIsNone(note.notification_email_id)
        self.support_request.refresh_from_db()
        self.assertEqual(self.support_request.status, 'new')
        self.assertFalse(EmailMessage.objects.exists())
        delay.assert_not_called()
        self.assertTrue(
            AuditEvent.objects.filter(
                action='support.note_created',
                object_id=str(note.id),
            ).exists()
        )

    def test_support_read_without_write_cannot_post_reply(self):
        read_perm = Permission.objects.create(
            code='support.read',
            name='support.read',
        )
        role = Role.objects.create(
            code='support-reader-test',
            name='Support Reader Test',
        )
        role.permissions.add(read_perm)
        reader = User.objects.create_user(
            'support-reader@example.test',
            'Support-Reader-Password-2026!',
            first_name='Read',
            last_name='Only',
            is_staff=True,
        )
        UserRole.objects.create(user=reader, role=role)

        self._login(reader)

        detail = self.client.get(
            reverse('ns_admin:support_request_detail', args=[self.support_request.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'Antwort / interne Notiz')

        response = self.client.post(
            reverse('ns_admin:support_request_reply', args=[self.support_request.pk]),
            {
                'visibility': 'customer',
                'body': 'Darf nicht gespeichert werden.',
                'status_after_message': 'in_progress',
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SupportMessage.objects.exists())

    def test_detail_renders_original_request_and_complete_backend_history(self):
        SupportMessage.objects.create(
            support_request=self.support_request,
            author_user=self.superadmin,
            sender_type='staff',
            visibility='customer',
            body='Kundenantwort im Verlauf.',
        )
        SupportMessage.objects.create(
            support_request=self.support_request,
            author_user=self.customer,
            sender_type='customer',
            visibility='customer',
            body='Kundenrückfrage im Verlauf.',
        )
        SupportMessage.objects.create(
            support_request=self.support_request,
            author_user=self.superadmin,
            sender_type='staff',
            visibility='internal',
            body='Interne Notiz im Verlauf.',
        )

        self._login(self.superadmin)
        response = self.client.get(
            reverse('ns_admin:support_request_detail', args=[self.support_request.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beim Start erscheint eine Fehlermeldung.')
        self.assertContains(response, 'Kundenantwort im Verlauf.')
        self.assertContains(response, 'Kundenrückfrage im Verlauf.')
        self.assertContains(response, 'Kundenrückfrage')
        self.assertContains(response, 'Interne Notiz im Verlauf.')
        self.assertContains(response, 'Antwort / interne Notiz')
        self.assertContains(response, 'Nachrichtenverlauf')
        html = response.content.decode(response.charset or 'utf-8')
        self.assertLess(html.index('Nachrichtenverlauf'), html.index('Antwort / interne Notiz'))
        self.assertLess(html.index('Antwort / interne Notiz'), html.index('Anfragedaten'))
