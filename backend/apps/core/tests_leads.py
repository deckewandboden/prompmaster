from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.companies.models import Company, Invitation
from apps.core.models import Lead


class LeadManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'lead-admin@example.test',
            None,
            first_name='Lead',
            last_name='Admin',
            is_staff=True,
            is_superuser=True,
            email_verified_at=timezone.now(),
            two_factor_required=False,
        )
        self.client.force_login(self.admin)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session.save()

        self.sales = User.objects.create_user(
            'sales@example.test',
            None,
            first_name='Sales',
            last_name='Owner',
            is_staff=True,
            email_verified_at=timezone.now(),
            two_factor_required=False,
        )
        self.lead = Lead.objects.create(
            kind='company',
            company_name='Lead Test GmbH',
            first_name='Ada',
            last_name='Lovelace',
            email='ada.lead@example.test',
            phone='+49 271 12345',
            source='website',
            priority='high',
            status='new',
            created_by=self.admin,
        )

    def test_create_edit_assign_and_soft_delete_are_audited(self):
        create = self.client.post(
            '/ns-admin/leads/new/',
            {
                'kind': 'company',
                'company_name': 'Neue Lead GmbH',
                'first_name': 'Max',
                'last_name': 'Muster',
                'email': 'max.lead@example.test',
                'phone': '',
                'source': 'manual',
                'status': 'new',
                'priority': 'normal',
                'assigned_to': str(self.sales.id),
                'next_action_at': '',
                'notes': 'Erstkontakt',
            },
        )
        self.assertEqual(create.status_code, 302)
        created = Lead.objects.get(email='max.lead@example.test')
        self.assertEqual(created.assigned_to, self.sales)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='lead.created',
                object_id=str(created.id),
            ).exists()
        )

        assign = self.client.post(
            f'/ns-admin/leads/{self.lead.id}/assign/',
            {'assigned_to': str(self.sales.id)},
        )
        self.assertEqual(assign.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.sales)
        self.assertTrue(
            AuditEvent.objects.filter(
                action='lead.assigned',
                object_id=str(self.lead.id),
            ).exists()
        )

        edit = self.client.post(
            f'/ns-admin/leads/{self.lead.id}/',
            {
                'kind': 'company',
                'company_name': 'Lead Test GmbH',
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'email': 'ada.lead@example.test',
                'phone': '+49 271 99999',
                'source': 'website',
                'status': 'qualified',
                'priority': 'high',
                'assigned_to': str(self.sales.id),
                'next_action_at': '',
                'notes': 'Qualifiziert',
            },
        )
        self.assertEqual(edit.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'qualified')
        self.assertEqual(self.lead.notes, 'Qualifiziert')
        self.assertTrue(
            AuditEvent.objects.filter(
                action='lead.updated',
                object_id=str(self.lead.id),
            ).exists()
        )

        deleted = self.client.post(
            f'/ns-admin/leads/{self.lead.id}/delete/',
            {'confirm': 'on'},
        )
        self.assertEqual(deleted.status_code, 302)
        self.lead.refresh_from_db()
        self.assertIsNotNone(self.lead.deleted_at)
        self.assertFalse(
            Lead.objects.filter(pk=self.lead.pk, deleted_at__isnull=True).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action='lead.deleted',
                object_id=str(self.lead.id),
            ).exists()
        )

    @patch('apps.notifications.services.queue_email')
    def test_company_lead_conversion_creates_customer_and_secure_invitation(self, queue_email):
        response = self.client.post(
            f'/ns-admin/leads/{self.lead.id}/convert-company/',
            {
                'company_name': 'Lead Test GmbH',
                'legal_form': 'GmbH',
                'email': 'ada.lead@example.test',
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'phone': '+49 271 12345',
                'street': 'Markt 1',
                'house_number': '',
                'postal_code': '57072',
                'city': 'Siegen',
                'country': 'DE',
                'vat_id': 'DE123456789',
                'tax_number': '123/456/789',
                'confirm': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)

        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'won')
        self.assertIsNotNone(self.lead.converted_at)
        company = self.lead.converted_company
        self.assertIsNotNone(company)
        self.assertEqual(company.customer_number, f'C-{self.lead.lead_number}')
        self.assertEqual(company.email, 'ada.lead@example.test')
        self.assertEqual(company.city, 'Siegen')

        invitation = Invitation.objects.get(company=company)
        self.assertEqual(invitation.email, 'ada.lead@example.test')
        self.assertIsNone(invitation.accepted_at)
        self.assertFalse(
            User.objects.filter(email='ada.lead@example.test').exists(),
            'Lead conversion must not create a customer identity before the customer accepts legal terms.',
        )
        queue_email.assert_called_once()
        self.assertEqual(queue_email.call_args.args[0], 'invite')
        self.assertEqual(queue_email.call_args.args[1], invitation.email)
        self.assertIn('/auth/invite/', queue_email.call_args.args[2]['url'])
        self.assertTrue(
            AuditEvent.objects.filter(
                action='lead.converted',
                object_id=str(self.lead.id),
            ).exists()
        )

    def test_private_lead_is_not_silently_converted_without_customer_legal_acceptance(self):
        self.lead.kind = 'private'
        self.lead.company_name = ''
        self.lead.save(update_fields=['kind', 'company_name', 'updated_at'])
        response = self.client.get(
            f'/ns-admin/leads/{self.lead.id}/convert-company/'
        )
        self.assertEqual(response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.converted_company_id)
        self.assertEqual(self.lead.status, 'new')

    def test_assignment_requires_explicit_assign_permission(self):
        read = Permission.objects.create(code='leads.read', name='Leads lesen')
        write = Permission.objects.create(code='leads.write', name='Leads bearbeiten')
        role = Role.objects.create(code='lead-editor', name='Lead Editor', active=True)
        role.permissions.set([read, write])
        editor = User.objects.create_user(
            'lead-editor@example.test',
            None,
            is_staff=True,
            email_verified_at=timezone.now(),
            two_factor_required=False,
        )
        UserRole.objects.create(user=editor, role=role)
        self.client.force_login(editor)
        session = self.client.session
        now = timezone.now().timestamp()
        session['security_version'] = editor.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = now
        session['last_activity_at'] = now
        session.save()

        response = self.client.post(
            f'/ns-admin/leads/{self.lead.id}/',
            {
                'kind': 'company',
                'company_name': self.lead.company_name,
                'first_name': self.lead.first_name,
                'last_name': self.lead.last_name,
                'email': self.lead.email,
                'phone': self.lead.phone,
                'source': self.lead.source,
                'status': self.lead.status,
                'priority': self.lead.priority,
                'assigned_to': str(self.sales.id),
                'next_action_at': '',
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 403)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.assigned_to_id)

    def test_lead_list_search_and_global_search_respect_soft_delete(self):
        response = self.client.get('/ns-admin/leads/?q=Lead%20Test')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.lead.lead_number)

        search = self.client.get('/ns-admin/search/?q=ada.lead')
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, self.lead.lead_number)

        self.lead.deleted_at = timezone.now()
        self.lead.save(update_fields=['deleted_at', 'updated_at'])

        hidden = self.client.get('/ns-admin/leads/?q=Lead%20Test')
        self.assertNotContains(hidden, self.lead.lead_number)
        search_hidden = self.client.get('/ns-admin/search/?q=ada.lead')
        self.assertNotContains(search_hidden, self.lead.lead_number)

    def test_sales_support_seed_permissions_cover_full_lead_lifecycle(self):
        from django.core.management import call_command

        call_command('seed_defaults', verbosity=0)
        support = Role.objects.get(code='support')
        codes = set(support.permissions.values_list('code', flat=True))
        self.assertTrue(
            {
                'leads.read',
                'leads.write',
                'leads.assign',
                'leads.convert',
                'leads.delete',
            }.issubset(codes)
        )
