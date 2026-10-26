"""Browser-link and order evidence contract for public legal checkout."""
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.legal.checkout_snapshot import validate_snapshot
from apps.legal.models import LegalAcceptance, LegalDocument
from apps.orders.models import Order


@override_settings(
    LEGAL_TRANSLATIONS_PUBLIC_ENABLED=False,
    LEGAL_CHECKOUT_SNAPSHOT_REQUIRED=True,
)
class SignedCheckoutLegalSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command('seed_legal_documents_2026', vat_id='DE123456789', stdout=StringIO())
        product = Product.objects.create(
            code='PRO', name='PROMPTFINISHER Pro', active=True,
            purchasable=True, visible=True, default_license_days=365,
            default_device_limit=2, reminder_1_days=60,
            reminder_2_days=30, critical_warning_days=7,
        )
        ProductPrice.objects.create(
            product=product, price_type='new', gross_amount=Decimal('35.88'),
            currency='EUR', valid_from=timezone.now(),
        )
        TaxRule.objects.create(
            country='DE', customer_type='company',
            tax_rate=Decimal('19.00'), active=True,
        )

    def snapshot(self, customer_type='company'):
        response = self.client.get(
            '/api/v1/checkout/legal-snapshot/',
            {'customer_type': customer_type},
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return response.json()

    def form(self, token=''):
        return {
            'quantity': '1', 'customer_type': 'company',
            'first_name': 'Ada', 'last_name': 'Lovelace',
            'email': 'legal-checkout-new@example.test',
            'phone': '', 'company_name': 'Legal Checkout GmbH',
            'legal_form': 'GmbH', 'vat_id': '', 'tax_number': '',
            'street': 'Testweg', 'house_number': '1',
            'postal_code': '57072', 'city': 'Siegen', 'country': 'DE',
            'accept_terms': 'on', 'accept_privacy': 'on',
            'accept_license': 'on', 'legal_snapshot_token': token,
        }

    def test_snapshot_records_exact_language_hashes_and_pinned_links(self):
        payload = self.snapshot()
        from apps.legal.checkout_snapshot import MAX_AGE_SECONDS
        self.assertEqual(payload['expiresInSeconds'], MAX_AGE_SECONDS - 60)
        self.assertEqual(payload['customerType'], 'company')
        self.assertEqual(set(payload['documents']), {'terms', 'privacy', 'license'})
        self.assertEqual(payload['documents']['terms']['bodyLanguage'], 'de')
        token = payload['token']
        self.assertGreater(len(token), 60)
        from django.core import signing
        from apps.legal.checkout_snapshot import SIGNING_SALT
        signed = signing.loads(token, salt=SIGNING_SALT)
        for offered in signed['documents'].values():
            self.assertEqual(
                set(offered), {
                    'document_id', 'document_type', 'document_version',
                    'source_identity_sha256', 'body_language', 'body_sha256',
                },
            )
            self.assertNotIn('approved_by_id', offered)
            self.assertNotIn('approval_reference', offered)
        evidence, documents = validate_snapshot(
            self._get_request_with_current_session(), token, 'company',
        )
        self.assertEqual(evidence['verification'], 'signed_session_bound_document_offer')
        self.assertEqual(evidence['presentation_proof'], 'links_offered_not_read_receipts')
        self.assertEqual(set(documents), {'terms', 'privacy', 'license'})
        for kind, entry in payload['documents'].items():
            response = self.client.get(entry['url'])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response['X-Robots-Tag'], 'noindex, noarchive')
            self.assertEqual(response.context['legal_content_language'], 'de')
            self.assertEqual(response.context['document'].pk, documents[kind].pk)
            self.assertContains(response, 'lang="de"')

    def _get_request_with_current_session(self):
        from django.test import RequestFactory

        request = RequestFactory().get('/checkout/')
        request.session = self.client.session
        return request

    def test_snapshot_is_session_bound_and_cannot_be_tampered(self):
        snap = self.snapshot()
        link = snap['documents']['privacy']['url']
        self.assertEqual(self.client.get(link).status_code, 200)
        other_browser = Client()
        rejected = other_browser.get(link)
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected['Cache-Control'], 'no-store')
        self.assertEqual(rejected['Referrer-Policy'], 'no-referrer')
        self.assertEqual(rejected['X-Robots-Tag'], 'noindex, noarchive')
        broken = ('a' if snap['token'][0] != 'a' else 'b') + snap['token'][1:]
        with self.assertRaises(ValidationError):
            validate_snapshot(
                self._get_request_with_current_session(),
                broken, 'company',
            )

    def test_version_only_change_blocks_both_checkout_and_pinned_display(self):
        snap = self.snapshot()
        original_link = snap['documents']['terms']['url']
        LegalDocument.objects.filter(doc_type='terms', active=True).update(
            version='relabelled-v2',
        )
        self.assertEqual(self.client.get(original_link).status_code, 409)
        with self.assertRaises(ValidationError):
            validate_snapshot(
                self._get_request_with_current_session(),
                snap['token'], 'company',
            )

    def test_early_performance_statement_is_versioned_for_every_language(self):
        from apps.legal.checkout_clause import (
            CLAUSE_ID, EARLY_PERFORMANCE_STATEMENTS,
            early_performance_statement,
        )
        from apps.legal.models import LegalDocumentTranslation

        languages = {'de', 'en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl'}
        self.assertEqual(set(EARLY_PERFORMANCE_STATEMENTS), languages)
        self.assertEqual(CLAUSE_ID, 'early-performance-services-2026-v1')
        for language in languages:
            with self.subTest(language=language):
                statement = early_performance_statement(language)
                self.assertEqual(statement['statement_id'], CLAUSE_ID)
                self.assertEqual(statement['language'], language)
                self.assertEqual(statement['text'], EARLY_PERFORMANCE_STATEMENTS[language])
                self.assertTrue(statement['text'].strip())
                self.assertEqual(
                    statement['sha256'],
                    LegalDocumentTranslation.fingerprint(statement['text']),
                )
        self.assertEqual(early_performance_statement('invalid')['language'], 'de')

    def test_early_performance_copy_change_invalidates_private_offer(self):
        from unittest.mock import patch
        from apps.legal.checkout_snapshot import validate_snapshot

        offer = self.snapshot('private')
        original_clause = offer['earlyPerformance']
        from apps.legal.models import LegalDocumentTranslation
        new_text = original_clause['text'] + ' Altered.'
        modified = {**original_clause, 'text': new_text,
                    'sha256': LegalDocumentTranslation.fingerprint(new_text)}
        with patch(
            'apps.legal.checkout_snapshot.early_performance_statement',
            return_value=modified,
        ):
            with self.assertRaises(ValidationError):
                validate_snapshot(
                    self._get_request_with_current_session(),
                    offer['token'], 'private',
                )

    def test_customer_type_change_requires_a_new_snapshot(self):
        company = self.snapshot()
        with self.assertRaises(ValidationError):
            validate_snapshot(
                self._get_request_with_current_session(),
                company['token'], 'private',
            )
        private = self.snapshot('private')
        self.assertIn('withdrawal', private['documents'])
        clause = private['earlyPerformance']
        self.assertEqual(clause['statement_id'], 'early-performance-services-2026-v1')
        self.assertEqual(clause['language'], 'en')
        self.assertEqual(len(clause['sha256']), 64)
        self.assertIn('before the withdrawal period ends', clause['text'])
        from apps.legal.checkout_snapshot import SIGNING_SALT
        from django.core import signing
        signed = signing.loads(private['token'], salt=SIGNING_SALT)
        self.assertEqual(
            signed['early_performance']['sha256'], clause['sha256'],
        )
        self.assertNotIn('text', signed['early_performance'])
        evidence, _documents = validate_snapshot(
            self._get_request_with_current_session(),
            private['token'], 'private',
        )
        self.assertEqual(
            evidence['early_performance_clause']['text'], clause['text'],
        )
        # A newer offer in another tab must not invalidate this one.
        company_evidence, _company_documents = validate_snapshot(
            self._get_request_with_current_session(),
            company['token'], 'company',
        )
        self.assertEqual(company_evidence['ui_language'], 'en')
        self.assertEqual(self.client.get(company['documents']['terms']['url']).status_code, 200)
        self.assertEqual(
            self.client.get(private['documents']['withdrawal']['url']).status_code,
            200,
        )

    def test_signed_offers_expire_after_thirty_minutes_across_tabs(self):
        """Offer and pinned legal links must reject an expired signed token.

        An unexpired offer from the same browser is valid, while expiry must
        fail closed even when the authoritative Redis nonce is still current.
        """
        import time

        from apps.legal.checkout_snapshot import MAX_AGE_SECONDS

        company_offer = self.snapshot('company')
        private_offer = self.snapshot('private')
        self.assertEqual(MAX_AGE_SECONDS, 1800)
        request = self._get_request_with_current_session()
        self.assertEqual(
            validate_snapshot(request, company_offer['token'], 'company')[0][
                'verification'
            ],
            'signed_session_bound_document_offer',
        )
        self.assertEqual(
            self.client.get(private_offer['documents']['withdrawal']['url']).status_code,
            200,
        )

        now = time.time()
        # Django's TimestampSigner validates a token's original signing time;
        # no mutation of the token or legal document contents is needed.
        with patch('django.core.signing.time.time', return_value=now + 1790):
            self.assertEqual(
                self.client.get(company_offer['documents']['terms']['url']).status_code,
                200,
            )
        with patch('django.core.signing.time.time', return_value=now + 1805):
            for offer, customer_type, document_type in (
                (company_offer, 'company', 'terms'),
                (private_offer, 'private', 'withdrawal'),
            ):
                with self.subTest(customer_type=customer_type):
                    with self.assertRaises(ValidationError):
                        validate_snapshot(
                            self._get_request_with_current_session(),
                            offer['token'], customer_type,
                        )
                    response = self.client.get(offer['documents'][document_type]['url'])
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response['Cache-Control'], 'no-store')

    def test_second_tab_does_not_invalidate_first_checkout_offer(self):
        first_tab = self.snapshot('company')
        second_tab = self.snapshot('private')
        for offer, customer_type in ((first_tab, 'company'), (second_tab, 'private')):
            evidence, _documents = validate_snapshot(
                self._get_request_with_current_session(), offer['token'], customer_type,
            )
            self.assertEqual(evidence['verification'], 'signed_session_bound_document_offer')
            self.assertEqual(self.client.get(offer['documents']['terms']['url']).status_code, 200)
        self.assertEqual(self.client.get(second_tab['documents']['withdrawal']['url']).status_code, 200)

    def test_simultaneous_first_offers_with_established_session_are_stable(self):
        """Two stale session reads must not race to install distinct nonces.

        Both requests read the same preexisting database session before either
        sends its response. The previous random on-missing nonce implementation
        created two different values and invalidated the losing tab.
        """
        from importlib import import_module

        from django.conf import settings
        from django.core import signing
        from django.test import RequestFactory

        from apps.legal.checkout_snapshot import (
            SESSION_NONCE, SIGNING_SALT, _nonce_cache_key,
            issue_snapshot, rotate_session_nonce,
        )
        from django.core.cache import cache

        session = self.client.session
        session['unrelated_preexisting_data'] = 'persisted'
        session.save()
        session_key = session.session_key
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session_key
        SessionStore = import_module(settings.SESSION_ENGINE).SessionStore

        # Independent session snapshots: neither request sees writes from
        # the other request, just as during concurrent GET handling.
        company_request = RequestFactory().get('/api/v1/checkout/legal-snapshot/')
        company_request.session = SessionStore(session_key=session_key)
        private_request = RequestFactory().get('/api/v1/checkout/legal-snapshot/')
        private_request.session = SessionStore(session_key=session_key)
        company = issue_snapshot(company_request, 'company')
        private = issue_snapshot(private_request, 'private')
        company_nonce = signing.loads(company['token'], salt=SIGNING_SALT)['nonce']
        private_nonce = signing.loads(private['token'], salt=SIGNING_SALT)['nonce']
        self.assertEqual(company_nonce, private_nonce)
        self.assertTrue(company_nonce)
        self.assertFalse(company_request.session.modified)
        self.assertFalse(private_request.session.modified)
        self.assertIsNone(SessionStore(session_key=session_key).get(SESSION_NONCE))
        self.assertEqual(self.client.get(company['documents']['terms']['url']).status_code, 200)
        self.assertEqual(self.client.get(private['documents']['withdrawal']['url']).status_code, 200)

        # Simulate an authenticated middleware request which loaded session
        # data BEFORE handoff but saves its activity timestamp AFTER handoff.
        stale_middleware_session = SessionStore(session_key=session_key)
        self.assertEqual(
            stale_middleware_session['unrelated_preexisting_data'], 'persisted',
        )
        # The provider handoff updates the authoritative Redis nonce,
        # invalidating BOTH earlier offers independently of session writes.
        self.assertEqual(cache.get(_nonce_cache_key(company_request)), company_nonce)
        rotate_session_nonce(company_request)
        self.assertNotEqual(cache.get(_nonce_cache_key(company_request)), company_nonce)
        stale_middleware_session['last_activity_at'] = 'late-middleware-write'
        stale_middleware_session.save()
        self.assertEqual(self.client.get(company['documents']['terms']['url']).status_code, 409)
        self.assertEqual(self.client.get(private['documents']['withdrawal']['url']).status_code, 409)

    def test_nonce_cache_eviction_or_failure_never_authorizes_stale_offer(self):
        from django.core.cache import cache
        from apps.legal.checkout_snapshot import _nonce_cache_key
        snapshot = self.snapshot()
        link = snapshot['documents']['terms']['url']
        self.assertEqual(self.client.get(link).status_code, 200)

        from django.test import RequestFactory
        request = RequestFactory().get('/checkout/')
        request.session = self.client.session
        cache.delete(_nonce_cache_key(request))
        # Do not silently reconstruct a deleted nonce from session contents.
        self.assertEqual(self.client.get(link).status_code, 409)
        # New offers may safely allocate a fresh nonce.
        new_offer = self.snapshot()
        self.assertEqual(
            self.client.get(new_offer['documents']['terms']['url']).status_code, 200,
        )
        self.assertEqual(self.client.get(link).status_code, 409)

        with patch('apps.legal.checkout_snapshot.cache.get', side_effect=RuntimeError('Redis unavailable')):
            self.assertEqual(self.client.get(new_offer['documents']['terms']['url']).status_code, 409)
            failed_issue = self.client.get('/api/v1/checkout/legal-snapshot/')
            self.assertEqual(failed_issue.status_code, 503)

    @patch('apps.payments.mollie.mollie_runtime_ready', return_value=True)
    def test_unsigned_checkout_fails_closed_before_account_or_order(
        self, _ready,
    ):
        response = self.client.post('/api/v1/checkout/start/', self.form())
        self.assertEqual(response.status_code, 302)
        self.assertIn('error=unavailable', response['Location'])
        self.assertFalse(User.objects.exists())
        self.assertFalse(Order.objects.exists())

    @patch('apps.payments.mollie.MollieClient')
    @patch('apps.payments.mollie.mollie_runtime_ready', return_value=True)
    def test_completed_checkout_persists_signed_offer_in_order_and_acceptances(
        self, _ready, client_class,
    ):
        snap = self.snapshot()
        client_class.return_value.create_payment.return_value = {
            'id': 'tr_legal_offer_test', 'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/offer'}},
        }
        response = self.client.post(
            '/api/v1/checkout/start/', self.form(token=snap['token']),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://checkout.example.test/offer')
        order = Order.objects.get()
        evidence = order.billing_snapshot['legal_offer']
        self.assertEqual(evidence['verification'], 'signed_session_bound_document_offer')
        self.assertEqual(evidence['ui_language'], 'en')
        self.assertEqual(set(evidence['documents']), {'terms', 'privacy', 'license'})
        for data in evidence['documents'].values():
            self.assertEqual(data['body_language'], 'de')
            self.assertEqual(len(data['body_sha256']), 64)
            self.assertEqual(len(data['source_identity_sha256']), 64)
            self.assertIsNone(data['translation_id'])
        order_acceptances = LegalAcceptance.objects.filter(order=order)
        self.assertEqual(order_acceptances.count(), 3)
        for acceptance in order_acceptances:
            self.assertEqual(
                acceptance.evidence['legal_offer']['verification'],
                'signed_session_bound_document_offer',
            )
        # Successful handoff rotates the session nonce and invalidates all old links.
        with self.assertRaises(ValidationError):
            validate_snapshot(
                self._get_request_with_current_session(),
                snap['token'], 'company',
            )
        self.assertEqual(self.client.get(snap['documents']['terms']['url']).status_code, 409)
