"""Read-only release-readiness audit cannot silently declare legal approval."""
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.legal.models import LegalDocument, LegalDocumentTranslation


class LegalLocaleReadinessAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command(
            'seed_legal_documents_2026', vat_id='DE123456789',
            stdout=StringIO(),
        )
        cls.reviewer = User.objects.create_superuser(
            email='readiness-reviewer@example.test',
            password='ReadinessReviewer-2026!',
            first_name='Audit', last_name='Reviewer',
            two_factor_required=False,
        )

    def report(self):
        output = StringIO()
        call_command('audit_legal_locale_readiness', as_json=True, stdout=output)
        return json.loads(output.getvalue())

    @override_settings(
        LEGAL_TRANSLATIONS_PUBLIC_ENABLED=False,
        LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=False,
    )
    def test_unapproved_matrix_is_blocked_and_read_only(self):
        before = list(LegalDocument.objects.values_list('pk', 'version', 'content'))
        result = self.report()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['total_required_translations'], 54)
        self.assertEqual(len(result['entries']), 54)
        self.assertEqual(result['summary']['missing'], 54)
        self.assertEqual(result['summary']['verified_approved'], 0)
        self.assertEqual(result['source_errors'], [])
        self.assertEqual(
            result['feature_flags'],
            {
                'LEGAL_TRANSLATIONS_PUBLIC_ENABLED': False,
                'LEGAL_CHECKOUT_SNAPSHOT_REQUIRED': False,
            },
        )
        self.assertFalse(result['external_legal_signoff_verified_by_audit'])
        self.assertFalse(result['production_deployment_authorized_by_audit'])
        self.assertEqual(before, list(
            LegalDocument.objects.values_list('pk', 'version', 'content'),
        ))
        self.assertEqual(LegalDocumentTranslation.objects.count(), 0)
        with self.assertRaises(CommandError):
            call_command(
                'audit_legal_locale_readiness', strict=True,
                stdout=StringIO(),
            )

    def test_draft_review_and_approved_are_independently_classified(self):
        privacy = LegalDocument.objects.get(doc_type='privacy', active=True)
        terms = LegalDocument.objects.get(doc_type='terms', active=True)
        draft = LegalDocumentTranslation.objects.create(
            document=privacy, language='en', content='Unreviewed draft text.',
        )
        pending = LegalDocumentTranslation.objects.create(
            document=privacy, language='es',
            content='Submitted translation awaiting legal review.',
            status='review',
        )
        approved = LegalDocumentTranslation.objects.create(
            document=terms, language='fr',
            content='Independently reviewed French terms.',
            status='review',
        )
        approved.approve(
            reviewer=self.reviewer, reference='TEST-ONLY-LEGAL-SIGNOFF',
        )
        before = LegalDocumentTranslation.objects.count()
        result = self.report()
        self.assertEqual(result['summary']['draft'], 1)
        self.assertEqual(result['summary']['review'], 1)
        self.assertEqual(result['summary']['verified_approved'], 1)
        self.assertEqual(result['summary']['missing'], 51)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(LegalDocumentTranslation.objects.count(), before)
        for text in (
            draft.content, pending.content, approved.content,
            'TEST-ONLY-LEGAL-SIGNOFF',
        ):
            self.assertNotIn(text, json.dumps(result, ensure_ascii=False))

        LegalDocumentTranslation.objects.filter(pk=approved.pk).update(
            content='Changed after signing.',
        )
        changed = self.report()
        self.assertEqual(changed['summary']['verified_approved'], 0)
        self.assertEqual(changed['summary']['stale_approved'], 1)
        self.assertEqual(changed['summary']['missing'], 51)

    def test_missing_active_german_source_blocks_its_nine_languages(self):
        LegalDocument.objects.filter(doc_type='accessibility', active=True).update(
            active=False,
        )
        result = self.report()
        self.assertEqual(result['summary']['source_unavailable'], 9)
        self.assertEqual(result['summary']['missing'], 45)
        self.assertEqual(len(result['source_errors']), 1)
        self.assertEqual(
            result['source_errors'][0]['document_type'], 'accessibility',
        )
        self.assertEqual(result['status'], 'BLOCKED')

    @override_settings(
        LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True,
        LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=True,
    )
    def test_enabled_flags_do_not_turn_a_missing_matrix_green(self):
        result = self.report()
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertTrue(result['feature_flags']['LEGAL_TRANSLATIONS_PUBLIC_ENABLED'])
        self.assertTrue(result['feature_flags']['LEGAL_CHECKOUT_SNAPSHOT_REQUIRED'])
        self.assertFalse(result['external_legal_signoff_verified_by_audit'])
        self.assertEqual(LegalDocumentTranslation.objects.count(), 0)
