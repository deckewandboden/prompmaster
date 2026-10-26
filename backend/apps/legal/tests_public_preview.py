"""Preview-release acceptance: public Free/Pro i18n, but no new payments.

This is a separate release candidate, never a legal translation approval.
"""
from datetime import timedelta

from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.legal.models import LegalDocument
from apps.legal.preview_display import FALLBACK_NOTICES
from apps.payments.mollie import mollie_runtime_ready


class PublicLegalPreviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for kind, _label in LegalDocument.DOC_TYPES:
            LegalDocument.objects.create(
                doc_type=kind, version='preview-original-de',
                content='Nur die deutsche Originalfassung: ' + kind,
                valid_from=timezone.now() - timedelta(days=1), active=True,
            )

    def test_six_original_legal_documents_disclose_german_body_in_ten_ui_languages(self):
        for language in ('de', *FALLBACK_NOTICES):
            for kind, _label in LegalDocument.DOC_TYPES:
                with self.subTest(language=language, kind=kind):
                    response = self.client.get(
                        reverse('legal_public', args=[kind]),
                        HTTP_ACCEPT_LANGUAGE=language,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['legal_content_language'], 'de')
                    self.assertEqual(
                        response.context['legal_fallback_notice'],
                        '' if language == 'de' else FALLBACK_NOTICES[language],
                    )
                    self.assertContains(response, f'Nur die deutsche Originalfassung: {kind}')
                    self.assertContains(response, 'class="legal-content" lang="de"')
                    if language == 'de':
                        self.assertNotContains(response, 'class="alert warn"')
                    else:
                        self.assertContains(response, 'class="alert warn"')


class PreviewSalesLockTests(SimpleTestCase):
    @override_settings(ENVIRONMENT='production')
    def test_live_purchase_gate_is_off_regardless_of_any_provider_configuration(self):
        # Production is always blocked by this preview branch before consulting
        # DB-stored keys or accidentally enabled admin settings.
        self.assertIs(mollie_runtime_ready(), False)

    @override_settings(ENVIRONMENT='staging')
    def test_existing_staging_payment_configuration_semantics_are_preserved(self):
        # Existing integration tests may still use test payment credentials;
        # only the publicly deployable production variant is locked.
        from unittest.mock import patch
        with patch('apps.core.settings_store.get_setting', return_value='test-profile'):
            with patch('apps.integrations.services.get_secret', return_value='test_qa_key'):
                self.assertIs(mollie_runtime_ready(), True)
