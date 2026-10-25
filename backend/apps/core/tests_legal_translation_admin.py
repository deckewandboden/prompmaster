"""Product admin legal-translation approval boundaries; no public release side effects."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.legal.models import LegalDocument, LegalDocumentTranslation


@override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=False)
class ProductLegalTranslationAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_legal_documents_2026', vat_id='DE123456789', stdout=StringIO())
        cls.document = LegalDocument.objects.get(doc_type='privacy', active=True)
        cls.reader = cls.make_staff('legal-reader@example.test', 'reader', ('legal.read',))
        cls.editor = cls.make_staff('legal-editor@example.test', 'editor', ('legal.read', 'legal.write'))
        cls.signer = cls.make_staff('legal-signer@example.test', 'signer', ('legal.read', 'legal.approve'))
        cls.customer = User.objects.create_user(
            email='no-staff@example.test', password='Password-2026-test',
            first_name='Customer', last_name='Only',
        )

    @classmethod
    def make_staff(cls, email, code, permissions):
        user = User.objects.create_user(
            email=email, password='Password-2026-test',
            first_name=code, last_name='Tester',
            is_staff=True, two_factor_required=False,
        )
        role = Role.objects.create(code='legal-'+code, name='Legal '+code)
        for permission in permissions:
            obj, _ = Permission.objects.get_or_create(code=permission, defaults={'name': permission})
            role.permissions.add(obj)
        UserRole.objects.create(user=user, role=role)
        return user

    def login_as(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()

    def new_draft(self, content='English legal text'):
        return LegalDocumentTranslation.objects.create(
            document=self.document, language='en', content=content,
        )

    def test_production_admin_is_staff_and_role_protected(self):
        url = '/ns-admin/legal/translations/'
        self.assertNotEqual(self.client.get(url).status_code, 200)
        self.login_as(self.customer)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login_as(self.reader)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url+'new/').status_code, 403)
        item = self.new_draft()
        self.assertEqual(
            self.client.post(f'/ns-admin/legal/translations/{item.pk}/submit/').status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f'/ns-admin/legal/translations/{item.pk}/approve/').status_code,
            403,
        )

    def test_draft_review_separate_approval_and_no_publication(self):
        self.login_as(self.editor)
        url = '/ns-admin/legal/translations/'
        create = self.client.post(
            url+'new/', {
                'document': str(self.document.pk), 'language': 'en',
                'content': 'Independently reviewed English legal policy.',
                'status': 'approved',  # ignored, cannot inject an approval status
            },
        )
        self.assertEqual(create.status_code, 302)
        item = LegalDocumentTranslation.objects.get(language='en', document=self.document)
        self.assertEqual(item.status, 'draft')
        self.assertIsNone(item.submitted_by)
        self.assertTrue(AuditEvent.objects.filter(
            action='legal.translation_draft_saved', object_id=str(item.pk),
        ).exists())
        self.assertEqual(
            self.client.post(url+f'{item.pk}/submit/').status_code, 302,
        )
        item.refresh_from_db()
        self.assertEqual(item.status, 'review')
        self.assertEqual(item.submitted_by_id, self.editor.pk)
        self.assertEqual(len(item.content_sha256), 64)
        self.assertEqual(len(item.source_sha256), 64)
        self.assertEqual(self.client.get(url+f'{item.pk}/edit/').status_code, 403)
        self.assertEqual(
            self.client.post(url+f'{item.pk}/approve/', {
                'approval_reference': 'LEGAL-CHECK-2026-01',
            }).status_code, 403,
        )
        self.login_as(self.signer)
        response = self.client.get(url+f'{item.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Independently reviewed English legal policy.')
        self.assertEqual(self.client.post(url+f'{item.pk}/approve/', {
            'approval_reference': 'LEGAL-CHECK-2026-01',
        }).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'approved')
        self.assertEqual(item.approved_by_id, self.signer.pk)
        self.assertEqual(item.approval_reference, 'LEGAL-CHECK-2026-01')
        self.assertTrue(item.is_publishable())
        self.assertTrue(AuditEvent.objects.filter(
            action='legal.translation_approve', object_id=str(item.pk),
        ).exists())
        # Feature remains OFF even for a correctly signed translation.
        response = self.client.get('/legal/privacy/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(response.context['legal_content_language'], 'de')
        self.assertNotContains(response, item.content)
        self.assertEqual(self.client.get(url+f'{item.pk}/edit/').status_code, 403)

    def test_submitter_cannot_sign_own_review_even_with_approve_role(self):
        self.login_as(self.editor)
        item = self.new_draft()
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/submit/')
        permission = Permission.objects.get(code='legal.approve')
        role = Role.objects.get(code='legal-editor')
        role.permissions.add(permission)
        response = self.client.post(f'/ns-admin/legal/translations/{item.pk}/approve/', {
            'approval_reference': 'ILLEGAL-SELF-APPROVAL',
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'review')
        self.assertIsNone(item.approved_at)
        self.assertFalse(AuditEvent.objects.filter(
            action='legal.translation_approve', object_id=str(item.pk),
        ).exists())

    def test_separate_approval_requires_signoff_reference(self):
        item = self.new_draft()
        self.login_as(self.editor)
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/submit/')
        self.login_as(self.signer)
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/approve/', {
            'approval_reference': '   ',
        })
        item.refresh_from_db()
        self.assertEqual(item.status, 'review')
        self.assertIsNone(item.approved_at)

    def test_editor_can_reset_review_and_must_re_submit_changed_text(self):
        item = self.new_draft()
        self.login_as(self.editor)
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/submit/')
        item.refresh_from_db()
        old_hash = item.content_sha256
        url = f'/ns-admin/legal/translations/{item.pk}/'
        self.assertEqual(self.client.get(url+'edit/').status_code, 403)
        self.assertEqual(self.client.get(url+'draft/').status_code, 405)
        self.assertEqual(self.client.post(url+'draft/').status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'draft')
        self.assertIsNone(item.submitted_by)
        response = self.client.post(url+'edit/', {
            'document': str(self.document.pk), 'language': 'en',
            'content': '<script>untrusted</script> Revised language.',
        })
        self.assertEqual(response.status_code, 302)
        self.client.post(url+'submit/')
        item.refresh_from_db()
        self.assertNotEqual(item.content_sha256, old_hash)
        self.assertContains(self.client.get(url), '&lt;script&gt;')
        self.assertNotContains(self.client.get(url), '<script>untrusted</script>')

    def test_source_change_aborts_signoff_and_stays_unreleased(self):
        item = self.new_draft()
        self.login_as(self.editor)
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/submit/')
        LegalDocument.objects.filter(pk=self.document.pk).update(
            content=self.document.content+'\nUpdated canonical source',
        )
        self.login_as(self.signer)
        self.client.post(f'/ns-admin/legal/translations/{item.pk}/approve/', {
            'approval_reference': 'LEGAL-REVIEW-STALE',
        })
        item.refresh_from_db()
        self.assertEqual(item.status, 'review')
        self.assertFalse(item.is_publishable())
        self.assertIsNone(item.approved_by)

    def test_reader_can_view_but_not_mutate_and_no_unapproved_leak(self):
        item = self.new_draft()
        self.login_as(self.reader)
        self.assertEqual(self.client.get(f'/ns-admin/legal/translations/{item.pk}/').status_code, 200)
        self.assertNotContains(self.client.get('/legal/privacy/', HTTP_ACCEPT_LANGUAGE='en'), item.content)
        self.assertEqual(self.client.post(f'/ns-admin/legal/translations/{item.pk}/draft/').status_code, 403)
