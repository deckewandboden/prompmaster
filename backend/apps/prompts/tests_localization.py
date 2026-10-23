"""Regression checks for server-rendered multilingual prompt output."""
from django.test import SimpleTestCase, RequestFactory

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
