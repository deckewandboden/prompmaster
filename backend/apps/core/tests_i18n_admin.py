"""Regression contracts for the admin's multilingual UI and stable header layout.

This audits the entire dashboard and customer preview instead of only side
navigation. Other admin modules remain separately tracked for i18n coverage.
"""
from pathlib import Path
from ast import literal_eval
import re

from django.template.loader import get_template
from django.test import SimpleTestCase
from django.conf import settings

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ('en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl')
PAGES = (
    'ns_admin/dashboard.html',
    'ns_admin/customer_portal_preview.html',
    'ns_admin/grid.html',
    'ns_admin/form.html',
    'ns_admin/stats.html',
    'ns_admin/support.html',
    'ns_admin/search.html',
    'ns_admin/audit.html',
    'ns_admin/payments.html',
    'ns_admin/products.html',
    'ns_admin/features.html',
    'ns_admin/roles.html',
    'ns_admin/legal.html',
)
TRANSLATE_PATTERN = re.compile(r'''{%\s*translate\s+(['"])(.*?)\1\s*%}''')


PLACEHOLDER_PATTERN = re.compile(r'%\(([A-Za-z_][A-Za-z_0-9]*)\)[a-zA-Z]')


def catalog_translations(path: Path) -> dict[str, str]:
    """Read gettext PO continuations, not just single-line msgid/msgstr pairs."""
    entries = {}
    source = None
    target = ''
    section = None

    def commit():
        if source:
            if source in entries:
                raise AssertionError('Duplicate gettext key: ' + source)
            entries[source] = target

    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('msgid '):
            commit()
            source = literal_eval(line[len('msgid '):])
            target = ''
            section = 'source'
        elif line.startswith('msgstr '):
            target = literal_eval(line[len('msgstr '):])
            section = 'target'
        elif line.startswith('"') and section:
            value = literal_eval(line)
            if section == 'source':
                source += value
            else:
                target += value
    commit()
    return entries



class AdminInternationalizationContractTests(SimpleTestCase):
    def test_ten_user_languages_are_offered(self):
        self.assertEqual(
            {code for code, _ in settings.LANGUAGES},
            {'de', 'en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl'},
        )

    def test_admin_primary_pages_have_nine_real_translations(self):
        keys = set()
        for page in PAGES:
            path = ROOT / 'templates' / page
            source = path.read_text(encoding='utf-8')
            keys.update(match.group(2) for match in TRANSLATE_PATTERN.finditer(source))
            get_template(page)  # Django parser must accept all our tags
        self.assertGreaterEqual(len(keys), 195)
        for code in LOCALES:
            translations = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for key in sorted(keys):
                with self.subTest(language=code, label=key):
                    self.assertIn(key, translations)
                    self.assertTrue(translations[key])

    def test_all_locale_format_placeholders_are_preserved(self):
        for code in LOCALES:
            translations = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for key, target in translations.items():
                expected = sorted(PLACEHOLDER_PATTERN.findall(key))
                actual = sorted(PLACEHOLDER_PATTERN.findall(target))
                with self.subTest(language=code, label=key):
                    self.assertEqual(expected, actual,
                        'Named interpolation placeholders must never be translated.')

    def test_shared_admin_templates_use_runtime_translation_for_dynamic_grid_columns(self):
        grid = (ROOT / 'templates/ns_admin/grid.html').read_text(encoding='utf-8')
        for token in (
            "{% translate label %}",
            'data-label="{% translate label %}"',
            "{% translate 'aufsteigend' %}",
            "{% translate 'absteigend' %}",
            "{% translate title %}",
            "{% translate primary_action_label %}",
        ):
            self.assertIn(token, grid, 'Shared grid must localize visible table metadata')

    def test_dynamic_admin_grid_headers_resolve_in_every_locale(self):
        source = (ROOT / 'apps/core/admin_views.py').read_text(encoding='utf-8')
        blocks = re.findall(r"'columns':\s*\[([\s\S]*?)\]", source)
        labels = set()
        for block in blocks:
            labels.update(re.findall(
                r"\(\s*'[^']+'\s*,\s*'([^']+)'\s*,\s*'[^']+'\s*\)",
                block,
            ))
        self.assertGreaterEqual(len(labels), 20)
        for code in LOCALES:
            translations = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for label in labels:
                with self.subTest(language=code, column=label):
                    self.assertTrue(translations.get(label),
                                    'Dynamic admin grid headings must be translated')

    def test_admin_security_confirmations_are_translated(self):
        role_html = (ROOT / 'templates/ns_admin/roles.html').read_text(encoding='utf-8')
        for source_text in (
            '2FA dieses Benutzers zurücksetzen?',
            'Benutzerstatus wirklich ändern?',
        ):
            self.assertIn("data-confirm=\"{% translate '" + source_text + "' %}\"", role_html)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(language=code, text=source_text):
                    self.assertTrue(translations.get(source_text))

    def test_language_picker_is_in_flex_header_and_never_overlays_avatar(self):
        shell = (ROOT / 'templates/app_shell.html').read_text(encoding='utf-8')
        base = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
        css = (ROOT / 'static/css/app.css').read_text(encoding='utf-8')
        self.assertIn('topbar-locale', shell)
        self.assertIn("{% block language_picker %}", base)
        self.assertIn("width:154px", css)
        self.assertIn("flex:0 0 154px", css)
        self.assertNotIn('position:fixed', css.split('.language-switcher{', 1)[1].split('}', 1)[0])

    def test_customer_preview_is_read_only_and_staff_edit_links_are_gated(self):
        source = (ROOT / 'templates/ns_admin/customer_portal_preview.html').read_text(encoding='utf-8')
        self.assertIn('preview_is_company_admin', source)
        self.assertIn('preview_can_write_customer', source)
        self.assertIn('preview_selectable_members', source)
        self.assertNotIn('method="post"', source)
        self.assertNotIn('force_login', source)
