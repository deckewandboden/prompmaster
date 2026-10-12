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
    'ns_admin/api.html',
    'ns_admin/ops.html',
    'ns_admin/ops_services.html',
    'ns_admin/mollie.html',
    'ns_admin/email.html',
    'ns_admin/customer_detail.html',
    'ns_admin/private_customer_detail.html',
    'ns_admin/customer_company.html',
    'ns_admin/customer_privacy.html',
    'ns_admin/order_detail.html',
    'ns_admin/license_detail.html',
    'ns_admin/email_log.html',
    'ns_admin/includes_customer_nav.html',
    'ns_admin/includes_private_customer_nav.html',
    'ns_admin/customer_grid.html',
    'ns_admin/private_customer_grid.html',
    'ns_admin/mollie_events.html',
    'ns_admin/legal_deletions.html',
    'ns_admin/legal_retention.html',
    'ns_admin/legal_documents.html',
    'ns_admin/ops_database.html',
    'ns_admin/ops_grid.html',
    'ns_admin/support_detail.html',
    'ns_admin/base.html',
    'ns_admin/content/faq_edit.html',
    'ns_admin/content/faq_list.html',
    'ns_admin/service_account_token.html',
    'ns_admin/product_edit.html',
    'ns_admin/settings.html',
    'ns_admin/prompt_studio/definition_detail.html',
    'ns_admin/prompt_studio/index.html',
    'ns_admin/prompt_studio/quality.html',
    'ns_admin/prompt_studio/quality_policy.html',
    'ns_admin/prompt_studio/testcase_edit.html',
    'ns_admin/prompt_studio/version_edit.html',
    'ns_admin/prompt_studio/version_detail.html',
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

    def test_mollie_live_checkout_and_service_account_warnings_are_translated(self):
        cases = (
            ('ns_admin/mollie.html', 'Produktiv-Checkout sperren'),
            ('ns_admin/mollie.html', 'Notabschaltung'),
            ('ns_admin/mollie.html', 'Live-Zugangsdaten sind hinterlegt, der Kunden-Checkout bleibt jedoch gesperrt, bis die Live-Readiness geprüft und ausdrücklich freigegeben wurde.'),
            ('ns_admin/api.html', 'Service Account wirklich sperren?'),
            ('ns_admin/api.html', 'Token rotieren'),
        )
        for page, phrase in cases:
            source = (ROOT / 'templates' / page).read_text(encoding='utf-8')
            with self.subTest(page=page, phrase=phrase):
                self.assertIn(phrase, source)
                for locale in LOCALES:
                    terms = catalog_translations(ROOT / 'locale' / locale / 'LC_MESSAGES' / 'django.po')
                    self.assertTrue(terms.get(phrase), 'Dangerous operations must never show untranslated confirmations')

    def test_mail_failover_critical_texts_are_translated(self):
        source = (ROOT / 'templates/ns_admin/email.html').read_text(encoding='utf-8')
        terms = (
            'Automatischer Fallback erfolgt nur bei eindeutig nicht zugestellten Fehlern. Bei unklaren Fehlern wird nicht automatisch weitergeschaltet, damit dieselbe E-Mail nicht versehentlich doppelt versendet wird.',
            'SPF/DKIM/DMARC werden unter „Einstellungen“ als DNS-Sollwerte dokumentiert. Änderungen dort aktualisieren nicht automatisch den öffentlichen DNS.',
            'Passwort fehlt',
            'Nicht konfiguriert',
        )
        for term in terms:
            self.assertIn(term, source)
            for code in LOCALES:
                catalog = catalog_translations(ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po')
                with self.subTest(language=code, term=term):
                    self.assertTrue(catalog.get(term), 'Email safety notice must be localized')

    def test_license_and_refund_confirmation_dialogs_are_localized(self):
        source = (ROOT / 'templates/ns_admin/license_detail.html').read_text(encoding='utf-8')
        critical = (
            'Lizenzstatus wirklich ändern?',
            'Lizenzzuweisung wirklich freigeben? Aktive Geräte dieser Lizenz werden widerrufen.',
            'Erstattung wirklich verbindlich über Mollie auslösen?',
        )
        for phrase in critical:
            self.assertIn("data-confirm=\"{% translate '" + phrase + "' %}\"", source)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(locale=code, phrase=phrase):
                    self.assertTrue(translations.get(phrase))

    def test_email_log_statuses_have_translations(self):
        source = (ROOT / 'templates/ns_admin/email_log.html').read_text(encoding='utf-8')
        for phrase in ('Gesendet', 'Fehlgeschlagen', 'Wird gesendet', 'Unterdrückt', 'Warteschlange'):
            self.assertIn("{% translate '" + phrase + "' %}", source)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(locale=code, status=phrase):
                    self.assertTrue(translations.get(phrase))

    def test_customer_grids_protect_device_revocation_and_user_disable_prompts(self):
        paths = ('ns_admin/customer_grid.html', 'ns_admin/private_customer_grid.html')
        messages = (
            'Benutzer wirklich deaktivieren? Lizenzen und Gerätezugänge werden freigegeben.',
            'Gerätezugang wirklich widerrufen?',
        )
        for path in paths:
            source = (ROOT / 'templates' / path).read_text(encoding='utf-8')
            self.assertIn("{% translate title %}", source)
            self.assertIn("{% translate 'Aktion' %}", source)
            self.assertIn(
                "data-confirm=\"{% translate 'Gerätezugang wirklich widerrufen?' %}\"",
                source,
            )
            if path.endswith('/customer_grid.html'):
                self.assertIn(
                    "data-confirm=\"{% translate 'Benutzer wirklich deaktivieren? Lizenzen und Gerätezugänge werden freigegeben.' %}\"",
                    source,
                )
        for code in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for phrase in messages:
                with self.subTest(language=code, message=phrase):
                    self.assertTrue(catalog.get(phrase))

    def test_customer_navigation_has_localized_accessible_labels(self):
        for page, label in (
            ('ns_admin/includes_customer_nav.html', 'Kundenbereiche'),
            ('ns_admin/includes_private_customer_nav.html', 'Privatkundenbereiche'),
        ):
            source = (ROOT / 'templates' / page).read_text(encoding='utf-8')
            self.assertIn("aria-label=\"{% translate '" + label + "' %}\"", source)
            self.assertIn("{% translate 'Übersicht' %}", source)
            for code in LOCALES:
                catalog = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(page=page, language=code):
                    self.assertTrue(catalog.get(label))

    def test_gdpr_anonymization_confirmation_is_translated(self):
        source = (ROOT / 'templates/ns_admin/legal_deletions.html').read_text(encoding='utf-8')
        phrase = 'Konto wirklich anonymisieren?'
        self.assertIn("data-confirm=\"{% translate '" + phrase + "' %}\"", source)
        for code in LOCALES:
            translations = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            with self.subTest(language=code):
                self.assertTrue(translations.get(phrase))

    def test_support_reply_and_email_statuses_are_localized(self):
        source = (ROOT / 'templates/ns_admin/support_detail.html').read_text(encoding='utf-8')
        for phrase in (
            'Antwort senden', 'Antwort an den Kunden eingeben …',
            'Gesendet', 'Fehlgeschlagen', 'Wird gesendet', 'Warteschlange',
        ):
            self.assertIn("{% translate '" + phrase + "' %}", source)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(language=code, phrase=phrase):
                    self.assertTrue(translations.get(phrase))

    def test_one_time_service_token_warnings_are_localized(self):
        source = (ROOT / 'templates/ns_admin/service_account_token.html').read_text(encoding='utf-8')
        phrases = (
            'Token jetzt sicher speichern.',
            'Er wird danach nicht erneut im Klartext angezeigt; ein alter Token ist nach einer Rotation sofort ungültig.',
            'Zur API-Verwaltung',
        )
        self.assertIn('{{ token }}', source)
        for phrase in phrases:
            self.assertIn("{% translate '" + phrase + "' %}", source)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(locale=code, phrase=phrase):
                    self.assertTrue(translations.get(phrase))

    def test_settings_privacy_and_failover_warnings_are_localized(self):
        source = (ROOT / 'templates/ns_admin/settings.html').read_text(encoding='utf-8')
        critical = (
            'Alle Provider bleiben parallel gespeichert. Im manuellen Modus wird nur der primäre Versandweg verwendet. Im automatischen Modus wird bei eindeutig nicht zugestellten Fehlern in der festgelegten Reihenfolge weitergeschaltet; bei unklaren Fehlern erfolgt bewusst kein automatischer Fallback, um Doppelversand zu vermeiden.',
            'Die Absenderadresse wird beim SMTP-Versand direkt aus diesen Einstellungen gelesen. SPF, DKIM und DMARC sind hier als DNS-Sollwerte dokumentiert; das Speichern verändert keine DNS-Zone.',
            'Erster SMTP-Transport. Das Passwort wird verschlüsselt gespeichert und niemals wieder im Klartext angezeigt.',
            'Alternative zu SMTP für Exchange Online. Das Client Secret wird verschlüsselt gespeichert und niemals wieder im Klartext angezeigt.',
            'Sie besitzen Leserechte, aber keine Berechtigung zum Ändern dieser Einstellungen.',
        )
        for phrase in critical:
            self.assertIn("{% translate '" + phrase + "' %}", source)
            for code in LOCALES:
                locale = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                with self.subTest(language=code, phrase=phrase):
                    self.assertTrue(locale.get(phrase))

    def test_prompt_studio_version_detail_localizes_release_actions_and_labels(self):
        source = (ROOT / 'templates/ns_admin/prompt_studio/version_detail.html').read_text(encoding='utf-8')
        self.assertIn("{% load i18n %}", source)
        for label in (
            'Versionen', 'Archivieren', 'Testfälle', 'Alle Tests ausführen',
            'Löschen', 'Prompt testen', 'Noch kein Testfall. Vor Übergang zu TEST muss mindestens einer angelegt werden.',
        ):
            self.assertIn("{% translate '" + label + "' %}", source)
            for code in LOCALES:
                translations = catalog_translations(
                    ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                )
                self.assertTrue(translations.get(label))
        self.assertIn("{% translate 'Deterministischer Feld-Fallback' as context_fallback %}", source)
        self.assertIn("|default:context_fallback", source)
        self.assertIn('data-label="{% translate \'Name\' %}"', source)

    def test_ops_dashboard_has_full_static_and_status_i18n_coverage(self):
        source = (ROOT / 'templates/ns_admin/ops.html').read_text(encoding='utf-8')
        self.assertIn("{% load pm i18n %}", source)
        labels = (
            'System & Betrieb', 'Aktive Warnungen', 'Dateiobjekte (Inodes) verfügbar',
            'Betriebszustand, Plattformdienste, Integrationen und Datensicherung.',
            'Inodes sind Dateisystem-Einträge für Dateien und Verzeichnisse. Sind sie ausgeschöpft, können trotz freiem Speicher keine neuen Dateien angelegt werden.',
            'Diese Werte stammen aus cAdvisor und beziehen sich auf Docker-Container. Die VM-Werte oben stammen aus node_exporter und beziehen sich auf die gesamte Docker-Host-VM.',
            'Letztes Backup', 'Letzter Restore-Test', 'nicht erreichbar',
            'nicht protokolliert', 'Heartbeat fehlt', 'konfiguriert',
        )
        for label in labels:
            with self.subTest(label=label):
                self.assertIn("{% translate '" + label + "' %}", source)
                for code in LOCALES:
                    translations = catalog_translations(
                        ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
                    )
                    self.assertTrue(translations.get(label))
        for runtime_name in (
            'database.status', 'certificate.status', 'integrations.mcp.status',
            'latest_backup.status', 'latest_restore.status', 'a.severity',
        ):
            self.assertIn('{% translate ' + runtime_name + ' %}', source)
        self.assertIn("{% translate 'nicht gesetzt' as ops_unset_label %}", source)
        self.assertIn('|default:ops_unset_label', source)
        self.assertIn("{% if certificate.status %}{% translate certificate.status %}{% else %}–{% endif %}", source)
        self.assertEqual(source.count("|date:'SHORT_DATETIME_FORMAT'"), 2)
        self.assertNotIn("|date:'d.m.Y H:i'", source)

    def test_ops_runtime_codes_are_available_in_all_languages(self):
        codes = (
            'not_configured', 'unknown', 'ok', 'warning', 'unavailable',
            'degraded', 'success', 'failed', 'running', 'critical',
            'passed', 'error', 'skipped', 'in_progress', 'no_data', 'completed',
        )
        for code in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for status_code in codes:
                with self.subTest(locale=code, status=status_code):
                    self.assertTrue(catalog.get(status_code))

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
