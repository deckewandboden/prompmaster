"""Regression: Free works anonymously and never weakens Pro authentication."""

import json

from django.core.management import call_command
from django.test import Client, TestCase

from apps.accounts.models import User
from apps.prompts.models import PromptLegacyContract


class PublicFreeAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)
        cls.user = User.objects.create_user(
            'public-free-2fa@example.test',
            'Free-2FA-Test-Password-2026!',
            two_factor_required=True,
            totp_secret_enc='configured-in-test',
        )
        cls.legacy_id = PromptLegacyContract.objects.filter(
            source='FREE_1_2_4',
        ).values_list('legacy_id', flat=True).first()
        assert cls.legacy_id is not None

    def _pending_session(self):
        client = Client()
        client.force_login(self.user)
        session = client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = False
        session.save()
        return client

    def _compose(self, client, product='FREE', *, url='/api/v1/prompts/free/compose/', **kwargs):
        return client.post(
            url,
            json.dumps({
                'product': product,
                'task_id': self.legacy_id,
                'microsoft_tier': 'chatbasic',
                'input': {
                    'primary': 'Informationen für einen kostenlosen Prompt',
                    'secondary': '',
                },
            }),
            content_type='application/json',
            **kwargs,
        )

    def test_anonymous_visitors_can_open_free_and_use_the_composer(self):
        for path in ('/free/', '/free-old/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        catalog = self.client.get('/api/v1/prompts/free/')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()['catalog']['product_code'], 'FREE')
        composed = self._compose(self.client)
        self.assertEqual(composed.status_code, 200, composed.content)
        self.assertTrue(composed.json()['ok'])

    def test_pending_two_factor_does_not_interrupt_free(self):
        client = self._pending_session()
        self.assertEqual(client.get('/free/').status_code, 200)
        self.assertEqual(client.get('/free-old/').status_code, 200)
        catalog = client.get('/api/v1/prompts/free/')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()['catalog']['product_code'], 'FREE')
        composed = self._compose(client)
        self.assertEqual(composed.status_code, 200, composed.content)
        self.assertTrue(composed.json()['ok'])
        self.assertEqual(client.session.get('two_factor_ok'), False)

    def test_pending_two_factor_still_blocks_every_pro_entry(self):
        client = self._pending_session()
        for path in (
            '/pro/app/',
            '/portal/dashboard/',
            '/ns-admin/',
            '/api/v1/prompts/?product=PRO',
            '/api/v1/prompts/PM20-001/?product=PRO',
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, '/auth/2fa/')
        pro_compose = self._compose(
            client,
            product='PRO',
            url='/api/v1/prompts/compose/',
        )
        self.assertEqual(pro_compose.status_code, 302)
        self.assertEqual(pro_compose.url, '/auth/2fa/')

    def test_public_free_endpoints_cannot_be_switched_to_pro(self):
        client = self._pending_session()
        catalog = client.get('/api/v1/prompts/free/?product=PRO')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()['catalog']['product_code'], 'FREE')
        wrong_product = self._compose(client, product='PRO')
        self.assertEqual(wrong_product.status_code, 400)
        self.assertEqual(wrong_product.json()['error']['code'], 'choice')
        self.assertEqual(client.post('/free/').status_code, 302)
        self.assertEqual(client.post('/free/').url, '/auth/2fa/')

    def test_free_is_public_even_before_totp_setup(self):
        self.user.totp_secret_enc = ''
        self.user.save(update_fields=['totp_secret_enc'])
        client = self._pending_session()
        self.assertEqual(client.get('/free/').status_code, 200)
        self.assertEqual(self._compose(client).status_code, 200)
        protected = client.get('/portal/dashboard/')
        self.assertEqual(protected.status_code, 302)
        self.assertEqual(protected.url, '/auth/2fa/setup/')

    def test_expired_security_session_cannot_block_public_free(self):
        client = self._pending_session()
        session = client.session
        session['security_version'] = 'invalid'
        session.save()
        self.assertEqual(client.get('/free/').status_code, 200)
        self.assertEqual(self._compose(client).status_code, 200)
        self.assertEqual(client.get('/portal/dashboard/').status_code, 302)
        self.assertNotIn('_auth_user_id', client.session)

    def test_csrf_protection_remains_active_for_public_free_post(self):
        client = Client(enforce_csrf_checks=True)
        forbidden = self._compose(client)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(client.get('/free/').status_code, 200)
        token = client.cookies['csrftoken'].value
        allowed = self._compose(client, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(allowed.status_code, 200, allowed.content)

    def test_pending_2fa_can_change_free_language_but_not_bypass_account_security(self):
        client = self._pending_session()
        response = client.get('/auth/language/', {'language': 'pl', 'next': '/free/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/free/')
        self.assertEqual(response.cookies['promptfinisher_language'].value, 'pl')
        self.assertEqual(client.get('/free/').status_code, 200)
        protected = client.get('/auth/language/', {'language': 'pl', 'next': '/pro/app/'})
        self.assertEqual(protected.status_code, 302)
        self.assertEqual(protected.url, '/auth/2fa/')
        self.assertEqual(client.get('/pro/app/').status_code, 302)
        self.assertEqual(client.session.get('two_factor_ok'), False)

