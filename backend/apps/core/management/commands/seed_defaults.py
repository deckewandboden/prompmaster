from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Permission, Role
from apps.catalog.models import Feature, Product, ProductEntitlement, ProductPrice, TaxRule
from apps.catalog.services import PRO_ACCESS_FEATURE
from apps.notifications.models import EmailTemplate
from apps.notifications.services import sanitize_stored_email_contexts


PERMS = [
    'customers.read', 'customers.write', 'leads.read', 'leads.write',
    'leads.assign', 'leads.convert', 'leads.delete', 'licenses.read', 'licenses.write',
    'devices.write', 'orders.read', 'payments.read', 'payments.refund',
    'products.read', 'products.write', 'email.read', 'email.write',
    'ops.read', 'api.read', 'api.write', 'roles.read', 'roles.write',
    'legal.read', 'legal.write', 'support.read', 'support.write',
    'audit.read', 'settings.read', 'settings.write', 'prompts.read',
    'prompts.write', 'prompts.compose', 'prompts.publish', 'prompts.quality',
    'content.read', 'content.write',
]


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        perms = {
            code: Permission.objects.get_or_create(code=code, defaults={'name': code})[0]
            for code in PERMS
        }
        roles = [
            ('superadmin', 'Superadmin', PERMS),
            (
                'support',
                'Vertrieb / Support',
                [
                    'customers.read', 'customers.write', 'leads.read', 'leads.write',
                    'leads.assign', 'leads.convert', 'leads.delete', 'licenses.read',
                    'licenses.write', 'devices.write', 'orders.read',
                    'payments.read', 'products.read', 'email.read',
                    'support.read', 'support.write', 'audit.read', 'content.read',
                ],
            ),
            ('ops', 'Technik / Operations', ['ops.read', 'api.read', 'audit.read']),
            (
                'prompt_manager',
                'Prompt Manager',
                [
                    'prompts.read', 'prompts.write', 'prompts.compose',
                    'prompts.publish', 'prompts.quality', 'content.read',
                    'content.write', 'audit.read',
                ],
            ),
        ]
        for code, name, codes in roles:
            role, _ = Role.objects.get_or_create(code=code, defaults={'name': name})
            role.name = name
            role.active = True
            role.save(update_fields=['name', 'active', 'updated_at'])
            role.permissions.set([perms[item] for item in codes])

        product, _ = Product.objects.get_or_create(
            code='PRO',
            defaults={
                'name': 'PromptMaster Pro',
                'description': 'PromptMaster Pro',
                'default_license_days': 365,
                'default_device_limit': 2,
                'reminder_1_days': 60,
                'reminder_2_days': 30,
                'critical_warning_days': 7,
            },
        )
        pro_feature, _ = Feature.objects.get_or_create(
            code=PRO_ACCESS_FEATURE,
            defaults={'name': 'PromptMaster Pro Runtime'},
        )
        ProductEntitlement.objects.update_or_create(
            product=product,
            feature=pro_feature,
            defaults={'enabled': True},
        )

        now = timezone.now()
        for price_type in ['new', 'renewal']:
            if not ProductPrice.objects.filter(
                product=product,
                price_type=price_type,
                active=True,
                valid_until__isnull=True,
            ).exists():
                ProductPrice.objects.create(
                    product=product,
                    price_type=price_type,
                    gross_amount=Decimal('35.88'),
                    currency='EUR',
                    valid_from=now,
                )

        TaxRule.objects.get_or_create(
            country='DE',
            customer_type='company',
            active=True,
            defaults={'tax_rate': 19},
        )
        TaxRule.objects.get_or_create(
            country='DE',
            customer_type='private',
            active=True,
            defaults={'tax_rate': 19},
        )

        templates = {
            'verify_email': (
                'E-Mail-Adresse bestätigen',
                'Bitte bestätigen Sie Ihre E-Mail-Adresse: {url}',
            ),
            'password_reset': (
                'PromptMaster Passwort zurücksetzen',
                'Sie können Ihr Passwort innerhalb einer Stunde zurücksetzen: {url}',
            ),
            'checkout_activation': (
                'PromptMaster Pro Zugang aktivieren',
                'Ihre Zahlung wurde bestätigt. Legen Sie innerhalb von 7 Tagen Ihr Passwort fest und aktivieren Sie damit Ihren PromptMaster-Zugang: {url}',
            ),
            'staff_invite': (
                'PromptMaster netstyle-Zugang einrichten',
                'Ihr netstyle PromptMaster-Administrationszugang wurde angelegt. Legen Sie innerhalb einer Stunde Ihr Passwort fest: {url}',
            ),
            'invite': (
                'Ihre PromptMaster-Einladung',
                'Sie wurden zu PromptMaster eingeladen. Der Link ist 24 Stunden gültig: {url}',
            ),
            't60': (
                'PromptMaster-Lizenz läuft in 60 Tagen ab',
                'Ihre Lizenz {license} läuft am {expiry} ab.',
            ),
            't30': (
                'PromptMaster-Lizenz läuft in 30 Tagen ab',
                'Ihre Lizenz {license} läuft am {expiry} ab.',
            ),
            'license_expired': (
                'PromptMaster-Lizenz abgelaufen',
                'Ihre Lizenz {license} ist am {expiry} abgelaufen. Der Pro-Zugriff ist bis zur Verlängerung gesperrt.',
            ),
            'payment_confirmed': (
                'PromptMaster-Zahlung bestätigt',
                'Ihre Zahlung für Bestellung {order} über {amount} {currency} wurde bestätigt.',
            ),
            'contract_confirmation': (
                'PromptMaster – Vertragsbestätigung {order}',
                'Ihre Vertragsbestätigung für PromptMaster Pro\n\n'
                'Anbieter: netstyle Informationstechnik GmbH, Am Bühl 2, 57223 Kreuztal\n'
                'Bestellung: {order}\n'
                'Vertragsdatum / Zahlungsbestätigung: {contract_date}\n'
                'Leistungsumfang: {items}\n'
                'Gesamtpreis: {amount} {currency}\n'
                'Laufzeit: {term}\n'
                'Automatische Verlängerung: nein\n'
                'Vorzeitiger Leistungsbeginn verlangt: {early_performance}\n\n'
                'Bei Vertragsschluss einbezogene Unterlagen:\n\n{legal_documents}\n\n'
                'Diese E-Mail dient als Vertragsbestätigung auf einem dauerhaften Datenträger.',
            ),
            'payment_failed': (
                'PromptMaster-Zahlung nicht erfolgreich',
                'Die Zahlung für Bestellung {order} konnte nicht erfolgreich abgeschlossen werden. Status: {status}.',
            ),
            'license_renewed': (
                'PromptMaster-Lizenz verlängert',
                'Ihre Lizenz {license} wurde erfolgreich bis {expiry} verlängert.',
            ),
            'refund_confirmed': (
                'PromptMaster-Erstattung bestätigt',
                'Die Erstattung über {amount} {currency} für Lizenz {license} wurde bestätigt.',
            ),
            'chargeback_review': (
                'PromptMaster-Zahlung muss geklärt werden',
                'Für Bestellung {order} wurde eine Zahlungsrückbuchung gemeldet. Betroffene Lizenzzugriffe wurden vorläufig gesperrt.',
            ),
            'assignment_link': (
                'PromptMaster-Lizenz zuordnen',
                'Für Sie wurde die Lizenz {license} vorbereitet. Der sichere Link ist bis {expiry} gültig: {url}',
            ),
            'upgrade_request': (
                'PromptMaster Pro angefragt',
                '{user} ({email}) bittet um Zuweisung von {product}.',
            ),
            'upgrade_request_resolved': (
                'PromptMaster Pro-Anfrage bearbeitet',
                'Ihre Anfrage für {product} wurde bearbeitet: {status}.',
            ),
            'support_confirmation': (
                'Ihre PromptMaster-Anfrage',
                'Wir haben Ihre Anfrage erhalten: {subject}',
            ),
            'support_notification': (
                'Neue PromptMaster-Supportanfrage',
                'Kategorie: {category}\nKunde: {customer}\nE-Mail: {email}\nLizenz: {license}\nBetreff: {subject}\n\n{message}',
            ),
            'withdrawal_received': (
                'PromptMaster – Eingang Ihres Widerrufs',
                'Guten Tag {name},\n\nwir bestätigen den Eingang Ihres Widerrufs.\n'
                'Vertrag / Bestellung / Kundennummer: {contract_reference}\n'
                'Eingang: {submitted_at}\n'
                'Vorgangs-ID: {declaration_id}\n\n'
                'Diese Nachricht dokumentiert den elektronischen Eingang Ihrer Erklärung.',
            ),
            'cancellation_received': (
                'PromptMaster – Eingang Ihrer Kündigung',
                'Guten Tag {name},\n\nwir bestätigen den Eingang Ihrer Kündigung.\n'
                'Art: {cancellation_kind}\n'
                'Vertrag / Bestellung / Kundennummer: {contract_reference}\n'
                'Gewünschter Beendigungszeitpunkt: {requested_end_date}\n'
                'Grund: {reason}\n'
                'Eingang: {submitted_at}\n'
                'Vorgangs-ID: {declaration_id}\n\n'
                'Diese Nachricht dokumentiert den elektronischen Eingang Ihrer Erklärung.',
            ),

        }
        for code, (subject, body) in templates.items():
            EmailTemplate.objects.update_or_create(
                code=code,
                defaults={'subject': subject, 'body_text': body, 'active': True},
            )

        sanitized = sanitize_stored_email_contexts()
        self.stdout.write(
            self.style.SUCCESS(
                f'Defaults gesetzt. Historische sensible Mail-Kontexte verschlüsselt: {sanitized}.'
            )
        )
