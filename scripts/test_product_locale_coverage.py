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
        if len(html.unescape(fragment).strip()) >= 3
        and re.search(r"[A-Za-zÄÖÜäöüß]", fragment)
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

    def test_all_free_pro_modal_dialogs_are_in_live_locale_scope(self):
        source = LOCALE.read_text(encoding="utf-8")
        ui = (ROOT / "backend/static/js/promptfinisher_ui_v2.20260922.js").read_text(encoding="utf-8")
        catalogue = extract_translations()
        self.assertIn(".pmv2-workspace,.modal-backdrop", source)
        self.assertIn("roots.forEach(root => observer.observe", source)
        self.assertIn("const translateUi = key => window.PF_PRODUCT_LOCALE", ui)
        self.assertIn("translateUi(desiredContactText)", ui)
        mandatory = (
            "Funktionsvergleich & zusätzliche Anwendungen",
            "Schließen",
            "Mit CopilotPROMPTFINISHER Pro erhalten Sie zusätzliche Microsoft-Anwendungen, erweiterte Business-Prompts und professionelle Ausgabeformate.",
            "PROMPTFINISHER Pro kaufen",
            "Weitere Anwendungen mit PROMPTFINISHER Pro",
            "Microsoft-Copilot-Lizenz anfragen",
            "Nutze den erweiterten Copilot-Katalog und passe Prompts noch genauer an deinen Arbeitsbereich an.",
        )
        for key in mandatory:
            with self.subTest(key=key):
                self.assertIn(key, catalogue)
                for locale in LANGUAGES:
                    value = catalogue[key].get(locale)
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip(), f"{locale}: {key}")
        self.assertEqual(catalogue["Schließen"]["en"], "Close")
        self.assertEqual(catalogue["Funktionsvergleich & zusätzliche Anwendungen"]["en"],
                         "Feature comparison & additional applications")
        self.assertIn("id=\"generalProModal\"", (PRODUCTS / "promptfinisher_free_reference.html").read_text(encoding="utf-8"))

    def test_runtime_generated_free_paywall_and_status_labels_are_localized(self):
        source = LOCALE.read_text(encoding="utf-8")
        bridge = (ROOT / "backend/static/js/free_catalog_bridge.20260918.js").read_text(encoding="utf-8")
        catalogue = extract_translations()
        runtime_labels = (
            "Weitere PROMPTFINISHER-Pro-Funktionen für diesen Copilot-Bereich.",
            "Dieser Bereich ist im vollständigen PROMPTFINISHER-Pro-Katalog enthalten.",
            "aufgabenspezifische Prompt-Assistenten verwenden",
            "professionelle Ausgabeformate und Schwerpunkte nutzen",
            "den vollständigen, laufend weiterentwickelten Pro-Katalog verwenden",
            "Diese Anwendung",
            ": erforderliche Microsoft-Copilot-Stufe anzeigen",
            "WIRD AUS DER PROMPT-DATENBANK ERSTELLT",
            "SERVER-PRÜFUNG FEHLGESCHLAGEN",
            "Katalog konnte nicht geladen werden.",
            "Erwarteter 34-App-Katalog ist unvollständig.",
        )
        for label in runtime_labels:
            with self.subTest(label=label):
                self.assertIn(label, bridge)
                self.assertIn(label, catalogue)
                for locale in LANGUAGES:
                    translated = catalogue[label].get(locale)
                    self.assertIsInstance(translated, str)
                    self.assertTrue(translated.strip(), f"{locale}: {label}")
        self.assertEqual(catalogue["PROMPT BEREIT"]["en"], "PROMPT READY")
        self.assertIn("element.matches('[data-licenselocked=\"1\"]')", source)
        self.assertIn("appName + t(': erforderliche Microsoft-Copilot-Stufe anzeigen')", source)

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
