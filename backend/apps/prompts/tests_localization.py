"""Regression checks for server-rendered multilingual prompt output."""
from django.test import SimpleTestCase, RequestFactory

from .free_surface import FREE_SURFACE_PRO_CONTRACTS
from .prompt_localization import _product_dictionary, SURFACE_TASK_TITLES, FAMILY_METHODS, STYLE_MODIFIERS, FREE_INTENTS, SOURCE_RULES, _output_label
from pathlib import Path
import json

from .prompt_localization import (
    FREE_TASK_TITLES, MESSAGES, SUPPORTED, render_localized_prompt,
    select_prompt_language,
)


class LocalizedPromptRenderingTests(SimpleTestCase):
    def test_german_canonical_prompt_is_unchanged(self):
        original = {'prompt': 'Arbeite dabei in folgender Reihenfolge: Test.', 'ready': True}
        result = render_localized_prompt(
            language='de', result=original, product='FREE', task_id='teams_notes',
            task_title='Nachbereitung formulieren', application='Teams',
            family='summarize', selections={'primary': 'Besprechungsnotizen'},
        )
        self.assertIs(result, original)

    def test_all_nine_languages_have_complete_structured_instructions(self):
        source = {'prompt': 'Deutscher Ausgangstext', 'ready': True,
                  'task_id': 'teams_notes', 'progress_percent': 100}
        for language in sorted(SUPPORTED - {'de'}):
            with self.subTest(language=language):
                result = render_localized_prompt(
                    language=language, result=source, product='FREE',
                    task_id='teams_notes', task_title='Nachbereitung formulieren',
                    application='Teams', family='summarize',
                    selections={'primary': 'Besprechungsnotizen – Originaldaten',
                                'secondary': '', 'focus': []},
                )
                self.assertEqual(result['language'], language)
                self.assertEqual(result['localization_mode'], 'structured')
                self.assertIn(FREE_TASK_TITLES['teams_notes'][language], result['prompt'])
                self.assertIn(MESSAGES[language]['output'], result['prompt'])
                self.assertIn('Besprechungsnotizen – Originaldaten', result['prompt'])
                self.assertNotIn('Arbeite dabei in folgender Reihenfolge', result['prompt'])
                self.assertNotIn('Führe abschließend diese Qualitätsprüfung', result['prompt'])
                self.assertEqual(result['progress_percent'], 100)
                self.assertEqual(result['task_id'], 'teams_notes')

    def test_pro_user_fields_are_preserved_with_native_instructions(self):
        result = render_localized_prompt(
            language='fr', result={'prompt': 'Original', 'ready': True},
            product='PRO', task_id='PM20-001', task_title='Aufgaben priorisieren',
            application='Outlook', family='analysis',
            selections={'fields': {'Fragestellung': 'Priorisiere Aufgaben Alpha und Beta'},
                        'focus': [], 'audience': ''},
        )
        self.assertIn(MESSAGES['fr']['intro'], result['prompt'])
        self.assertIn('Priorisiere Aufgaben Alpha und Beta', result['prompt'])
        self.assertIn('Contrôle qualité final', result['prompt'])
        self.assertNotIn('Original', result['prompt'])

    def test_all_sixteen_free_intents_are_localized_and_task_specific(self):
        self.assertEqual(len(FREE_INTENTS), 16)
        for task_id, variants in FREE_INTENTS.items():
            for lang in SUPPORTED - {'de'}:
                with self.subTest(task=task_id, lang=lang):
                    self.assertGreater(len(variants[lang].strip()), 45)
        example = render_localized_prompt(
            language='en',
            result={'prompt': 'German baseline', 'ready': True},
            product='FREE', task_id='teams_notes',
            task_title='Nachbereitung formulieren',
            application='Teams', family='summarize',
            selections={'primary': 'Internal minutes'},
        )
        self.assertIn('owners, dates and outstanding issues', example['prompt'])
        self.assertIn('Internal minutes', example['prompt'])
        self.assertNotIn('German baseline', example['prompt'])

    def test_pro_source_and_output_choices_are_not_dropped(self):
        result = render_localized_prompt(
            language='it', result={'prompt': 'Original', 'ready': True},
            product='PRO', task_id='PM20-006', task_title='Neue E-Mail verfassen',
            application='Outlook', family='draft',
            selections={
                'fields': {'Thema / Aussage': 'Customer delivery update'},
                'output': 'Fertige E-Mail', 'source': 'work',
                'tone': 'professional', 'detail': 'standard', 'focus': ['Kernaussage'],
            },
        )
        self.assertIn(SOURCE_RULES['work']['it'], result['prompt'])
        self.assertIn(_output_label('Fertige E-Mail', 'it'), result['prompt'])
        self.assertIn('Customer delivery update', result['prompt'])
        self.assertNotIn('Arbeite dabei in folgender Reihenfolge', result['prompt'])

    def test_all_sixteen_free_titles_are_localized(self):
        self.assertEqual(len(FREE_TASK_TITLES), 16)
        for task_id, texts in FREE_TASK_TITLES.items():
            for lang in SUPPORTED - {'de'}:
                self.assertTrue(texts[lang].strip(), f'{task_id} {lang}')

    def test_all_pro_task_titles_have_native_language_variants(self):
        data = json.loads((Path(__file__).resolve().parent
                           / 'data/pm20_golden_logic.json').read_text(encoding='utf-8'))
        catalogue = _product_dictionary()
        tasks = [task for app in data['APP'].values() for task in app['tasks']]
        self.assertEqual(len(tasks), 194)
        for task in tasks:
            for language in SUPPORTED - {'de'}:
                with self.subTest(task=task['id'], language=language):
                    self.assertTrue(catalogue.get(task['title'], {}).get(language))

    def test_all_free_surface_pro_task_titles_have_native_language_variants(self):
        catalogue = _product_dictionary()
        for task_id, entry in FREE_SURFACE_PRO_CONTRACTS.items():
            for language in SUPPORTED - {'de'}:
                with self.subTest(task=task_id, language=language):
                    title = entry['title']
                    self.assertTrue(
                        catalogue.get(title, {}).get(language)
                        or SURFACE_TASK_TITLES.get(title, {}).get(language),
                        f'No native task title: {task_id} ({language})',
                    )

    def test_all_pro_focus_choices_have_target_language_labels(self):
        from .prompt_localization import FOCUS_AUDIENCE_LABELS
        data = json.loads((Path(__file__).resolve().parent
                           / 'data/pm20_golden_logic.json').read_text(encoding='utf-8'))
        catalogue = _product_dictionary()
        labels = {value for app in data['APP'].values()
                  for task in app['tasks'] for value in task.get('focus', [])}
        self.assertGreaterEqual(len(labels), 60)
        for label in labels:
            for language in SUPPORTED - {'de'}:
                with self.subTest(label=label, language=language):
                    translation = (catalogue.get(label, {}).get(language)
                                   or FOCUS_AUDIENCE_LABELS.get(label, {}).get(language))
                    self.assertTrue(translation, f'Untranslated Pro focus choice: {label} ({language})')

    def test_all_specialized_pro_families_have_native_methodology(self):
        data = json.loads((Path(__file__).resolve().parent
                           / 'data/pm20_golden_logic.json').read_text(encoding='utf-8'))
        common = {'analysis', 'compare', 'summarize', 'draft', 'plan'}
        families = {task['family'] for app in data['APP'].values() for task in app['tasks']}
        specialized = families - common
        self.assertTrue(specialized)
        for family in specialized:
            for language in SUPPORTED - {'de'}:
                with self.subTest(family=family, language=language):
                    self.assertTrue(FAMILY_METHODS.get(family, {}).get(language))

    def test_core_microsoft_app_guardrails_are_translated(self):
        from .prompt_localization import APP_SCOPE_RULES
        for app in ('copilot_chat', 'outlook', 'teams', 'word', 'excel', 'powerpoint'):
            for language in SUPPORTED - {'de'}:
                with self.subTest(app=app, language=language):
                    self.assertTrue(APP_SCOPE_RULES[app][language].strip())
        example = render_localized_prompt(
            language='fr', result={'prompt': 'German', 'ready': True},
            product='FREE', task_id='teams_notes', task_title='Nachbereitung formulieren',
            application='Teams', family='summarize',
            selections={'primary': 'Notes de réunion'},
        )
        self.assertIn(APP_SCOPE_RULES['teams']['fr'], example['prompt'])

    def test_locale_specific_style_and_format_are_used(self):
        base = {'prompt': 'Deutscher Ausgangsprompt', 'ready': True}
        result = render_localized_prompt(
            language='en', result=base, product='FREE',
            task_id='teams_notes', task_title='Nachbereitung formulieren',
            application='Teams', family='summarize',
            selections={'primary': 'Private meeting note', 'focus': ['Kernaussagen'],
                        'output': 'meeting_notes', 'tone': 'professional',
                        'detail': 'short'},
        )
        self.assertIn('Meeting follow-up', result['prompt'])
        self.assertIn('Key points', result['prompt'])
        self.assertIn(STYLE_MODIFIERS['professional']['en'], result['prompt'])
        self.assertIn(STYLE_MODIFIERS['short']['en'], result['prompt'])

    def test_localized_field_labels_and_mixed_custom_priorities_are_retained(self):
        result = render_localized_prompt(
            language='en', result={'prompt': 'German baseline', 'ready': True},
            product='PRO', task_id='PM20-001',
            task_title='Frage fundiert beantworten',
            application='Copilot Chat', family='research',
            selections={
                'fields': {'Kontext': 'Board meeting notes'},
                'focus': ['Primärquellen', 'My special focus'],
                'audience': 'Our review team',
            },
        )
        prompt = result['prompt']
        self.assertIn('Context: «Board meeting notes»', prompt)
        self.assertIn('Primary sources', prompt)
        self.assertIn('«My special focus»', prompt)
        self.assertIn('«Our review team»', prompt)
        self.assertNotIn('German baseline', prompt)
        self.assertTrue(result['source_values_preserved'])

    def test_short_compact_pro_task_keeps_data_and_reports_truncation(self):
        base = {'prompt': 'Originaler deutscher Prompt', 'ready': True}
        ordinary = render_localized_prompt(
            language='en', result=base, product='PRO',
            task_id='PM20-171', task_title='Website aus Beschreibung erstellen',
            application='Power Pages', family='build',
            selections={'fields': {'Beschreibung': 'Blue brochure website'}},
            maximum_chars=250,
        )
        self.assertLessEqual(len(ordinary['prompt']), 250)
        self.assertIn('Blue brochure website', ordinary['prompt'])
        self.assertTrue(ordinary['source_values_preserved'])
        oversized = render_localized_prompt(
            language='en', result=base, product='PRO',
            task_id='PM20-171', task_title='Website aus Beschreibung erstellen',
            application='Power Pages', family='build',
            selections={'fields': {'Beschreibung': 'A' * 500}},
            maximum_chars=250,
        )
        self.assertLessEqual(len(oversized['prompt']), 250)
        self.assertIn('A', oversized['prompt'])
        self.assertFalse(oversized['source_values_preserved'])
        self.assertTrue(oversized['input_truncated'])
        # Truncation must never drop the output-language instruction.
        self.assertIn('response in English', ordinary['prompt'])
        self.assertIn('response in English', oversized['prompt'])
        self.assertEqual(ordinary['language'], 'en')
        self.assertEqual(oversized['language'], 'en')

    def test_cookie_and_explicit_language_selection(self):
        request = RequestFactory().post('/api/v1/prompts/free/compose/')
        request.COOKIES['promptfinisher_language'] = 'fr'
        self.assertEqual(select_prompt_language(request, {}), 'fr')
        self.assertEqual(select_prompt_language(request, {'language': 'it'}), 'it')
        self.assertEqual(select_prompt_language(request, {'language': 'en-US'}), 'en')
        with self.assertRaises(ValueError):
            select_prompt_language(request, {'language': 'xx'})
        with self.assertRaises(ValueError):
            select_prompt_language(request, {'language': 'en<script>'})
