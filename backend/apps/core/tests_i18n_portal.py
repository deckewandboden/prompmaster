"""Fail-closed locale coverage of all customer portal templates.

The customer portal uses Django gettext, not the separate Free/Pro JS dictionary.
Do not accept correct navigation with untranslated dynamic license/payment/team
labels. Keep protected legal document *bodies* outside this UI acceptance gate.
"""
from pathlib import Path
import re
from types import SimpleNamespace

from django.template import Context, Template
from django.template.loader import get_template
from django.test import SimpleTestCase
from django.utils.translation import override

from apps.core.tests_i18n_admin import LOCALES, catalog_translations

ROOT = Path(__file__).resolve().parents[2]
PORTAL_PAGES = (
    'portal/assignment_link_claim.html',
    'portal/assignment_link_created.html',
    'portal/base.html',
    'portal/buy.html',
    'portal/company.html',
    'portal/dashboard.html',
    'portal/devices.html',
    'portal/form.html',
    'portal/help.html',
    'portal/invitations.html',
    'portal/license_detail.html',
    'portal/licenses.html',
    'portal/more.html',
    'portal/orders.html',
    'portal/profile.html',
    'portal/renew.html',
    'portal/renew_index.html',
    'portal/search.html',
    'portal/security.html',
    'portal/support_detail.html',
    'portal/team.html',
    'portal/team_member.html',
)
LITERAL_TRANSLATE = re.compile(r"""{%\s*translate\s+(['"])(.*?)\1\s*%}""")
UNTRANSLATED_DISPLAY = re.compile(
    r"\{\{\s*[\w.]+\.get_(?:role|status|category|kind|source|priority|"
    r"sender_type|cancellation_kind)_display\s*\}\}"
)


class PortalInternationalizationContractTests(SimpleTestCase):
    def test_all_portal_pages_are_part_of_the_locale_matrix(self):
        actual = {
            'portal/' + item.name
            for item in (ROOT / 'templates' / 'portal').glob('*.html')
        }
        self.assertEqual(set(PORTAL_PAGES), actual)
        self.assertEqual(len(actual), 22)

    def test_all_portal_template_labels_have_translations_in_nine_locales(self):
        keys = set()
        for page in PORTAL_PAGES:
            path = ROOT / 'templates' / page
            markup = path.read_text(encoding='utf-8')
            get_template(page)  # All page tags and variable translates must compile.
            keys.update(m.group(2) for m in LITERAL_TRANSLATE.finditer(markup))
        self.assertGreaterEqual(len(keys), 60)
        for locale in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / locale / 'LC_MESSAGES' / 'django.po'
            )
            for key in keys:
                with self.subTest(locale=locale, page_label=key):
                    self.assertTrue(
                        catalog.get(key),
                        f'Missing customer portal translation for {locale}: {key!r}',
                    )

    def test_portal_model_choice_display_never_falls_back_to_german(self):
        for page in PORTAL_PAGES:
            markup = (ROOT / 'templates' / page).read_text(encoding='utf-8')
            with self.subTest(page=page):
                self.assertNotRegex(
                    markup, UNTRANSLATED_DISPLAY,
                    'Model choice text needs {% translate variable.get_status_display %}',
                )
        profile = (ROOT / 'templates/portal/profile.html').read_text(encoding='utf-8')
        self.assertIn(
            '{% translate pending_deletion.get_status_display as translated_deletion_status %}',
            profile,
        )
        self.assertIn('status=translated_deletion_status', profile)
        dashboard = (ROOT / 'templates/portal/dashboard.html').read_text(encoding='utf-8')
        self.assertIn('{% translate payment.get_status_display %}', dashboard)
        self.assertNotIn('{{ payment.status }}', dashboard)

    def test_critical_customer_choice_values_resolve_at_render_time(self):
        sources = (
            'Firmenadministrator', 'Mitarbeiter',
            'Aktiv', 'Frei', 'Zahlung offen', 'Neu',
            'In Bearbeitung', 'Abgeschlossen', 'Abgelehnt',
            'Offen', 'Bezahlt', 'Fehlgeschlagen', 'Storniert',
            'Zahlung prüfen', 'Gesperrt', 'Teilweise erstattet',
        )
        renderer = Template('{% load i18n %}{% translate row.get_status_display %}')
        for locale in LOCALES:
            translations = catalog_translations(
                ROOT / 'locale' / locale / 'LC_MESSAGES' / 'django.po'
            )
            with override(locale):
                for key in sources:
                    with self.subTest(locale=locale, status=key):
                        self.assertTrue(translations.get(key))
                        sample = SimpleNamespace(get_status_display=lambda source=key: source)
                        self.assertEqual(
                            renderer.render(Context({'row': sample})),
                            translations[key],
                        )

    def test_dutch_license_terms_use_software_license_vocabulary(self):
        catalog = catalog_translations(
            ROOT / 'locale/nl/LC_MESSAGES/django.po'
        )
        self.assertEqual(catalog['Lizenzen nach Produkt'], 'Licenties per product')
        self.assertEqual(catalog['Lizenzen'], 'Licenties')
        self.assertEqual(catalog['Lizenzstatus'], 'Licentiestatus')
