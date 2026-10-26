"""Issue #91: explicit default-off signed legal offers for account onboarding."""
import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import User
from apps.companies.models import Company, Invitation
from apps.core.security import token_hash
from apps.legal.models import LegalAcceptance, LegalDocument


def signed_token(response):
    match = re.search(
        r'name="account_snapshot" value="([^"]+)"',
        response.content.decode(),
    )
    assert match is not None, 'Account legal snapshot input missing'
    return match.group(1)


@override_settings(
    LEGAL_ACCOUNT_SNAPSHOT_REQUIRED=True,
    LEGAL_TRANSLATIONS_PUBLIC_ENABLED=False,
)
class AccountSignedLegalOfferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for doc_type in ('terms', 'privacy'):
            LegalDocument.objects.create(
                doc_type=doc_type, version='signed-account-v1',
                content='German legal ' + doc_type + ' original.',
                valid_from=timezone.now() - timedelta(days=1), active=True,
            )

    def registration_data(self, email='signed-private@example.test', customer_type='private'):
        return {
            'customer_type': customer_type,
            'first_name': 'Signed', 'last_name': 'Customer',
            'email': email, 'password': 'SignedAccountRegression-2026!',
            'company_name': 'Signed Company GmbH' if customer_type == 'company' else '',
            'accept_terms': 'on', 'accept_privacy': 'on',
        }

    def invitation(self, email='signed-invitee@example.test'):
        inviter = User.objects.create_user(
            email='inviter-'+email, password='InviterAccount-2026!',
            first_name='Inviter', last_name='Test',
        )
        company = Company.objects.create(
            customer_number='C-' + str(Company.objects.count()+1),
            name='Signed Invite GmbH', email='company-'+email,
        )
        raw_token = 'invite-'+email
        invite = Invitation.objects.create(
            company=company, email=email, first_name='Invitee', last_name='Signed',
            role='member', token_hash=token_hash(raw_token),
            expires_at=timezone.now()+timedelta(days=1),
            invited_by=inviter,
        )
        return invite, reverse('accounts:accept_invitation', args=[raw_token])

    def assert_signed_evidence(self, user, source):
        rows = list(LegalAcceptance.objects.filter(user=user))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.evidence['source'], source)
            self.assertEqual(
                row.evidence['verification'], 'signed_session_bound_document_offer',
            )
            self.assertEqual(
                row.evidence['presentation_proof'], 'links_offered_not_read_receipts',
            )
            self.assertEqual(row.evidence['document']['document_id'], str(row.document_id))
            self.assertEqual(row.evidence['document']['document_version'], 'signed-account-v1')
            self.assertEqual(row.evidence['document']['body_language'], 'de')
            self.assertEqual(len(row.evidence['document']['body_sha256']), 64)
            self.assertEqual(len(row.evidence['document']['source_identity_sha256']), 64)
            self.assertEqual(set(row.evidence['documents']), {'terms', 'privacy'})
            self.assertIn('offered_at', row.evidence)
            self.assertIn('accepted_at', row.evidence)
            self.assertNotIn('read', row.evidence)
            self.assertNotIn('viewed', row.evidence)

    @patch('apps.accounts.views.queue_email')
    def test_private_registration_pins_german_fallback_and_evidence(self, _queue):
        with override('en'):
            response = self.client.get(reverse('accounts:register'))
            token = signed_token(response)
            self.assertContains(response, 'account_snapshot=')
            # The linked exact German body is available even under English UI.
            match = re.search(r'href="([^"]+account_snapshot=[^"]+)"', response.content.decode())
            self.assertIsNotNone(match)
            link = match.group(1).replace('&amp;', '&')
            legal = self.client.get(link, HTTP_ACCEPT_LANGUAGE='en')
            self.assertEqual(legal.status_code, 200)
            self.assertEqual(legal.context['legal_content_language'], 'de')
            self.assertEqual(legal['Cache-Control'], 'no-store')
            self.assertEqual(legal['Referrer-Policy'], 'no-referrer')
            self.assertEqual(legal['X-Robots-Tag'], 'noindex, noarchive')
            payload = self.registration_data()
            payload['account_snapshot'] = token
            created = self.client.post(reverse('accounts:register'), payload)
            self.assertEqual(created.status_code, 302)
        self.assert_signed_evidence(User.objects.get(email=payload['email']), 'registration')

    @patch('apps.accounts.views.queue_email')
    def test_company_registration_still_routes_to_mfa(self, _queue):
        token = signed_token(self.client.get(reverse('accounts:register')))
        payload = self.registration_data(
            'signed-company-admin@example.test', customer_type='company',
        )
        payload['account_snapshot'] = token
        response = self.client.post(reverse('accounts:register'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:two_factor_setup'))
        self.assert_signed_evidence(User.objects.get(email=payload['email']), 'registration')

    def test_missing_or_tampered_token_fails_closed(self):
        url = reverse('accounts:register')
        self.assertEqual(self.client.post(url, self.registration_data()).status_code, 200)
        self.assertFalse(User.objects.filter(email='signed-private@example.test').exists())
        token = signed_token(self.client.get(url))
        bad = self.registration_data()
        bad['account_snapshot'] = token + 'tampered'
        self.assertEqual(self.client.post(url, bad).status_code, 200)
        self.assertFalse(User.objects.filter(email=bad['email']).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    def test_other_session_rejected_and_two_tabs_do_not_invalidate_each_other(self):
        url = reverse('accounts:register')
        first = signed_token(self.client.get(url))
        second = signed_token(self.client.get(url))
        another = Client()
        payload = self.registration_data()
        payload['account_snapshot'] = first
        self.assertEqual(another.post(url, payload).status_code, 200)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())
        # Issuing a second GET must not revoke the first tab's valid offer.
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assert_signed_evidence(User.objects.get(email=payload['email']), 'registration')

    def test_document_change_invalidates_post_and_pinned_links(self):
        url = reverse('accounts:register')
        response = self.client.get(url)
        token = signed_token(response)
        LegalDocument.objects.filter(doc_type='privacy').update(
            content='German privacy text changed after offer.',
        )
        payload = self.registration_data()
        payload['account_snapshot'] = token
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())
        self.assertEqual(LegalAcceptance.objects.count(), 0)
        link = '/legal/privacy/?account_snapshot=' + token
        pinned = self.client.get(link)
        self.assertEqual(pinned.status_code, 409)
        self.assertEqual(pinned['Cache-Control'], 'no-store')

    def test_new_invitation_binds_invitee_and_consumes_capability(self):
        invitation, url = self.invitation()
        token = signed_token(self.client.get(url))
        response = self.client.post(url, {
            'first_name': 'Invitee', 'last_name': 'Signed',
            'password': 'SignedInviteeRegression-2026!',
            'accept_terms': 'on', 'accept_privacy': 'on',
            'account_snapshot': token,
        })
        self.assertEqual(response.status_code, 302)
        self.assert_signed_evidence(User.objects.get(email=invitation.email), 'invitation')
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_invitation_offer_cannot_be_used_for_different_invitation(self):
        invitation_a, url_a = self.invitation('invited-a@example.test')
        invitation_b, url_b = self.invitation('invited-b@example.test')
        token_a = signed_token(self.client.get(url_a))
        response = self.client.post(url_b, {
            'first_name': 'Invitee', 'last_name': 'Signed',
            'password': 'SignedInviteeRegression-2026!',
            'accept_terms': 'on', 'accept_privacy': 'on',
            'account_snapshot': token_a,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email=invitation_b.email).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    def test_missing_invitation_token_cannot_create_user(self):
        invite, url = self.invitation()
        response = self.client.post(url, {
            'first_name': 'Invitee', 'last_name': 'Signed',
            'password': 'SignedInviteeRegression-2026!',
            'accept_terms': 'on', 'accept_privacy': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    def test_out_of_scope_or_mixed_legal_link_is_rejected(self):
        token = signed_token(self.client.get(reverse('accounts:register')))
        self.assertEqual(
            self.client.get('/legal/license/?account_snapshot='+token).status_code,
            409,
        )
        self.assertEqual(
            self.client.get('/legal/terms/?account_snapshot='+token+'&checkout_snapshot=bad').status_code,
            409,
        )


class AccountOfferDefaultOffTests(TestCase):
    def test_snapshot_inputs_are_absent_when_gate_is_off(self):
        with override_settings(LEGAL_ACCOUNT_SNAPSHOT_REQUIRED=False):
            response = self.client.get(reverse('accounts:register'))
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('name="account_snapshot"', response.content.decode())
