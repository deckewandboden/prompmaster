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
