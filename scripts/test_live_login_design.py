#!/usr/bin/env python3
"""Offline regression suite for public read-only login audit; no network."""
import unittest

from audit_live_login_design import (
    CAPTIONS, LOGIN, LoginDocument, is_main_app_css, check_login
)


class LoginAuditContracts(unittest.TestCase):
    def test_hashed_and_unhashed_css_recognized(self):
        self.assertTrue(is_main_app_css("/static/css/app.css"))
        self.assertTrue(is_main_app_css("/static/css/app.a1b2c3d4e5f6.css"))
        self.assertTrue(is_main_app_css("/static/css/app.A1B2C3D4E5F6.css"))
        for path in (
            "/static/css/app.js",
            "/static/css/not-app.a1b2c3d4e5f6.css",
            "/static/css/app-malicious.css",
            "/static/css/app.not-a-hash.css",
            "/x/static/css/app.a1b2c3d4e5f6.css",
        ):
            self.assertFalse(is_main_app_css(path), path)

    def test_two_secondary_actions_and_stylesheet_parser(self):
        parser = LoginDocument()
        parser.feed("""
        <html><head>
          <link rel="stylesheet" href="/static/css/app.a1b2c3d4e5f6.css?v=20261113-login-actions1">
          <link rel="stylesheet" href="/static/css/datagrid.1a2b3c4d5e6f.css">
        </head><body>
        <div class="login-secondary-actions">
          <a href="/auth/register/?next=%2Fns-admin%2F" class="btn secondary">Konto anlegen</a>
          <a href="/auth/password-reset/" class="btn secondary">Passwort vergessen?</a>
        </div></body></html>
        """)
        self.assertEqual(len(parser.stylesheets), 2)
        self.assertEqual(len(parser.actions), 2)
        self.assertEqual(parser.actions[0]["text"], "Konto anlegen")
        self.assertTrue(is_main_app_css(parser.stylesheets[0].split("?")[0]))

    def test_ten_complete_caption_pairs(self):
        self.assertEqual(len(CAPTIONS), 10)
        for language, pair in CAPTIONS.items():
            self.assertEqual(len(pair), 2, language)
            self.assertTrue(all(part.strip() for part in pair))


if __name__ == "__main__":
    unittest.main()
