from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services import (
    get_graph_transport,
    get_mail_delivery,
    get_mail_identity,
    get_smtp_transport,
)


class Command(BaseCommand):
    help = (
        'Validiert die tatsächlich wirksame Mail-Routing-Konfiguration aus '
        'Runtime-Settings, Secret Store und Environment-Fallbacks.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--require-tls',
            action='store_true',
            help='Verlangt STARTTLS für alle aktiven SMTP-Wege.',
        )

    def handle(self, *args, **options):
        delivery = get_mail_delivery()
        identity = get_mail_identity()
        errors = []

        from_email = identity['from_email']
        if '@' not in from_email:
            errors.append('Absender-E-Mail ist nicht gültig konfiguriert.')

        route = delivery['route']
        if not route:
            errors.append('Mail-Routing enthält keinen aktiven Versandweg.')

        details = []
        for provider in route:
            if provider in {'smtp1', 'smtp2'}:
                transport = get_smtp_transport(provider)
                if not transport['host']:
                    errors.append(f'{provider}: SMTP-Host fehlt.')
                if not 1 <= int(transport['port']) <= 65535:
                    errors.append(f'{provider}: SMTP-Port ist ungültig.')
                if options['require_tls'] and not transport['use_tls']:
                    errors.append(f'{provider}: STARTTLS ist für Produktion erforderlich.')
                if transport['username'] and not transport['password_configured']:
                    errors.append(f'{provider}: Benutzername gesetzt, aber Passwort fehlt.')
                details.append(
                    f"{provider}=smtp://{transport['host']}:{transport['port']} "
                    f"tls={'ja' if transport['use_tls'] else 'nein'} "
                    f"auth={'ja' if transport['username'] else 'nein'}"
                )
            elif provider == 'graph':
                graph = get_graph_transport()
                missing = [
                    label
                    for label, value in (
                        ('Tenant-ID', graph['tenant_id']),
                        ('Client-ID', graph['client_id']),
                        ('Client-Secret', graph['client_secret_configured']),
                        ('Sender', graph['sender']),
                    )
                    if not value
                ]
                if missing:
                    errors.append(
                        'graph: Konfiguration unvollständig: ' + ', '.join(missing)
                    )
                details.append(
                    f"graph=sender:{graph['sender'] or '-'} "
                    f"secret={'ja' if graph['client_secret_configured'] else 'nein'}"
                )
            else:
                errors.append(f'Unbekannter Mail-Provider im Routing: {provider}')

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError('MAIL RUNTIME VALIDATION FAIL')

        self.stdout.write(
            self.style.SUCCESS(
                'MAIL RUNTIME VALIDATION OK: '
                f"mode={delivery['mode']} route={' -> '.join(route)} "
                f"from={from_email}"
            )
        )
        for detail in details:
            self.stdout.write(detail)
