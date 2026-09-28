from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from apps.legal.models import ConsumerContractDeclaration, LegalDocument
from apps.notifications.models import EmailTemplate


class CurrentLegalDocumentSeedTests(TestCase):
    def test_seed_installs_complete_active_legal_set(self):
        out = StringIO()
        call_command('seed_legal_documents_2026', vat_id='DE123456789', stdout=out)

        expected = {
            'imprint', 'privacy', 'withdrawal',
            'terms', 'license', 'accessibility',
        }
        active = set(
            LegalDocument.objects.filter(active=True)
            .values_list('doc_type', flat=True)
        )
        self.assertEqual(active, expected)
        self.assertTrue(
            LegalDocument.objects.filter(
                doc_type='imprint',
                active=True,
                content__icontains='§ 5 Digitale-Dienste-Gesetz',
            ).exists()
        )
        self.assertTrue(
            LegalDocument.objects.filter(
                doc_type='privacy',
                active=True,
                content__icontains='Landesbeauftragte für Datenschutz',
            ).exists()
        )
        self.assertTrue(
            EmailTemplate.objects.filter(
                code='withdrawal_received',
                active=True,
            ).exists()
        )
        self.assertTrue(
            EmailTemplate.objects.filter(
                code='cancellation_received',
                active=True,
            ).exists()
        )
        for doc_type in expected:
            response = self.client.get(f'/legal/{doc_type}/')
            self.assertEqual(response.status_code, 200, doc_type)

    def test_reseed_replaces_active_version_without_duplicates(self):
        call_command('seed_legal_documents_2026', vat_id='DE123456789', stdout=StringIO())
        call_command('seed_legal_documents_2026', stdout=StringIO())
        for doc_type in (
            'imprint', 'privacy', 'withdrawal',
            'terms', 'license', 'accessibility',
        ):
            self.assertEqual(
                LegalDocument.objects.filter(doc_type=doc_type, active=True).count(),
                1,
            )


class ConsumerContractFunctionTests(TestCase):
    def setUp(self):
        cache.clear()
        EmailTemplate.objects.create(
            code='withdrawal_received',
            subject='Widerruf',
            body_text='{name} {contract_reference} {submitted_at} {declaration_id}',
            active=True,
        )
        EmailTemplate.objects.create(
            code='cancellation_received',
            subject='Kündigung',
            body_text=(
                '{name} {contract_reference} {submitted_at} {declaration_id} '
                '{cancellation_kind} {requested_end_date} {reason}'
            ),
            active=True,
        )

    def test_withdrawal_is_public_and_creates_timestamped_declaration(self):
        self.assertEqual(self.client.get('/vertrag-widerrufen/').status_code, 200)
        with patch('apps.notifications.services.queue_email') as queue:
            response = self.client.post(
                '/vertrag-widerrufen/',
                {
                    'name': 'Private Kundin',
                    'email': 'private@example.test',
                    'contract_reference': 'PM-ORDER-1001',
                },
            )
        self.assertEqual(response.status_code, 200)
        declaration = ConsumerContractDeclaration.objects.get(kind='withdrawal')
        self.assertEqual(declaration.email, 'private@example.test')
        self.assertEqual(declaration.contract_reference, 'PM-ORDER-1001')
        self.assertIsNotNone(declaration.submitted_at)
        queue.assert_called_once()
        self.assertContains(response, 'Widerruf eingegangen')
        self.assertContains(response, str(declaration.id))

    def test_cancellation_requires_reason_for_extraordinary_case(self):
        response = self.client.post(
            '/vertraege-kuendigen/',
            {
                'cancellation_kind': 'extraordinary',
                'name': 'Private Kundin',
                'email': 'private@example.test',
                'contract_reference': 'PM-ORDER-1001',
                'reason': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConsumerContractDeclaration.objects.count(), 0)
        self.assertContains(response, 'Kündigungsgrund ist erforderlich')

    def test_cancellation_confirmation_is_recorded(self):
        with patch('apps.notifications.services.queue_email') as queue:
            response = self.client.post(
                '/vertraege-kuendigen/',
                {
                    'cancellation_kind': 'ordinary',
                    'name': 'Private Kundin',
                    'email': 'private@example.test',
                    'contract_reference': 'PM-ORDER-1001',
                    'reason': '',
                },
            )
        self.assertEqual(response.status_code, 200)
        declaration = ConsumerContractDeclaration.objects.get(kind='cancellation')
        self.assertEqual(declaration.cancellation_kind, 'ordinary')
        queue.assert_called_once()
        self.assertContains(response, 'Kündigung eingegangen')
