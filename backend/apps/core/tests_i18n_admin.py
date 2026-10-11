"""Regression contracts for the admin's multilingual UI and stable header layout.

This audits the entire dashboard and customer preview instead of only side
navigation. Other admin modules remain separately tracked for i18n coverage.
"""
from pathlib import Path
import re

from django.template.loader import get_template
from django.test import SimpleTestCase
from django.conf import settings

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ('en', 'es', 'pt', 'tr', 'ru')
PAGES = (
    'ns_admin/dashboard.html',
    'ns_admin/customer_portal_preview.html',
)
TRANSLATE_PATTERN = re.compile(r'{%\\s*translate\\s+([\\'"])(.*?)\\1\\s*%}')


class AdminInternationalizationContractTests(SimpleTestCase):
    def test_six_user_languages_are_offered(self):
        self.assertEqual(
            {code for code, _ in settings.LANGUAGES},
            {'de', 'en', 'es', 'pt', 'tr', 'ru'},
        )

    def test_all_dashboard_and_preview_labels_have_five_real_translations(self):
        keys = set()
        for page in PAGES:
            path = ROOT / 'templates' / page
            source = path.read_text(encoding='utf-8')
            keys.update(match.group(2) for match in TRANSLATE_PATTERN.finditer(source))
            get_template(page)  # Django parser must accept all our tags
        self.assertGreaterEqual(len(keys), 110)
        for code in LOCALES:
            po = (ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po').read_text(encoding='utf-8')
            for key in sorted(keys):
                escaped = key.replace('\\', '\\\\').replace('"', '\\"')
                pattern = re.escape('msgid "' + escaped + '"') + r'\\nmsgstr "(?!")'
                with self.subTest(language=code, label=key):
                    self.assertRegex(po, pattern)

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
