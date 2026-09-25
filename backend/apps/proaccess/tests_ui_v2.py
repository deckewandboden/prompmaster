from __future__ import annotations

import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class PromptMasterV2RouteIsolationTests(TestCase):
    """Protect the redesign/legacy split without touching Golden Master bytes."""

    def _staff_session(self):
        user = User.objects.create_user(
            'pm-v2-staff@example.test',
            'PromptMaster-V2-Strong-Password-2026!',
            first_name='PromptMaster',
            last_name='V2',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-for-test',
        )
        self.client.force_login(user)
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session.save()
        return user

    def test_free_current_route_adds_v2_shell_but_legacy_route_does_not(self):
        current = self.client.get(reverse('free_product'))
        legacy = self.client.get(reverse('free_product_old'))

        self.assertEqual(current.status_code, 200)
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(current['Cache-Control'], 'private, no-store')
        self.assertEqual(legacy['Cache-Control'], 'public, max-age=300')

        current_html = current.content.decode('utf-8')
        legacy_html = legacy.content.decode('utf-8')

        self.assertIn('/static/js/free_catalog_bridge.20260918.js?v=20260925-mobile6', current_html)
        self.assertIn('/static/js/free_catalog_bridge.20260918.js?v=20260925-mobile6', legacy_html)
        self.assertRegex(
            current_html,
            r'<meta name="pm-free-compose" content="server" data-csrf="[A-Za-z0-9]+">',
        )
        self.assertNotIn('name="pm-free-compose"', legacy_html)

        self.assertIn('/static/css/promptmaster_v2.20260922.css?v=20260925-mobile6', current_html)
        self.assertIn('/static/js/promptmaster_ui_v2.20260922.js?v=20260925-mobile6', current_html)
        self.assertNotIn('/static/css/promptmaster_v2.20260922.css', legacy_html)
        self.assertNotIn('/static/js/promptmaster_ui_v2.20260922.js', legacy_html)

        remote_logo = (
            'https://netstyle.de/public_pictures/'
            'netstyle%20Logo%20OHNE%20Netz%20FREIGESTELLT.png'
        )
        self.assertNotIn(remote_logo, current_html)
        self.assertIn(remote_logo, legacy_html)

        # Remove only the additive V2 tags and the V2-only remote-logo
        # neutralization. The remaining response must be byte-for-byte
        # identical to the preserved pre-redesign route.
        # byte-for-byte identical to the preserved pre-redesign route.
        stripped = current_html.replace(
            '<link rel="stylesheet" href="/static/css/promptmaster_v2.20260922.css?v=20260925-mobile6">',
            '',
        ).replace(
            '<script src="/static/js/promptmaster_ui_v2.20260922.js?v=20260925-mobile6" defer></script>',
            '',
        ).replace(
            'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
            remote_logo,
        )
        stripped = re.sub(
            r'<meta name="pm-free-compose" content="server" data-csrf="[A-Za-z0-9]+">',
            '',
            stripped,
        )
        self.assertEqual(stripped, legacy_html)

    def test_pro_current_route_adds_v2_shell_but_legacy_route_does_not(self):
        self._staff_session()
        current = self.client.get(reverse('proaccess:content'))
        legacy = self.client.get(reverse('pro_product_old'))

        self.assertEqual(current.status_code, 200)
        self.assertEqual(legacy.status_code, 200)

        current_html = current.content.decode('utf-8')
        legacy_html = legacy.content.decode('utf-8')

        self.assertIn('/static/css/promptmaster_v2.20260922.css?v=20260925-mobile6', current_html)
        self.assertIn('/static/js/promptmaster_ui_v2.20260922.js?v=20260925-mobile6', current_html)
        self.assertNotIn('/static/css/promptmaster_v2.20260922.css', legacy_html)
        self.assertNotIn('/static/js/promptmaster_ui_v2.20260922.js', legacy_html)

        remote_logo = (
            'https://netstyle.de/public_pictures/'
            'netstyle%20Logo%20OHNE%20Netz%20FREIGESTELLT.png'
        )
        self.assertNotIn(remote_logo, current_html)
        self.assertIn(remote_logo, legacy_html)

        # Session links and the server runtime bridge must exist on both routes.
        for html in (current_html, legacy_html):
            self.assertIn('href="/ns-admin/"', html)
            self.assertIn('href="/auth/logout/"', html)
            self.assertIn('/api/v1/prompts/?product=PRO', html)
            self.assertIn('/api/v1/prompts/compose/', html)

    def test_pro_legacy_route_keeps_the_same_authentication_boundary(self):
        response = self.client.get(reverse('pro_product_old'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_legacy_route_names_are_stable_and_explicit(self):
        self.assertEqual(reverse('free_product_old'), '/free-old/')
        self.assertEqual(reverse('pro_product_old'), '/pro-old/')
