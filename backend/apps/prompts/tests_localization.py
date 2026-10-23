"""Regression checks for server-rendered multilingual prompt output."""
from django.test import SimpleTestCase, RequestFactory

from .free_surface import FREE_SURFACE_PRO_CONTRACTS
from .prompt_localization import _product_dictionary, SURFACE_TASK_TITLES, FAMILY_METHODS, STYLE_MODIFIERS
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
