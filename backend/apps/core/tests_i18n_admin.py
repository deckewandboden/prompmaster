"""Regression contracts for the admin's multilingual UI and stable header layout.

This audits the entire dashboard and customer preview instead of only side
navigation. Other admin modules remain separately tracked for i18n coverage.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ast import literal_eval
import re

from django.template import Context, Template
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

    def test_shared_memory_formatter_translates_unavailable_values(self):
        source = (ROOT / 'apps/core/templatetags/pm.py').read_text(encoding='utf-8')
        self.assertIn("from django.utils.translation import gettext as _", source)
        self.assertIn("return _(\'nicht verfügbar\')", source)
        for code in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            with self.subTest(locale=code):
                self.assertTrue(catalog.get('nicht verfügbar'))


    def test_ops_alert_catalog_has_complete_safe_interpolation(self):
        from apps.core.templatetags.pm import _OPS_ALERT_RULES
        self.assertEqual(len(_OPS_ALERT_RULES), 20)
        source_texts = [entry[2] for entry in _OPS_ALERT_RULES]
        self.assertEqual(len(set(source_texts)), 20)
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for source_text in source_texts:
                with self.subTest(locale=language, source=source_text):
                    self.assertIn(source_text, catalog)
                    self.assertTrue(catalog[source_text])
                    expected = source_text.count('{value}')
                    self.assertEqual(catalog[source_text].count('{value}'), expected)
                    self.assertNotIn('{', catalog[source_text].replace('{value}', ''))
                    self.assertNotIn('}', catalog[source_text].replace('{value}', ''))

    def test_ops_alert_display_contract(self):
        from apps.core.templatetags.pm import ops_alert_display
        examples = (
            ('disk.critical', 'Disk 90.5% belegt', '90.5'),
            ('disk.warning', 'Disk 82.0% belegt', '82.0'),
            ('ram.warning', 'RAM 81.1% belegt', '81.1'),
            ('cpu.warning', 'CPU 10-Minuten-Mittel 93.0%', '93.0'),
            ('backup.unavailable', 'Kein auswertbarer Backupstatus verfügbar', None),
            ('backup.failed', 'Letztes Backup meldet Status failed', 'failed'),
            ('backup.critical', 'Backup ist 33.2 Stunden alt', '33.2'),
            ('restore.unavailable', 'Restore-Statusdatei ist nicht auswertbar', None),
            ('restore.missing', 'Noch kein Restore-Test protokolliert', None),
            ('restore.failed', 'Letzter Restore-Test war nicht erfolgreich', None),
            ('restore.old', 'Letzter Restore-Test ist 42 Tage alt', '42'),
            ('service.node-exporter.down', 'Monitoring-Ziel node-exporter ist nicht erreichbar', 'node-exporter'),
            ('service.prometheus.unknown', 'Monitoring-Ziel prometheus liefert keinen Status', 'prometheus'),
            ('service.caddy.down', 'Caddy Healthcheck ist nicht erreichbar', None),
            ('worker.ping', 'Kein Celery Worker beantwortet den aktiven Ping', None),
            ('beat.heartbeat', 'Celery Beat-Heartbeat älter als 5 Minuten', '5'),
            ('queue.unavailable', 'Celery Queue-Tiefe kann nicht gelesen werden', None),
            ('queue.backlog', 'Celery Queue enthält 120 wartende Jobs', '120'),
            ('task.failures', '7 fehlgeschlagene Hintergrundjobs in 24 Stunden', '7'),
            ('mail.failures', '3 E-Mail-Fehler in 24 Stunden', '3'),
            ('mollie.failures', '2 Mollie-Verarbeitungsfehler in 24 Stunden', '2'),
        )
        with patch(
            'apps.core.templatetags.pm.gettext',
            side_effect=lambda s: 'LOCALIZED ' + s,
        ):
            for code, message, variable in examples:
                with self.subTest(code=code):
                    output = ops_alert_display(SimpleNamespace(code=code, message=message))
                    self.assertTrue(output.startswith('LOCALIZED '), output)
                    if variable and code != 'backup.failed':
                        self.assertIn(variable, output)
                    self.assertNotIn('{value}', output)
        # Unknown and mismatched messages must not be transformed.
        for code, message in (
            ('custom.disk', 'Manueller Hinweis'),
            ('disk.warning', 'RAM 90% belegt'),
            ('service.caddy.down', 'Administrativer Sonderhinweis'),
            ('service.node-exporter.down', 'Monitoring-Ziel prometheus ist nicht erreichbar'),
            ('', '<img src=x onerror=alert(1)>'),
        ):
            alert = SimpleNamespace(code=code, message=message)
            self.assertEqual(ops_alert_display(alert), message)
        with patch('apps.core.templatetags.pm.gettext', return_value='bad {placeholder}'):
            alert = SimpleNamespace(code='disk.warning', message='Disk 88.0% belegt')
            self.assertEqual(ops_alert_display(alert), alert.message)
        rendered = Template('{% load pm %}{{ item|ops_alert_display }}').render(
            Context({'item': SimpleNamespace(
                code='custom', message='<img src=x onerror=alert(1)>',
            )})
        )
        self.assertIn('&lt;img', rendered)
        self.assertNotIn('<img', rendered)
        self.assertIn('{{ a|ops_alert_display }}',
            (ROOT / 'templates/ns_admin/ops.html').read_text(encoding='utf-8'))


    def test_ops_alert_grid_and_shared_toolbar_are_localized(self):
        grid = (ROOT / 'templates/ns_admin/ops_grid.html').read_text(encoding='utf-8')
        toolbar = (ROOT / 'templates/includes/grid_toolbar.html').read_text(encoding='utf-8')
        self.assertIn('{{ row|ops_alert_display }}', grid)
        self.assertNotIn('{{ row.message }}', grid)
        self.assertNotIn('{{ row.severity }}', grid)
        self.assertEqual(grid.count('{% translate row.status %}'), 2)
        self.assertIn('{% translate row.severity %}', grid)
        self.assertEqual(grid.count("|date:'SHORT_DATETIME_FORMAT'"), 3)
        self.assertNotIn("|date:'d.m.Y H:i'", grid)
        for phrase in (
            '{% translate label as translated_filter_label %}',
            '{% translate text %}',
            '{% translate "Seite" %}',
            '{% translate label %}',
            '{% translate display %}',
            '{% translate \'Filter\' %}',
        ):
            self.assertIn(phrase, toolbar)
        self.assertNotIn('aria-label="{{ label }} filtern"', toolbar)
        get_template('ns_admin/ops_grid.html')
        get_template('includes/grid_toolbar.html')
        for code in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / code / 'LC_MESSAGES' / 'django.po'
            )
            for term in ('Backups', 'Restore-Tests', 'Systemwarnungen', 'Erledigt', 'Filter', 'Seite'):
                with self.subTest(language=code, term=term):
                    self.assertTrue(catalog.get(term))


    def test_checkout_legal_account_form_localization(self):
        from apps.accounts.forms import LoginForm, RegistrationForm, PasswordResetConfirmForm
        from apps.legal.forms import WithdrawalDeclarationForm, CancellationDeclarationForm
        from apps.orders.forms import PurchaseForm, RenewalForm, PublicCheckoutForm

        files = (
            ROOT / 'apps/orders/forms.py',
            ROOT / 'apps/legal/forms.py',
            ROOT / 'apps/accounts/forms.py',
        )
        messages = set()
        for path in files:
            source = path.read_text(encoding='utf-8')
            self.assertIn('from django.utils.translation import gettext_lazy as _', source)
            self.assertNotIn('forms.BooleanField(,', source)
            messages.update(re.findall(r"_\('([^']+)'\)", source))
        self.assertGreaterEqual(len(messages), 55)
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for message in messages:
                with self.subTest(locale=language, message=message):
                    self.assertTrue(catalog.get(message))

        purchase = PurchaseForm(require_withdrawal=True)
        renewal = RenewalForm(require_withdrawal=True)
        checkout = PublicCheckoutForm()
        cancellation = CancellationDeclarationForm()
        withdrawal = WithdrawalDeclarationForm()
        self.assertTrue(purchase.fields['accept_withdrawal'].required)
        self.assertTrue(renewal.fields['accept_withdrawal'].required)
        self.assertFalse(PurchaseForm().fields.get('accept_withdrawal'))
        self.assertTrue(checkout.fields['first_name'].label)
        self.assertTrue(checkout.fields['request_early_performance'].label)
        self.assertEqual(
            [code for code, _ in cancellation.fields['cancellation_kind'].choices],
            ['ordinary', 'extraordinary'],
        )
        self.assertTrue(withdrawal.fields['contract_reference'].help_text)
        self.assertTrue(LoginForm().fields['email'].label)
        self.assertTrue(RegistrationForm().fields['company_name'].label)
        self.assertTrue(PasswordResetConfirmForm().fields['password_repeat'].label)

    def test_checkout_and_cancellation_validation_contract_remains_intact(self):
        from types import SimpleNamespace
        from unittest.mock import patch as patch_module
        from apps.orders.forms import PublicCheckoutForm
        from apps.legal.forms import CancellationDeclarationForm, WithdrawalDeclarationForm
        from apps.accounts.forms import PasswordResetConfirmForm

        base = {
            'quantity': 1,
            'first_name': 'Test',
            'last_name': 'Customer',
            'email': 'form-contract@example.test',
            'street': 'Example Street',
            'postal_code': '12345',
            'city': 'Example City',
            'country': 'DE',
            'accept_terms': 'on',
            'accept_privacy': 'on',
            'accept_license': 'on',
        }
        private = PublicCheckoutForm(data={**base, 'customer_type': 'private'})
        self.assertFalse(private.is_valid())
        self.assertIn('accept_withdrawal', private.errors)
        self.assertIn('request_early_performance', private.errors)
        valid_private = PublicCheckoutForm(data={
            **base, 'customer_type': 'private',
            'accept_withdrawal': 'on', 'request_early_performance': 'on',
        })
        self.assertTrue(valid_private.is_valid(), valid_private.errors.as_text())

        with patch_module('apps.orders.forms.TaxRule.objects.filter') as tax_query:
            tax_query.return_value.first.return_value = SimpleNamespace(
                require_vat_id=True, require_tax_number=True,
            )
            company = PublicCheckoutForm(data={**base, 'customer_type': 'company'})
            self.assertFalse(company.is_valid())
            self.assertIn('company_name', company.errors)
            self.assertIn('vat_id', company.errors)
            self.assertIn('tax_number', company.errors)

        base_legal = {
            'name': 'Test Customer',
            'email': 'form-contract@example.test',
            'contract_reference': 'ORDER-TEST-123',
        }
        self.assertTrue(
            WithdrawalDeclarationForm(data=base_legal).is_valid()
        )
        extraordinary = CancellationDeclarationForm(data={
            **base_legal, 'cancellation_kind': 'extraordinary',
        })
        self.assertFalse(extraordinary.is_valid())
        self.assertIn('reason', extraordinary.errors)
        ordinary = CancellationDeclarationForm(data={
            **base_legal, 'cancellation_kind': 'ordinary',
        })
        self.assertTrue(ordinary.is_valid(), ordinary.errors.as_text())
        different_passwords = PasswordResetConfirmForm(data={
            'password': 'AveryStrong2026Pass!',
            'password_repeat': 'AnotherStrong2026Pass!',
        })
        self.assertFalse(different_passwords.is_valid())
        self.assertIn('password_repeat', different_passwords.errors)


    def test_customer_support_and_device_forms_have_localized_labels(self):
        from apps.companies.forms import (
            InviteForm, CompanyForm, PrivateCustomerForm, SupportForm, UserProfileForm,
        )
        from apps.contenthub.forms import FAQEntryForm
        from apps.proaccess.forms import DeviceRegistrationForm

        form_files = (
            ROOT / 'apps/companies/forms.py',
            ROOT / 'apps/contenthub/forms.py',
            ROOT / 'apps/proaccess/forms.py',
        )
        phrases = set()
        for path in form_files:
            source = path.read_text(encoding='utf-8')
            self.assertIn('from django.utils.translation import gettext_lazy as _', source)
            phrases.update(re.findall(r"_\('([^']+)'\)", source))
        self.assertEqual(len(phrases), 33)
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for phrase in phrases:
                with self.subTest(locale=language, phrase=phrase):
                    self.assertTrue(catalog.get(phrase))

        self.assertEqual(
            [value for value, _ in SupportForm().fields['category'].choices],
            ['license', 'payment', 'user', 'device', 'technical', 'privacy', 'other'],
        )
        support = SupportForm(data={
            'category': 'technical',
            'subject': 'Test issue',
            'message': 'The sign-in button does not respond.',
        })
        self.assertTrue(support.is_valid(), support.errors.as_text())
        invalid = SupportForm(data={
            'category': 'technical', 'subject': '', 'message': '',
        })
        self.assertFalse(invalid.is_valid())
        self.assertIn('subject', invalid.errors)
        self.assertIn('message', invalid.errors)
        self.assertTrue(InviteForm().fields['first_name'].label)
        self.assertTrue(CompanyForm().fields['vat_id'].label)
        self.assertTrue(PrivateCustomerForm().fields['postal_code'].label)
        self.assertTrue(UserProfileForm().fields['last_name'].label)
        self.assertTrue(FAQEntryForm().fields['question'].label)
        self.assertTrue(DeviceRegistrationForm().fields['display_name'].label)


    def test_prompt_studio_forms_translate_labels_and_validation_errors(self):
        import ast
        from apps.prompts.forms import PromptPreviewForm
        source = (ROOT / 'apps/prompts/forms.py').read_text(encoding='utf-8')
        syntax = ast.parse(source)
        phrases = {
            node.args[0].value
            for node in ast.walk(syntax)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == '_'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertEqual(len(phrases), 36)
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for phrase in phrases:
                with self.subTest(locale=language, phrase=phrase):
                    self.assertTrue(catalog.get(phrase))
            self.assertIn('%(error)s', catalog['Ungültiges JSON: %(error)s'])
            self.assertIn('{value}', catalog[
                'Ein Feld pro Zeile. Optionales Fragment: Feldname ||| Text mit {value}.'
            ])
            self.assertIn('"microsoft_tier"', catalog[
                'Beispiel: {"microsoft_tier":"premium","payload":{"fields":{...}}}'
            ])
        self.assertEqual(source.count("raise ValidationError(_('Ungültiges JSON: %(error)s')"), 2)
        self.assertIn("lifecycle != 'DRAFT'", source)
        self.assertIn("len(labels) != len(set(labels))", source)
        self.assertIn("('chatbasic', 'Copilot Chat')", source)
        self.assertIn("('premium', 'Microsoft 365 Copilot Business')", source)
        form = PromptPreviewForm(data={
            'microsoft_tier': 'chatbasic',
            'payload_json': '[]',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('payload_json', form.errors)


    def test_core_admin_forms_permission_and_product_i18n(self):
        import ast
        from types import SimpleNamespace as Row
        from django.test import override_settings
        from apps.core.admin_forms import (
            LeadForm, ProductForm, PriceVersionForm, ServiceAccountForm,
            RoleForm, MollieConfigForm, PERMISSION_DOMAIN_LABELS,
            PERMISSION_ACTION_LABELS,
        )

        source = (ROOT / 'apps/core/admin_forms.py').read_text(encoding='utf-8')
        self.assertIn('from django.utils.translation import gettext_lazy as _', source)
        # The first admin group is fully localized; mail and other settings
        # below the GeneralSettingsForm boundary have a separate audit.
        first_group = source.split('class GeneralSettingsForm(forms.Form):', 1)[0]
        gettext_sources = {
            call.args[0].value
            for call in ast.walk(ast.parse(first_group))
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == '_'
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        }
        self.assertEqual(len(gettext_sources), 100)
        for lang in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / lang / 'LC_MESSAGES' / 'django.po'
            )
            for msgid in gettext_sources:
                with self.subTest(language=lang, msgid=msgid):
                    self.assertTrue(catalog.get(msgid))

        # IDs, permission codes, and payment key prefixes are never translated.
        self.assertEqual(
            [value for value, _ in PriceVersionForm().fields['price_type'].choices],
            ['new', 'renewal'],
        )
        self.assertEqual(
            [value for value, _ in ServiceAccountForm.SCOPE_CHOICES],
            ['ops.read', 'prompt.read', 'prompt.draft', 'prompt.test'],
        )
        from django.utils.translation import override
        with override('de'):
            self.assertEqual(str(PERMISSION_DOMAIN_LABELS['customers']), 'Kunden')
            self.assertEqual(str(PERMISSION_ACTION_LABELS['read']), 'Lesen')
        perm = RoleForm.base_fields['permissions']
        display = perm.label_from_instance(Row(name='', code='customers.read'))
        self.assertIn('(customers.read)', display)
        named = perm.label_from_instance(Row(name='External label', code='customers.read'))
        self.assertEqual(named, 'External label (customers.read)')
        self.assertTrue(LeadForm.base_fields['assigned_to'].label)
        self.assertTrue(ProductForm.base_fields['features'].label)

        with override_settings(ENVIRONMENT='production'):
            invalid = MollieConfigForm(data={'api_key': 'test_example'})
            self.assertFalse(invalid.is_valid())
            self.assertIn('api_key', invalid.errors)
        with override_settings(ENVIRONMENT='development'):
            invalid = MollieConfigForm(data={'api_key': 'live_example'})
            self.assertFalse(invalid.is_valid())
            self.assertIn('api_key', invalid.errors)


    def test_admin_mail_monitoring_settings_localization(self):
        import ast
        from apps.core.admin_forms import GeneralSettingsForm, RefundForm, IntegrationSecretForm

        source = (ROOT / 'apps/core/admin_forms.py').read_text(encoding='utf-8')
        settings_scope = source.split('class GeneralSettingsForm(forms.Form):', 1)[1]
        translated = {
            node.args[0].value
            for node in ast.walk(ast.parse('class GeneralSettingsForm(forms.Form):' + settings_scope))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == '_'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertEqual(len(translated), 73)
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for key in translated:
                with self.subTest(language=language, key=key):
                    self.assertTrue(catalog.get(key))
            self.assertIn('v=spf1 ', catalog['Ein SPF-Eintrag muss mit "v=spf1 " beginnen.'])
            self.assertIn('v=DMARC1;', catalog['Ein DMARC-Eintrag muss mit "v=DMARC1;" beginnen.'])
            self.assertIn('_dmarc.<Domain>', catalog['Dokumentierter DNS-Sollwert für _dmarc.<Domain>.'])
            self.assertIn('promptmaster@netstyle.de', catalog[
                'Postfach, über das Microsoft Graph senden soll, z. B. promptmaster@netstyle.de.'
            ])

        self.assertEqual(
            [key for key, _ in GeneralSettingsForm.MAIL_PROVIDER_CHOICES],
            ['smtp1', 'smtp2', 'graph'],
        )
        self.assertEqual(
            [key for key, _ in GeneralSettingsForm.MAIL_DELIVERY_MODE_CHOICES],
            ['manual', 'failover'],
        )
        self.assertFalse(GeneralSettingsForm.base_fields['smtp_password'].widget.render_value)
        self.assertFalse(GeneralSettingsForm.base_fields['graph_client_secret'].widget.render_value)
        self.assertTrue(RefundForm.base_fields['confirm'].required)
        self.assertTrue(IntegrationSecretForm.base_fields['value'].required)

    def test_admin_mail_fallback_and_dns_validation_unchanged(self):
        from apps.core.admin_forms import GeneralSettingsForm
        base = {
            'support_email': 'ops@example.test',
            'mail_provider': 'smtp1',
            'smtp_host': 'smtp.example.test',
            'smtp_port': '587',
            'disk_warning': 80,
            'disk_critical': 90,
            'ram_warning': 80,
            'ram_critical': 90,
            'cpu_warning': 80,
            'backup_warning_hours': 8,
            'backup_critical_hours': 24,
            'restore_warning_days': 35,
        }
        no_fallback = GeneralSettingsForm(data={
            **base, 'mail_delivery_mode': 'failover',
        })
        self.assertFalse(no_fallback.is_valid())
        self.assertIn('mail_fallback_1', no_fallback.errors)
        duplicate_route = GeneralSettingsForm(data={
            **base, 'mail_delivery_mode': 'failover',
            'mail_fallback_1': 'smtp1',
        })
        self.assertFalse(duplicate_route.is_valid())
        self.assertIn('mail_fallback_1', duplicate_route.errors)
        invalid_spf = GeneralSettingsForm(data={
            **base, 'mail_delivery_mode': 'manual', 'mail_spf_record': 'invalid',
        })
        self.assertFalse(invalid_spf.is_valid())
        self.assertIn('mail_spf_record', invalid_spf.errors)
        graph_missing = GeneralSettingsForm(data={
            **base,
            'mail_delivery_mode': 'manual', 'mail_provider': 'graph',
        })
        self.assertFalse(graph_missing.is_valid())
        for required_field in ('graph_tenant_id', 'graph_client_id', 'graph_sender', 'graph_client_secret'):
            self.assertIn(required_field, graph_missing.errors)
        good = GeneralSettingsForm(data={
            **base, 'mail_delivery_mode': 'manual',
        })
        self.assertTrue(good.is_valid(), good.errors.as_text())


    def test_critical_admin_flash_feedback_has_all_language_catalogs(self):
        import ast
        from django.utils.translation import override, gettext
        admin_view_source = (ROOT / 'apps/core/admin_views.py').read_text(encoding='utf-8')
        translated = {
            call.args[0].value
            for call in ast.walk(ast.parse(admin_view_source))
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == '_'
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        }
        critical = (
            'Das eigene netstyle Konto kann hier nicht deaktiviert werden.',
            'Der letzte aktive Superadmin kann nicht deaktiviert werden.',
            'Die eigene 2FA wird nicht über die Admin-Fremdverwaltung zurückgesetzt.',
            '2FA zurückgesetzt. Der Benutzer muss sie beim nächsten Login neu einrichten.',
            'Die eigene Superadmin-Rolle kann nicht hier entfernt werden.',
            'Die letzte aktive Superadmin-Berechtigung kann nicht entfernt werden.',
            'Ein gesperrter Service Account kann nicht rotiert werden.',
            'Mollie-Produktiv-Checkout wurde gesperrt.',
            'Bestätigung für die Erstattung fehlt.',
            'Erstattung wurde an Mollie übermittelt.',
            'Für dieses Unternehmen existiert bereits ein aktiver Firmenadministrator.',
            'Dieser Benutzer ist bereits Firmenadministrator.',
            'Ungültiger Supportstatus.',
            'Ungültiger Bearbeitungsstatus.',
            'Bitte eine Antwort eingeben.',
            'Die Antwort darf höchstens 10.000 Zeichen enthalten.',
            'Status aktualisiert.',
            'Einstellungen gespeichert.',
            'Rolle gespeichert.',
            'Rolle zugewiesen.',
            'Rolle entfernt.',
            'Benutzerstatus aktualisiert.',
        )
        self.assertEqual(len(critical), 22)
        self.assertEqual(len(set(critical)), 22)
        self.assertTrue(set(critical).issubset(translated))
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for source in critical:
                with self.subTest(language=language, source=source):
                    self.assertTrue(catalog.get(source))
            with override(language):
                self.assertEqual(
                    gettext('Der letzte aktive Superadmin kann nicht deaktiviert werden.'),
                    catalog['Der letzte aktive Superadmin kann nicht deaktiviert werden.'],
                )
                self.assertEqual(
                    gettext('Erstattung wurde an Mollie übermittelt.'),
                    catalog['Erstattung wurde an Mollie übermittelt.'],
                )


    def test_standard_admin_feedback_uses_nine_compiled_catalogs(self):
        import ast
        from django.utils.translation import gettext, override
        source = (ROOT / 'apps/core/admin_views.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        translatable = {
            call.args[0].value
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == '_'
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        }
        required = (
            'Lead gespeichert.',
            'Lead-Zuständigkeit aktualisiert.',
            'Gerät wurde widerrufen.',
            'Unternehmensdaten gespeichert.',
            'Benutzer deaktiviert; Lizenz- und Gerätezugänge wurden freigegeben.',
            'Die Lizenz ist bereits frei.',
            'Lizenzzuweisung wurde freigegeben.',
            'Lizenz wurde entsperrt.',
            'Lizenz wurde gesperrt; vorhandene Gerätezugänge wurden widerrufen.',
            'Produkt angelegt. Legen Sie anschließend Preisversionen an.',
            'Feature gespeichert.',
            'Produkt gespeichert.',
            'Neue Preisversion angelegt.',
            'E-Mail-Vorlage gespeichert.',
            'Mollie-Konfiguration gespeichert.',
            'Service Account gesperrt.',
            'Verbrauchererklärung aktualisiert.',
            'Rechtsdokument gespeichert.',
            'Retention-Policy gespeichert.',
            'Löschanfrage verarbeitet und Konto anonymisiert.',
            'Löschanfrage abgelehnt.',
        )
        self.assertEqual(len(required), 21)
        self.assertEqual(len(set(required)), 21)
        self.assertTrue(set(required).issubset(translatable))
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for message in required:
                with self.subTest(language=language, message=message):
                    self.assertTrue(catalog.get(message))
            with override(language):
                self.assertEqual(
                    gettext('Lizenz wurde entsperrt.'),
                    catalog['Lizenz wurde entsperrt.'],
                )


    def test_admin_dynamic_feedback_format_keys_are_localized(self):
        import ast
        from django.utils.translation import gettext, override

        source = (ROOT / 'apps/core/admin_views.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        translated = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == '_'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        texts = (
            'Dieser Lead ist bereits einem Kunden zugeordnet.',
            'Einladung für den Firmenadministrator wurde gesendet.',
            'Kundenantwort gespeichert. Für Demo-Adressen wurde keine E-Mail versendet.',
            'Kundenantwort gespeichert und E-Mail-Benachrichtigung eingeplant.',
            'Kundenantwort gespeichert, E-Mail-Benachrichtigung konnte aber nicht eingeplant werden.',
            'netstyle Benutzer angelegt; Einrichtungslink wurde per E-Mail versendet.',
            'Privatkunden werden aus rechtlichen Gründen über Registrierung/Checkout angelegt; der Lead kann dort anschließend als gewonnen abgeschlossen werden.',
            'Lead wurde in einen Firmenkunden umgewandelt. Der Ansprechpartner hat eine sichere Einladung erhalten.',
            'Lead %(lead_number)s angelegt.',
            'Lead %(lead_number)s gelöscht.',
            'Firmenadministrator wurde auf %(email)s übertragen.',
            'Lizenz wurde %(email)s zugewiesen.',
        )
        self.assertEqual(len(texts), 12)
        self.assertTrue(set(texts).issubset(translated))
        for language in LOCALES:
            catalog = catalog_translations(
                ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
            )
            for text in texts:
                with self.subTest(language=language, text=text):
                    translated_text = catalog.get(text)
                    self.assertTrue(translated_text)
                    if '%(lead_number)s' in text:
                        self.assertIn('%(lead_number)s', translated_text)
                    if '%(email)s' in text:
                        self.assertIn('%(email)s', translated_text)
            with override(language):
                rendered = gettext('Lead %(lead_number)s angelegt.') % {
                    'lead_number': 'L-2026-123',
                }
                self.assertIn('L-2026-123', rendered)
                rendered = gettext('Lizenz wurde %(email)s zugewiesen.') % {
                    'email': 'customer@example.test',
                }
                self.assertIn('customer@example.test', rendered)

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
