"""Evidence transparency for legacy account and invitation consent flows.

A legacy acceptance links to a German LegalDocument row but is NOT a signed
GET-time offer, translated text snapshot, or document read receipt.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, Invitation
from apps.core.security import token_hash
from apps.legal.models import LegalAcceptance, LegalDocument


class LegacyAccountLegalEvidenceTests(TestCase):
    def setUp(self):
        # Keep per-IP registration budgets independent across QA cases.
        names = sorted(name for name in dir(type(self)) if name.startswith('test_'))
        self.client.defaults['REMOTE_ADDR'] = (
            f'203.0.115.{names.index(self._testMethodName) + 1}'
        )

    @classmethod
    def setUpTestData(cls):
        for doc_type in ('terms', 'privacy'):
            LegalDocument.objects.create(
                doc_type=doc_type,
                version='account-legacy-evidence-v1',
                content=f'Versioned German original for {doc_type}.',
                valid_from=timezone.now(),
                active=True,
            )

    def assert_legacy_evidence(self, user, source):
        entries = list(LegalAcceptance.objects.filter(user=user).select_related('document'))
        self.assertEqual(len(entries), 2)
        self.assertEqual({row.document.doc_type for row in entries}, {'terms', 'privacy'})
        for entry in entries:
            self.assertEqual(entry.document.version, 'account-legacy-evidence-v1')
            self.assertEqual(entry.evidence['source'], source)
            self.assertEqual(
                entry.evidence['verification'], 'legacy_without_signed_snapshot',
            )
            self.assertEqual(entry.evidence['presentation_proof'], 'not_recorded')
            self.assertNotIn('viewed', entry.evidence)
            self.assertNotIn('read', entry.evidence)
            self.assertNotIn('offered_at', entry.evidence)
            self.assertNotIn('body_sha256', entry.evidence)

    @patch('apps.accounts.views.queue_email')
    def test_registration_records_legacy_not_signed_evidence(self, _queue_email):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'customer_type': 'private',
            'first_name': 'Evidence',
            'last_name': 'Test',
            'email': 'evidence-registration@example.test',
            'password': 'EvidenceRegression-2026!',
            'company_name': '',
            'accept_terms': 'on',
            'accept_privacy': 'on',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='evidence-registration@example.test')
        self.assert_legacy_evidence(user, 'registration')

    @patch('apps.accounts.views.queue_email')
    def test_company_registration_records_legacy_not_signed_evidence(self, _queue_email):
        response = self.client.post(reverse('accounts:register'), {
            'customer_type': 'company',
            'first_name': 'Company',
            'last_name': 'Creator',
            'email': 'evidence-company-admin@example.test',
            'password': 'EvidenceCompanyCreator-2026!',
            'company_name': 'Evidence Company GmbH',
            'accept_terms': 'on',
            'accept_privacy': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:two_factor_setup'))
        user = User.objects.get(email='evidence-company-admin@example.test')
        self.assert_legacy_evidence(user, 'registration')

    def test_invitation_records_legacy_not_signed_evidence(self):
        inviter = User.objects.create_user(
            email='evidence-inviter@example.test',
            password='EvidenceInviter-2026!',
            first_name='Inviter', last_name='Test',
        )
        company = Company.objects.create(
            customer_number='C-INVITE-EVIDENCE',
            name='Invitation Evidence GmbH',
            email='evidence-company@example.test',
        )
        token = 'evidence-invitation-token'
        invitation = Invitation.objects.create(
            company=company,
            email='evidence-invitee@example.test',
            first_name='Invitee',
            last_name='Test',
            role='member',
            token_hash=token_hash(token),
            expires_at=timezone.now() + timedelta(days=1),
            invited_by=inviter,
        )
        url = reverse('accounts:accept_invitation', args=[token])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {
            'first_name': 'Invitee',
            'last_name': 'Test',
            'password': 'EvidenceInvitee-2026!',
            'accept_terms': 'on',
            'accept_privacy': 'on',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=invitation.email)
        self.assert_legacy_evidence(user, 'invitation')
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)

    def test_invalid_registration_consent_cannot_create_legal_acceptances(self):
        response = self.client.post(reverse('accounts:register'), {
            'customer_type': 'private',
            'first_name': 'Incomplete',
            'last_name': 'Consent',
            'email': 'missing-privacy-consent@example.test',
            'password': 'MissingPrivacyConsent-2026!',
            'accept_terms': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(
            email='missing-privacy-consent@example.test',
        ).exists())
        self.assertEqual(LegalAcceptance.objects.count(), 0)
