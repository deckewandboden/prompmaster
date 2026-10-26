"""Issue #91: explicit default-off signed legal offers for account onboarding."""
import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core import signing
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import User
from apps.companies.models import Company, Invitation
from apps.core.security import token_hash
from apps.legal.models import LegalAcceptance, LegalDocument, LegalDocumentTranslation
from apps.legal.account_snapshot import SIGNING_SALT, validate_account_offer


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
    def setUp(self):
        # Real rate limiting uses IP-scoped Redis keys. Isolate each case so
        # independent security checks cannot trip another test's quota.
        names = sorted(
            name for name in dir(type(self)) if name.startswith('test_')
        )
        self.client.defaults['REMOTE_ADDR'] = f'203.0.113.{names.index(self._testMethodName) + 1}'

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
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response['X-Robots-Tag'], 'noindex, noarchive')
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

    def test_invalid_offer_error_is_localized_in_ten_languages(self):
        expected = {
            'de': 'Das Rechtsdokument-Angebot ist ungültig',
            'en': 'The legal document offer is invalid',
            'es': 'La oferta de documentos legales no es válida',
            'pt': 'A apresentação dos documentos legais é inválida',
            'tr': 'Hukuki belge teklifi geçersiz',
            'ru': 'Предложенные юридические документы недействительны',
            'pl': 'Przedstawione dokumenty prawne są nieprawidłowe',
            'fr': 'Les documents juridiques présentés ne sont pas valides',
            'it': 'I documenti legali presentati non sono validi',
            'nl': 'Het aangeboden juridische document is ongeldig',
        }
        for index, (language, snippet) in enumerate(expected.items(), start=1):
            with self.subTest(language=language), override(language):
                payload = self.registration_data(email=language+'-bad-offer@example.test')
                response = self.client.post(
                    reverse('accounts:register'),
                    payload,
                    HTTP_ACCEPT_LANGUAGE=language,
                    REMOTE_ADDR=f'198.51.100.{index}',
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, snippet)
                self.assertFalse(User.objects.filter(email=payload['email']).exists())

    @patch('apps.accounts.views.queue_email')
    def test_other_session_rejected_and_two_tabs_do_not_invalidate_each_other(self, _queue_email):
        url = reverse('accounts:register')
        first = signed_token(self.client.get(url))
        second = signed_token(self.client.get(url))
        another = Client(REMOTE_ADDR='203.0.114.1')
        payload = self.registration_data()
        payload['account_snapshot'] = first
        self.assertEqual(another.post(url, payload).status_code, 200)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())
        # Issuing a second GET must not revoke the first tab's valid offer.
        self.assertNotEqual(first, second)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assert_signed_evidence(User.objects.get(email=payload['email']), 'registration')

    def test_same_signed_offer_cannot_be_claimed_twice_before_session_rotation(self):
        token = signed_token(self.client.get(reverse('accounts:register')))
        request = RequestFactory().post(reverse('accounts:register'))
        request.session = self.client.session
        first, documents = validate_account_offer(
            request, token, flow='registration', lock=True,
        )
        self.assertEqual(first['verification'], 'signed_session_bound_document_offer')
        self.assertEqual(set(documents), {'terms', 'privacy'})
        with self.assertRaises(ValidationError):
            validate_account_offer(
                request, token, flow='registration', lock=True,
            )

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
        form_response = self.client.get(url)
        self.assertEqual(form_response['Cache-Control'], 'no-store')
        self.assertEqual(form_response['Referrer-Policy'], 'no-referrer')
        token = signed_token(form_response)
        # Django signatures are readable; the URL must not expose PII or
        # the invitation's bearer-token hash.
        signed_payload = signing.loads(token, salt=SIGNING_SALT)
        self.assertIn('identity_hmac', signed_payload['invitation'])
        self.assertNotIn('email', signed_payload['invitation'])
        self.assertNotIn('token_hash', signed_payload['invitation'])
        self.assertNotIn(invitation.email, str(signed_payload))
        self.assertNotIn(invitation.token_hash, str(signed_payload))
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
        consumed = self.client.get(url)
        self.assertEqual(consumed.status_code, 200)
        self.assertFalse(consumed.context['ok'])

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


    def test_signed_legal_query_presence_must_never_downgrade_to_public_view(self):
        token = signed_token(self.client.get(reverse('accounts:register')))
        # A completely unsigned document view still works as before.
        self.assertEqual(self.client.get('/legal/terms/').status_code, 200)
        invalid = (
            '/legal/terms/?account_snapshot=',
            '/legal/terms/?checkout_snapshot=',
            '/legal/terms/?account_snapshot=&checkout_snapshot=',
            '/legal/terms/?account_snapshot=' + token + '&account_snapshot=' + token,
            '/legal/terms/?account_snapshot=' + token + '&checkout_snapshot=',
        )
        for path in invalid:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertEqual(response['Referrer-Policy'], 'no-referrer')
                self.assertEqual(response['X-Robots-Tag'], 'noindex, noarchive')

    def test_expired_offer_rejects_submission_and_pinned_link(self):
        token = signed_token(self.client.get(reverse('accounts:register')))
        payload = self.registration_data(email='expired-account@example.test')
        payload['account_snapshot'] = token
        expired_time = signing.time.time() + 1802
        with patch('django.core.signing.time.time', return_value=expired_time):
            response = self.client.post(reverse('accounts:register'), payload)
            linked = self.client.get('/legal/terms/?account_snapshot=' + token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(linked.status_code, 409)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    def test_replay_cache_failure_rejects_claim(self):
        token = signed_token(self.client.get(reverse('accounts:register')))
        request = RequestFactory().post(reverse('accounts:register'))
        request.session = self.client.session
        with patch('apps.legal.account_snapshot.cache.add', side_effect=RuntimeError('redis unavailable')):
            with self.assertRaises(ValidationError):
                validate_account_offer(request, token, flow='registration', lock=True)


    def _approved_english_terms(self):
        reviewer = User.objects.create_superuser(
            email='issue91-qa-legal-reviewer@example.test',
            password='Issue91-ApprovedTranslation-QA-2026!',
            first_name='Issue', last_name='Reviewer',
            two_factor_required=False,
        )
        document = LegalDocument.objects.get(doc_type='terms', active=True)
        translation = LegalDocumentTranslation.objects.create(
            document=document, language='en',
            content='English terms for a controlled security regression test.',
            status='draft',
        )
        translation.status = 'review'
        translation.save()
        translation.approve(reviewer=reviewer, reference='QA-ISSUE91-NONPRODUCTION')
        return translation

    @patch('apps.accounts.views.queue_email')
    def test_approved_translation_is_pinned_and_saved_as_actual_offered_body(self, _queue):
        translation = self._approved_english_terms()
        url = reverse('accounts:register')
        with override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True), override('en'):
            response = self.client.get(url, HTTP_ACCEPT_LANGUAGE='en')
            token = signed_token(response)
            legal = self.client.get(
                '/legal/terms/?account_snapshot=' + token,
                HTTP_ACCEPT_LANGUAGE='en',
            )
            self.assertEqual(legal.status_code, 200)
            self.assertEqual(legal.context['legal_content_language'], 'en')
            self.assertContains(legal, translation.content)
            payload = self.registration_data('approved-english@example.test')
            payload['account_snapshot'] = token
            accepted = self.client.post(url, payload, HTTP_ACCEPT_LANGUAGE='en')
            self.assertEqual(accepted.status_code, 302)
        row = LegalAcceptance.objects.get(
            user__email=payload['email'], document__doc_type='terms',
        )
        self.assertEqual(row.evidence['ui_language'], 'en')
        self.assertEqual(row.evidence['document']['body_language'], 'en')
        self.assertEqual(
            row.evidence['document']['body_sha256'], translation.content_sha256,
        )
        self.assertEqual(row.evidence['document']['document_id'], str(translation.document_id))

    def test_approved_translation_tampering_invalidates_link_and_account_post(self):
        translation = self._approved_english_terms()
        url = reverse('accounts:register')
        with override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True), override('en'):
            token = signed_token(self.client.get(url, HTTP_ACCEPT_LANGUAGE='en'))
            # Bypass model save to simulate unauthorized database tampering.
            LegalDocumentTranslation.objects.filter(pk=translation.pk).update(
                content='Unreviewed English terms unexpectedly replaced the approved text.',
            )
            pinned = self.client.get(
                '/legal/terms/?account_snapshot=' + token,
                HTTP_ACCEPT_LANGUAGE='en',
            )
            payload = self.registration_data('tampered-english@example.test')
            payload['account_snapshot'] = token
            attempted = self.client.post(url, payload, HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(pinned.status_code, 409)
        self.assertEqual(attempted.status_code, 200)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    def test_draft_and_review_translations_remain_german_for_signed_offers(self):
        original = LegalDocument.objects.get(doc_type='terms', active=True)
        translation = LegalDocumentTranslation.objects.create(
            document=original, language='en',
            content='Never display this unapproved English draft.',
        )
        with override_settings(LEGAL_TRANSLATIONS_PUBLIC_ENABLED=True), override('en'):
            for status in ('draft', 'review'):
                with self.subTest(status=status):
                    if status == 'review':
                        translation.status = 'review'
                        translation.save()
                    token = signed_token(self.client.get(
                        reverse('accounts:register'), HTTP_ACCEPT_LANGUAGE='en',
                    ))
                    response = self.client.get(
                        '/legal/terms/?account_snapshot=' + token,
                        HTTP_ACCEPT_LANGUAGE='en',
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['legal_content_language'], 'de')
                    self.assertNotContains(response, translation.content)
                    self.assertContains(response, 'available only in German')

    def test_expired_invitation_rejects_signed_offer_and_account_creation(self):
        invite, url = self.invitation('expired-guest@example.test')
        token = signed_token(self.client.get(url))
        invite.expires_at = timezone.now() - timedelta(minutes=1)
        invite.save(update_fields=['expires_at'])
        response = self.client.post(url, {
            'first_name': 'Expired', 'last_name': 'Guest',
            'password': 'Issue91-ExpiredInvitation-QA-2026!',
            'accept_terms': 'on', 'accept_privacy': 'on',
            'account_snapshot': token,
        })
        pinned = self.client.get('/legal/privacy/?account_snapshot=' + token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pinned.status_code, 409)
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        self.assertFalse(LegalAcceptance.objects.exists())

    @patch('apps.accounts.views.queue_email')
    def test_signed_registration_accepts_real_csrf_after_pinned_legal_tabs(self, _queue):
        # Unlike Django's default Client, enforce real CSRF cookie + form
        # token + same-origin Origin checks after BOTH pinned GET requests.
        real_client = Client(
            enforce_csrf_checks=True, REMOTE_ADDR='198.51.100.159',
        )
        url = reverse('accounts:register')
        response = real_client.get(url, HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        token = signed_token(response)
        csrf = re.search(
            r'name="csrfmiddlewaretoken" value="([^"]+)"',
            response.content.decode(),
        )
        self.assertIsNotNone(csrf)
        self.assertIn('csrftoken', real_client.cookies)
        for kind in ('terms', 'privacy'):
            pinned = real_client.get(
                f'/legal/{kind}/?account_snapshot={token}',
                HTTP_HOST='testserver',
            )
            self.assertEqual(pinned.status_code, 200)
        data = self.registration_data(email='live-csrf-pass@example.test')
        data['account_snapshot'] = token
        data['csrfmiddlewaretoken'] = csrf.group(1)
        accepted = real_client.post(
            url, data,
            HTTP_HOST='testserver',
            HTTP_ORIGIN='http://testserver',
        )
        self.assertEqual(
            accepted.status_code, 302,
            f'Signed account registration rejected after pinned GETs: {accepted.status_code}',
        )
        self.assertTrue(User.objects.filter(email=data['email']).exists())
        self.assertEqual(
            LegalAcceptance.objects.filter(user__email=data['email']).count(),
            2,
        )

    def test_signed_registration_and_invitation_do_not_bypass_csrf(self):
        register_client = Client(
            enforce_csrf_checks=True, REMOTE_ADDR='198.51.100.110',
        )
        url = reverse('accounts:register')
        token = signed_token(register_client.get(url))
        payload = self.registration_data(email='csrf-guest@example.test')
        payload['account_snapshot'] = token
        self.assertEqual(register_client.post(url, payload).status_code, 403)
        self.assertFalse(User.objects.filter(email=payload['email']).exists())

        invite, invite_url = self.invitation('csrf-invitee@example.test')
        invite_client = Client(
            enforce_csrf_checks=True, REMOTE_ADDR='198.51.100.111',
        )
        invite_token = signed_token(invite_client.get(invite_url))
        self.assertEqual(invite_client.post(invite_url, {
            'first_name': 'CSRF', 'last_name': 'Invitee',
            'password': 'Issue91-CSRFInvitation-QA-2026!',
            'accept_terms': 'on', 'accept_privacy': 'on',
            'account_snapshot': invite_token,
        }).status_code, 403)
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        self.assertFalse(LegalAcceptance.objects.exists())


class AccountOfferDefaultOffTests(TestCase):
    def test_snapshot_inputs_are_absent_when_gate_is_off(self):
        with override_settings(LEGAL_ACCOUNT_SNAPSHOT_REQUIRED=False):
            response = self.client.get(reverse('accounts:register'))
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('name="account_snapshot"', response.content.decode())
