"""Fail-closed, version-bound legal language release contracts (Issue #87)."""
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.legal.models import LegalDocument, LegalDocumentTranslation
from apps.legal.translation_display import FALLBACK_NOTICES


class LegalDocumentLanguageReleaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_legal_documents_2026', vat_id='DE123456789', stdout=StringIO())
        cls.document = LegalDocument.objects.get(doc_type='privacy', active=True)
        cls.reviewer = User.objects.create_superuser(
            email='legal-reviewer@example.test',
            password='StrongLegalReviewer-2026!',
            first_name='Legal', last_name='Reviewer', two_factor_required=False,
        )

    def create_translation(self, language='en', status='draft', body=None):
        return LegalDocumentTranslation.objects.create(
            document=self.document, language=language,
            content=body or 'Reviewed translation of the privacy policy.',
            status=status,
        )

    def get_english(self):
        return self.client.get('/legal/privacy/', HTTP_ACCEPT_LANGUAGE='en')

    def test_fallback_is_explicit_and_marks_german_body(self):
        response = self.get_english()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['legal_content_language'], 'de')
        self.assertContains(response, 'data-legal-language-fallback')
        self.assertContains(response, FALLBACK_NOTICES['en'])
        self.assertContains(response, 'lang="de"')
        self.assertContains(response, self.document.content.splitlines()[0])

    def test_german_original_has_no_fallback_warning(self):
        response = self.client.get('/legal/privacy/', HTTP_ACCEPT_LANGUAGE='de')
        self.assertEqual(response.context['legal_content_language'], 'de')
        self.assertNotContains(response, 'data-legal-language-fallback')

    @override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True)
    def test_draft_and_review_are_never_public(self):
        translation = self.create_translation()
        for status in ('draft', 'review'):
            with self.subTest(status=status):
                translation.status = status
                translation.save()
                response = self.get_english()
                self.assertEqual(response.context['legal_content_language'], 'de')
                self.assertNotContains(response, translation.content)
                self.assertContains(response, FALLBACK_NOTICES['en'])

    def test_approval_requires_permission_and_signoff_reference(self):
        translation = self.create_translation()
        with self.assertRaises(ValidationError):
            translation.approve(reviewer=self.reviewer, reference='LEGAL-123')
        translation.status = 'review'
        translation.save()
        with self.assertRaises(ValidationError):
            translation.approve(reviewer=self.reviewer, reference='  ')
        with self.assertRaises(ValidationError):
            translation.approve(reviewer=None, reference='LEGAL-123')
        self.assertEqual(translation.status, 'review')

    def test_direct_approved_status_assignment_cannot_bypass_permission(self):
        from django.utils import timezone

        translation = self.create_translation(status='review')
        translation.status = 'approved'
        translation.approved_by = self.reviewer
        translation.approved_at = timezone.now()
        translation.approval_reference = 'LEGAL-FORGED-DIRECT-APPROVAL'
        with self.assertRaises(ValidationError):
            translation.save()
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'review')
        self.assertIsNone(translation.approved_at)

    def test_stale_review_cannot_be_approved_after_return_to_draft(self):
        translation = self.create_translation(status='review')
        current = LegalDocumentTranslation.objects.get(pk=translation.pk)
        current.status = 'draft'
        current.save()
        with self.assertRaises(ValidationError):
            translation.approve(
                reviewer=self.reviewer, reference='LEGAL-STALE-SIGNOFF',
            )
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'draft')
        self.assertIsNone(translation.approved_at)

    def test_direct_approved_record_creation_is_not_permitted(self):
        from django.utils import timezone

        with self.assertRaises(ValidationError):
            LegalDocumentTranslation.objects.create(
                document=self.document, language='fr',
                content='Unauthorized published legal content',
                status='approved',
                source_sha256=LegalDocumentTranslation.fingerprint(self.document.content),
                content_sha256=LegalDocumentTranslation.fingerprint(
                    'Unauthorized published legal content',
                ),
                approved_by=self.reviewer,
                approved_at=timezone.now(),
                approval_reference='LEGAL-NO-REVIEW',
            )

    def test_approval_is_immutable_and_not_automatically_published(self):
        translation = self.create_translation(status='review')
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-001')
        self.assertTrue(translation.is_publishable())
        self.assertEqual(len(translation.source_sha256), 64)
        self.assertEqual(len(translation.content_sha256), 64)
        response = self.get_english()  # production feature flag defaults OFF
        self.assertEqual(response.context['legal_content_language'], 'de')
        translation.content = 'Modified without new approved primary version'
        with self.assertRaises(ValidationError):
            translation.save()
        translation.refresh_from_db()
        self.assertTrue(translation.is_publishable())
        # A no-op save must not undermine the immutable approved state.
        translation.save()
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'approved')

    @override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True)
    def test_only_matching_approved_translation_is_rendered(self):
        translation = self.create_translation(
            status='review',
            body='Privacy policy fully reviewed by a qualified legal reviewer.',
        )
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-002')
        response = self.get_english()
        self.assertEqual(response.context['legal_content_language'], 'en')
        self.assertContains(response, translation.content)
        self.assertNotContains(response, 'data-legal-language-fallback')
        self.assertContains(response, 'lang="en"')
        self.assertContains(response, translation.content_sha256)

    @override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True)
    def test_stale_original_or_tampered_translation_fail_closed(self):
        translation = self.create_translation(status='review')
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-003')
        LegalDocumentTranslation.objects.filter(pk=translation.pk).update(
            content='Changed after approval without new audit hash',
        )
        response = self.get_english()
        self.assertEqual(response.context['legal_content_language'], 'de')
        self.assertNotContains(response, 'Changed after approval')

        # Restoring the approved body but changing the canonical German source
        # must also disable the outdated translation.
        LegalDocumentTranslation.objects.filter(pk=translation.pk).update(
            content='Reviewed translation of the privacy policy.',
        )
        LegalDocument.objects.filter(pk=self.document.pk).update(
            content=self.document.content + '\\nCanonical change.',
        )
        response = self.get_english()
        self.assertEqual(response.context['legal_content_language'], 'de')
        self.assertContains(response, 'Canonical change.')

    @override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True)
    def test_untrusted_translation_html_is_escaped(self):
        translation = self.create_translation(
            status='review', body='<script>alert("attack")</script>',
        )
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-004')
        response = self.get_english()
        self.assertEqual(response.context['legal_content_language'], 'en')
        self.assertNotContains(response, '<script>alert(')
        self.assertContains(response, '&lt;script&gt;')

    def test_review_freezes_exact_source_and_translation_before_approval(self):
        translation = self.create_translation()
        self.assertEqual(translation.source_sha256, '')
        self.assertEqual(translation.content_sha256, '')
        translation.status = 'review'
        translation.save()
        self.assertEqual(
            translation.source_sha256,
            translation.fingerprint(self.document.content),
        )
        self.assertEqual(
            translation.content_sha256,
            translation.fingerprint(translation.content),
        )
        translation.content = 'Changed after review, not independently verified.'
        with self.assertRaises(ValidationError):
            translation.save()
        translation.refresh_from_db()
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-005')
        self.assertTrue(translation.is_publishable())

    def test_review_detects_german_source_change_before_approval(self):
        translation = self.create_translation(status='review')
        original_review_hash = translation.source_sha256
        LegalDocument.objects.filter(pk=self.document.pk).update(
            content=self.document.content + '\\nSource changed after review.',
        )
        # The in-memory FK intentionally remains stale. Approval MUST read
        # the real original from the database rather than this cached copy.
        self.assertEqual(translation.document.content, self.document.content)
        with self.assertRaises(ValidationError):
            translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-006')
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'review')
        self.assertEqual(translation.source_sha256, original_review_hash)

    def test_return_to_draft_requires_new_review_fingerprints(self):
        translation = self.create_translation(status='review')
        first = translation.content_sha256
        translation.status = 'draft'
        translation.save()
        self.assertFalse(translation.source_sha256)
        self.assertFalse(translation.content_sha256)
        translation.content = 'Revised text, needs an entirely new legal review.'
        translation.save()
        translation.status = 'review'
        translation.save()
        self.assertNotEqual(translation.content_sha256, first)
        translation.approve(reviewer=self.reviewer, reference='LEGAL-REVIEW-2026-007')
        self.assertTrue(translation.is_publishable())

    def test_admin_review_action_does_not_bypass_review_fingerprint(self):
        from unittest.mock import patch
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from apps.legal.admin import LegalDocumentTranslationAdmin

        translation = self.create_translation()
        admin_view = LegalDocumentTranslationAdmin(
            LegalDocumentTranslation, AdminSite(),
        )
        request = RequestFactory().post('/admin/legal/legaldocumenttranslation/')
        request.user = self.reviewer
        with patch.object(admin_view, 'message_user'):
            admin_view.submit_for_review(
                request, LegalDocumentTranslation.objects.filter(pk=translation.pk),
            )
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'review')
        self.assertEqual(
            translation.content_sha256,
            translation.fingerprint(translation.content),
        )

    def test_admin_review_fields_cannot_be_edited_until_draft_reset(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from apps.legal.admin import LegalDocumentTranslationAdmin

        admin_view = LegalDocumentTranslationAdmin(
            LegalDocumentTranslation, AdminSite(),
        )
        request = RequestFactory().get('/admin/legal/legaldocumenttranslation/')
        request.user = self.reviewer
        translation = self.create_translation()
        self.assertNotIn('content', admin_view.get_readonly_fields(request, translation))
        translation.status = 'review'
        translation.save()
        readonly = admin_view.get_readonly_fields(request, translation)
        for field in ('document', 'language', 'content'):
            self.assertIn(field, readonly)
        self.assertNotIn('approval_reference', readonly)
        translation.status = 'draft'
        translation.save()
        self.assertNotIn('content', admin_view.get_readonly_fields(request, translation))

    def test_admin_can_return_review_to_draft_and_start_new_review(self):
        from unittest.mock import patch
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from apps.legal.admin import LegalDocumentTranslationAdmin

        translation = self.create_translation(status='review')
        before_hash = translation.content_sha256
        admin_view = LegalDocumentTranslationAdmin(
            LegalDocumentTranslation, AdminSite(),
        )
        request = RequestFactory().post('/admin/legal/legaldocumenttranslation/')
        request.user = self.reviewer
        with patch.object(admin_view, 'message_user'):
            admin_view.return_to_draft(
                request, LegalDocumentTranslation.objects.filter(pk=translation.pk),
            )
        translation.refresh_from_db()
        self.assertEqual(translation.status, 'draft')
        self.assertEqual(translation.source_sha256, '')
        self.assertEqual(translation.content_sha256, '')
        translation.content = 'Improved translation following legal review feedback.'
        translation.save()
        translation.status = 'review'
        translation.save()
        self.assertNotEqual(before_hash, translation.content_sha256)

    def test_no_german_duplicate_and_unique_language_per_primary_version(self):
        with self.assertRaises(ValidationError):
            self.create_translation(language='de')
        self.create_translation(language='en')
        with self.assertRaises(ValidationError):
            self.create_translation(language='en')

    def test_all_original_legal_types_remain_accessible(self):
        for kind, _ in LegalDocument.DOC_TYPES:
            with self.subTest(kind=kind):
                response = self.client.get(f'/legal/{kind}/', HTTP_ACCEPT_LANGUAGE='fr')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['legal_content_language'], 'de')
                self.assertContains(response, FALLBACK_NOTICES['fr'])

    def test_all_nine_fallback_languages_have_notices(self):
        for language, notice in FALLBACK_NOTICES.items():
            with self.subTest(language=language):
                response = self.client.get(
                    '/legal/privacy/', HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, notice)
                self.assertEqual(response.context['legal_content_language'], 'de')
