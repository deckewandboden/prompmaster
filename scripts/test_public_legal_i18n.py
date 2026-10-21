#!/usr/bin/env python3
"""Check all visible fixed legal-page labels in nine gettext catalogues."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend"
LANGUAGES = ("en", "es", "pt", "tr", "ru", "pl", "fr", "it", "nl")
TEMPLATES = (
    "legal_base.html",
    "legal_public.html",
    "legal_action_form.html",
    "legal_action_success.html",
)


def translation_keys():
    keys = set()
    for name in TEMPLATES:
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "{% load static i18n %}" in source, name
        keys.update(re.findall(r'{%\s*translate\s+["\']([^"\']+)["\']\s*%}', source))
    backend = (ROOT / "apps" / "core" / "views.py").read_text(encoding="utf-8")
    actions = backend.split("def contract_withdrawal(request):", 1)[1]
    actions = actions.split("def checkout_csrf(request):", 1)[0]
    keys.update(re.findall(r"_\('([^']+)'\)", actions))
    return keys


class LegalInterfaceLanguageTests(unittest.TestCase):
    def test_every_fixed_label_has_translation_in_every_language(self):
        keys = translation_keys()
        self.assertGreaterEqual(len(keys), 20)
        for code in LANGUAGES:
            po = (ROOT / "locale" / code / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
            for key in keys:
                msgid = 'msgid "' + key.replace('\\', '\\\\').replace('"', '\\"') + '"'
                with self.subTest(locale=code, label=key):
                    self.assertIn(msgid + "\nmsgstr \"", po)
                    pattern = re.escape(msgid) + r'\nmsgstr "([^"]+)"'
                    match = re.search(pattern, po)
                    self.assertIsNotNone(match)
                    self.assertTrue(match.group(1).strip())

    def test_legal_original_content_remains_immutable(self):
        page = (ROOT / "templates" / "legal_public.html").read_text(encoding="utf-8")
        self.assertIn("{{ document.content|linebreaks }}", page)
        self.assertIn("{{ document.version }}", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
