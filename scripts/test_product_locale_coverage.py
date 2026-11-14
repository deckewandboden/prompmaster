#!/usr/bin/env python3
"""Static UI-text completeness contract for protected Free/Pro V2 sources.

The Golden Master bytes remain untouched. This checks the runtime translation
catalogue that V2 injects next to them, for every language in use.
"""
import html
import json
import re
import subprocess
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
    def test_known_english_language_leaks_are_corrected(self):
        translations = extract_translations()
        expected = {
            ('Dateien zusammenfassen, vergleichen und als Entscheidungsgrundlage nutzen', 'tr'): 'Dosyaları özetleyin, karşılaştırın ve kararlar için dayanak olarak kullanın',
            ('Daten analysieren, Trends erkennen, Formeln erklären und Szenarien vergleichen.', 'tr'): 'Verileri analiz edin, eğilimleri belirleyin, formülleri açıklayın ve senaryoları karşılaştırın.',
            ('E-Mail-Verlauf analysieren', 'tr'): 'E-posta yazışmalarını analiz et',
            ('Präsentationen zusammenfassen, verbessern und ergänzen', 'tr'): 'Sunumları özetleyin, iyileştirin ve tamamlayın',
            ('Terminlage, Engpässe und alternative Zeitfenster bewerten.', 'tr'): 'Tarihleri, darboğazları ve alternatif zaman aralıklarını değerlendirin.',
            ('Webseiten, PDFs und Browserkontext mit Copilot analysieren', 'tr'): "Web sitelerini, PDF'leri ve tarayıcı bağlamını Copilot ile analiz edin",
            ('Agent-Instructions erstellen', 'tr'): 'Ajan talimatları oluştur',
            ('Chat oder Kanal zusammenfassen', 'tr'): 'Sohbeti veya kanalı özetle',
            ('Copilot-Adoption analysieren', 'tr'): "Copilot'un benimsenmesini analiz et",
            ('Incident analysieren', 'tr'): 'Olayı analiz et',
            ('Kundenverhalten analysieren', 'tr'): 'Müşteri davranışını analiz et',
            ('Ressourceninventar analysieren', 'tr'): 'Kaynak envanterini analiz et',
            ('SharePoint-Inhalte zusammenfassen', 'tr'): 'SharePoint içeriklerini özetle',
            ('Webseite oder PDF zusammenfassen', 'tr'): "Web sayfasını veya PDF'yi özetle",
            ('Chat oder Kanal zusammenfassen', 'it'): 'Riassumi la chat o il canale',
            ('Webseite oder PDF zusammenfassen', 'it'): 'Riassumi il sito web o il PDF',
            ('Chat oder Kanal zusammenfassen', 'es'): 'Resumir el chat o el canal',
            ('Dateien vergleichen', 'es'): 'Comparar archivos',
            ('Mehrere Tabs vergleichen', 'es'): 'Comparar varias pestañas',
            ('Webseite oder PDF zusammenfassen', 'es'): 'Resumir el sitio web o el PDF',
        }
        for (source, language), correct in expected.items():
            with self.subTest(source=source, language=language):
                self.assertEqual(translations[source][language], correct)
        self.assertEqual(len(expected), 20)
        english_leak = re.compile(r'\b(?:Summarize|Analyze|Evaluate|Create)\b', flags=re.IGNORECASE)
        for source, variants in translations.items():
            value = variants.get('tr')
            if value:
                # Identifiers and placeholder names are not translated as prose.
                pure_ui = re.sub(r'%\([a-z]+\)s', '', value)
                with self.subTest(source=source, language='tr'):
                    self.assertIsNone(english_leak.search(pure_ui), source)

    def test_shared_backend_controls_cover_all_supported_languages(self):
        # Evaluate the shipped JavaScript catalogue, including ARIA labels.
        source = (ROOT / 'backend/static/js/app.js').read_text(encoding='utf-8')
        prefix = source.split('  const text = translations[language]', 1)[0]
        program = "const document = {documentElement: {lang: 'fr'}};\n" + prefix
        program += "\nconsole.log(JSON.stringify(Object.fromEntries(Object.entries(translations).map(([lang, terms]) => [lang, Object.fromEntries(Object.entries(terms).map(([key, value]) => [key, typeof value === 'function' ? value('QA_COLUMN') : value]))]))));\n})();"
        result = subprocess.run(['node', '-e', program], check=True, capture_output=True, text=True)
        catalogues = json.loads(result.stdout)
        for language in ('de',) + LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(set(catalogues[language]), set(catalogues['de']))
                self.assertTrue(all(catalogues[language].values()))
                for key in ('sortAria', 'sortAscAria', 'sortDescAria'):
                    self.assertIn('QA_COLUMN', catalogues[language][key])
                if language != 'de':
                    for key in catalogues['de']:
                        self.assertNotEqual(catalogues[language][key], catalogues['de'][key])

    def test_production_v2_labels_and_rebranded_legal_notice(self):
        translated = extract_translations()
        keys = ['Strukturierten Bericht erstellen', 'Aus Dokumentinhalten einen klar gegliederten Bericht erzeugen.', 'Risiken und Lücken analysieren', 'Unklare Angaben, Widersprüche und Risiken erkennen.', 'Beispiel: Für eine Geschäftsleitung kürzer, klarer und ohne technische Detailtiefe.', 'Optional. Ohne Zusatzangabe verbessert Copilot Sprache und Struktur des aktuellen Textes.', 'Zum Beispiel Zahlen, Namen, Termine oder fachliche Pflichtaussagen.', 'Optional. Kritische Fakten dürfen nicht verändert werden.', 'PROMPTFINISHER Pro erweitert Apps, Rollen und Business-Prompts. Microsoft 365 Copilot wird separat lizenziert.'] + ['Aktuell ausgewählt: %(tier)s.', 'Erforderlich für %(app)s: %(tier)s.', '%(tier)s auswählen', '%(tier)s anfragen', 'Für %(app)s benötigt PROMPTFINISHER in dieser Konfiguration mindestens %(tier)s.', '28 weitere Pro-Bereiche anzeigen ▾',
                '28 weitere Pro-Bereiche ausblenden ▴',
                'Fortschritt der Prompt-Konfiguration',
                'Ausgewählt', 'Informationen vergleichen', 'Management-Briefing', 'Unterschiede, Gemeinsamkeiten und Entscheidungspunkte herausarbeiten.', 'Kernaussagen, Risiken und nächste Schritte für Entscheider.', 'Stichpunkte', 'Fließtext', 'Beispiel: Die wichtigsten Aussagen, Entscheidungen und nächsten Schritte kompakt zusammenfassen.', 'Beschreiben Sie kurz, was die Zusammenfassung für Sie leisten soll.', 'Fügen Sie hier Text, Notizen oder Informationen ein. Alternativ stellen Sie den Inhalt später im Copilot-Chat bereit.', 'Optional. Ohne Inhalt hier muss die Quelle beim Einfügen des fertigen Prompts in Copilot bereitgestellt oder eindeutig referenziert werden.', 'Offene Fragen', 'Offene Fragen · PRO', 'Termine', 'Termine · PRO', 'Zahlen / Fakten', 'Zahlen / Fakten · PRO']
        keys += [key.replace('CopilotPROMPTFINISHER', 'PROMPTFINISHER')
                 for key in translated
                 if key.startswith('Microsoft, Microsoft 365 und Copilot sind Marken')
                 and 'CopilotPROMPTFINISHER' in key]
        for key in keys:
            for language in LANGUAGES:
                with self.subTest(key=key, language=language):
                    self.assertTrue(translated.get(key, {}).get(language))
                    self.assertNotEqual(translated[key][language], key)

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

    def test_prompt_terms_and_browser_text_are_semantically_safe(self):
        """Protect official prompt terminology and literal browser text in ten locales."""
        catalogue = extract_translations()
        marketing_line = {
            "en": "Better prompts · better results",
            "es": "Mejores prompts · mejores resultados",
            "pt": "Melhores prompts · melhores resultados",
            "tr": "Daha iyi promptlar · daha iyi sonuçlar",
            "ru": "Лучшие промпты · лучшие результаты",
            "pl": "Lepsze prompty · lepsze wyniki",
            "fr": "De meilleurs prompts · de meilleurs résultats",
            "it": "Prompt migliori · risultati migliori",
            "nl": "Betere prompts · betere resultaten",
        }
        for locale, phrase in marketing_line.items():
            with self.subTest(locale=locale):
                self.assertEqual(catalogue["Bessere Prompts · bessere Ergebnisse"][locale], phrase)
                self.assertEqual(
                    catalogue["PRO · Bessere Prompts · bessere Ergebnisse"][locale],
                    "PRO · " + phrase,
                )
                self.assertEqual(
                    catalogue["AI Builder – Prompt Builder"][locale],
                    "AI Builder – Prompt Builder",
                )
                self.assertIn("Dataverse", catalogue["Dataverse-grounded Prompt erstellen"][locale])
                self.assertIn("Promptbook", catalogue["Promptbook entwerfen"][locale])
        ready_status = {
            "en": "PROMPT READY", "es": "PROMPT LISTO",
            "pt": "PROMPT PRONTO", "tr": "PROMPT HAZIR",
            "ru": "ПРОМПТ ГОТОВ", "pl": "PROMPT GOTOWY",
            "fr": "PROMPT PRÊT", "it": "PROMPT PRONTO",
            "nl": "PROMPT GEREED",
        }
        for locale, expected in ready_status.items():
            with self.subTest(locale=locale, key="PROMPT BEREIT"):
                self.assertEqual(catalogue["PROMPT BEREIT"][locale], expected)
                self.assertEqual(catalogue["Prompt Builder"][locale], "Prompt Builder")
                for key in (
                    "Ihr fertiger Prompt",
                    "App-spezifische Business-Prompts",
                    "Custom Prompt erstellen",
                    "Prompt-Abnahmetest erstellen",
                ):
                    translated = catalogue[key][locale].lower()
                    if locale == "ru":
                        self.assertTrue(
                            "промпт" in translated or "prompt" in translated,
                            f"{locale} {key}: {translated}",
                        )
                    else:
                        self.assertIn("prompt", translated, f"{locale} {key}: {translated}")
        for locale in ("tr", "ru", "pl", "fr", "it"):
            with self.subTest(locale=locale, key="Pro hero summary"):
                source = (
                    "34 Copilot-Bereiche, präzise Aufgabenführung und professionelle "
                    "Ausgabeformate – für Prompts, die im Arbeitsalltag sofort weiterhelfen."
                )
                summary = catalogue[source][locale].lower()
                self.assertTrue(
                    ("промпт" in summary) if locale == "ru" else ("prompt" in summary),
                    f"{locale}: the Pro summary must not omit prompt purpose",
                )
        for key, locale_map in catalogue.items():
            for locale, value in locale_map.items():
                with self.subTest(key=key[:45], locale=locale):
                    self.assertNotRegex(value, r"&(?:amp|lt|gt|quot|nbsp|#\d+);")


    def test_postmerge_terminology_and_speaker_notes_are_semantically_correct(self):
        """Catch misleading product terms that completeness checks cannot detect.

        'Solution' means a business/software solution, not a chemical
        solution. Speaker notes belong to a presenter, not loudspeakers.
        """
        catalog = extract_translations()
        expected = {
            ("Entscheidung", "tr"): "Karar",
            ("Solution", "tr"): "Çözüm",
            ("Solution", "pl"): "Rozwiązanie",
            ("Sprecherhinweise erstellen", "es"): "Crear notas del presentador",
            ("Sprecherhinweise erstellen", "pl"): "Tworzenie notatek prelegenta",
            ("Sprecherhinweise erstellen", "it"): "Creare note del relatore",
        }
        for (term, locale), target in expected.items():
            with self.subTest(term=term, locale=locale):
                self.assertEqual(catalog[term][locale], target)
        for locale, wrong_term in (
            ("es", "altavoces"),
            ("pl", "głośników"),
            ("it", "altoparlanti"),
        ):
            self.assertNotIn(
                wrong_term,
                catalog["Sprecherhinweise erstellen"][locale].lower(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
