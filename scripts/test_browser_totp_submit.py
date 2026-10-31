#!/usr/bin/env python3
"""Offline contract guard for the WebKit MFA browser-login acceptance path."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "browser_runtime_smoke.py"


class BrowserTotpSubmitTests(unittest.TestCase):
    def source(self) -> str:
        script = RUNTIME.read_text(encoding="utf-8")
        return script.split("def _browser_login(", 1)[1].split(
            "\ndef _browser_login_password_only(", 1
        )[0]

    def test_mfa_form_is_submitted_natively_without_implicit_press_wait(self):
        code = self.source()
        self.assertIn("code_input.fill(submitted_code)", code)
        self.assertIn("el.form.requestSubmit()", code)
        self.assertIn("if (!el.form)", code)
        self.assertNotIn("code_input.press('Enter')", code)

    def test_success_requires_real_navigation_to_expected_destination(self):
        code = self.source()
        self.assertLess(code.index("el.form.requestSubmit()"), code.index("page.wait_for_url(lambda url:"))
        self.assertLess(code.index("page.wait_for_url(lambda url:"), code.index("if expected_path not in page.url:"))
        self.assertIn("wait_until='domcontentloaded'", code)
        self.assertIn("raise AssertionError(f'login for {email} ended", code)
        self.assertLess(
            code.index("if expected_path not in page.url:"),
            code.index("_LAST_SUCCESSFUL_TOTP_BY_EMAIL[email] = submitted_code"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
