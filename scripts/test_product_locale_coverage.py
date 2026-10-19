#!/usr/bin/env python3
"""Static UI-text completeness contract for protected Free/Pro V2 sources.

The Golden Master bytes remain untouched. This checks the runtime translation
catalogue that V2 injects next to them, for every language in use.
"""
import html
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "backend" / "private_assets"
LOCALE = ROOT / "backend" / "static" / "js" / "promptfinisher_product_i18n.20261011.js"
LANGUAGES = ("en", "es", "pt", "tr", "ru", "pl", "fr", "it", "nl")

# Stable product names, contact details and legal attribution must not be
# machine-translated into a different brand or email address.
UNTRANSLATED_IDENTIFIERS = {
    "CopilotPROMPTFINISHER 1.2.2 | Microsoft 365 Copilot",
    "CopilotPROMPTFINISHER Pro | netstyle",
    "CopilotPROMPTFINISHER",
    "CopilotPROMPTFINISHER Pro",
    "CopilotPROMPTFINISHER Free",
    "CopilotPROMPTFINISHER Pro für Outlook",
    "CopilotPROMPTFINISHER Pro anfragen",  # catalog translates this explicitly
    "PRO", "FREE", "info@netstyle.de",
}
UNTRANSLATED_IDENTIFIERS.remove("CopilotPROMPTFINISHER Pro anfragen")


def extract_translations():
    source = LOCALE.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    anchor = "  const TEXT="
    if source.count(anchor) != 1:
        raise AssertionError("Exactly one immutable base translation catalogue required")
    start = source.index(anchor) + len(anchor)
    base, _ = decoder.raw_decode(source[start:])
    if not isinstance(base, dict):
        raise AssertionError("Translation catalogue is not a map")
    for match in re.finditer(r"Object\.assign\(TEXT,\s*", source):
        delta, _ = decoder.raw_decode(source[match.end():])
        if not isinstance(delta, dict):
            raise AssertionError("Invalid supplementary translation catalogue")
        base.update(delta)
    return base


def visible_text_from_markup(path):
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"<(?:script|style)\b[^>]*>[\s\S]*?</(?:script|style)>",
                    "", source, flags=re.I)
    fragments = re.findall(r">([^<>{}]+)<", source)
    return {
        re.sub(r"\s+", " ", html.unescape(fragment)).strip()
        for fragment in fragments
        if re.search(r"[A-Za-zÄÖÜäöüß]", fragment)
    }


class ProductLanguageCoverageTests(unittest.TestCase):
    def test_free_and_pro_visible_text_in_all_ten_languages(self):
        translated = extract_translations()
        self.assertGreaterEqual(len(translated), 600)
        for name in ("promptfinisher_free_reference.html", "promptfinisher_pro_runtime.html"):
            with self.subTest(page=name):
                terms = visible_text_from_markup(PRODUCTS / name)
                missing = sorted(
                    t for t in terms
                    if t and t not in UNTRANSLATED_IDENTIFIERS
                    and t not in translated
                )
                self.assertEqual(missing, [], f"{name} has source text without translations")
                for source in terms:
                    if not source or source in UNTRANSLATED_IDENTIFIERS:
                        continue
                    for language in LANGUAGES:
                        with self.subTest(page=name, text=source[:35], language=language):
                            value = translated[source].get(language)
                            self.assertIsInstance(value, str)
                            self.assertTrue(value.strip(), f"{language}: {source}")

    def test_language_switch_is_visible_in_v2_shell(self):
        source = LOCALE.read_text(encoding="utf-8")
        self.assertIn("data-pf-product-language", source)
        self.assertIn("header.prepend(label)", source)
        self.assertIn("'/auth/language/?language='", source)
        self.assertIn("promptfinisher_language", source)

    def test_customer_prompt_and_input_values_not_translated(self):
        source = LOCALE.read_text(encoding="utf-8")
        self.assertIn("#promptOutput,#pmv2PromptOutput", source)
        self.assertIn("script,style,textarea,input,[contenteditable]", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
