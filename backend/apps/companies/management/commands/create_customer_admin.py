import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import audit
from apps.companies.models import Company, Membership, PrivateCustomerProfile


class Command(BaseCommand):
    help = (
        'Create a customer company administrator directly without sending an email. '
        'A generated temporary password is printed once when no --password is supplied.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--company-name', required=True)
        parser.add_argument('--customer-number')
        parser.add_argument('--email', required=True)
        parser.add_argument('--first-name', required=True)
        parser.add_argument('--last-name', required=True)
        parser.add_argument('--password')
        parser.add_argument(
            '--reset-existing-password',
            action='store_true',
            help='Explicitly allow resetting a pre-existing non-staff customer identity.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        company_name = options['company_name'].strip()
        customer_number = (options.get('customer_number') or '').strip()
        first_name = options['first_name'].strip()
        last_name = options['last_name'].strip()

        companies = Company.objects.select_for_update().filter(status='active')
        if customer_number:
            companies = companies.filter(customer_number=customer_number)
        else:
            companies = companies.filter(name__iexact=company_name)

        matches = list(companies[:2])
        if not matches:
            qualifier = (
                f'Kundennummer {customer_number!r}'
                if customer_number
                else f'Firmenname {company_name!r}'
            )
            raise CommandError(
                f'Aktives Kundenunternehmen für {qualifier} nicht gefunden. '
                'Das Unternehmen muss zuerst im Kundenstamm existieren.'
            )
        if len(matches) > 1:
            raise CommandError(
                'Firmenname ist nicht eindeutig. Bitte zusätzlich --customer-number angeben.'
            )
        company = matches[0]

        current_admin = (
            Membership.objects.select_for_update()
            .select_related('user')
            .filter(company=company, active=True, role='admin')
            .first()
        )
        if current_admin and current_admin.user.email.lower() != email:
            raise CommandError(
                f'{company.name} hat bereits den Firmenadministrator '
                f'{current_admin.user.email}. Keine automatische Überschreibung.'
            )

        user = User.objects.select_for_update().filter(email__iexact=email).first()
        temporary_password = None

        if user is not None:
            if user.is_staff:
                raise CommandError(
                    'Interne netstyle Benutzer dürfen keine Kundenmitgliedschaft erhalten.'
                )
            if PrivateCustomerProfile.objects.filter(user=user).exists():
                raise CommandError(
                    'Diese Identität ist bereits Privatkunde und kann in V1 nicht '
                    'gleichzeitig Firmenkunde sein.'
                )
            foreign_membership = (
                Membership.objects.filter(user=user, active=True)
                .exclude(company=company)
                .first()
            )
            if foreign_membership:
                raise CommandError(
                    'Diese Identität gehört bereits zu einem anderen aktiven Unternehmen.'
                )
            if current_admin is None and not options['reset_existing_password']:
                raise CommandError(
                    'Die E-Mail-Adresse existiert bereits. Aus Sicherheitsgründen wird '
                    'sie nicht automatisch übernommen. Mit --reset-existing-password '
                    'kann die vorhandene Kundenidentität ausdrücklich übernommen werden.'
                )
        else:
            temporary_password = options.get('password') or secrets.token_urlsafe(18)
            if len(temporary_password) < 12:
                raise CommandError('Das temporäre Passwort muss mindestens 12 Zeichen haben.')
            user = User.objects.create_user(
                email=email,
                password=temporary_password,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                email_verified_at=timezone.now(),
                two_factor_required=True,
            )

        dirty = []
        if user.first_name != first_name:
            user.first_name = first_name
            dirty.append('first_name')
        if user.last_name != last_name:
            user.last_name = last_name
            dirty.append('last_name')
        if not user.is_active:
            user.is_active = True
            dirty.append('is_active')
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            dirty.append('email_verified_at')
        if not user.two_factor_required:
            user.two_factor_required = True
            dirty.append('two_factor_required')

        if user.pk and options['reset_existing_password'] and temporary_password is None:
            temporary_password = options.get('password') or secrets.token_urlsafe(18)
            if len(temporary_password) < 12:
                raise CommandError('Das temporäre Passwort muss mindestens 12 Zeichen haben.')
            user.set_password(temporary_password)
            dirty.append('password')
            user.security_version += 1
            dirty.append('security_version')

        if dirty:
            dirty.append('updated_at')
            user.save(update_fields=list(dict.fromkeys(dirty)))

        membership, created = Membership.objects.get_or_create(
            company=company,
            user=user,
            defaults={'role': 'admin', 'active': True},
        )
        if not created and (membership.role != 'admin' or not membership.active):
            membership.role = 'admin'
            membership.active = True
            membership.save(update_fields=['role', 'active', 'updated_at'])

        audit(
            None,
            'customer_admin.direct_created',
            company,
            {
                'user_id': str(user.id),
                'email': email,
                'method': 'management_command_no_email',
                'password_generated': temporary_password is not None,
                'mfa_required': True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Kundenadministrator bereit: {user.full_name} <{user.email}> '
                f'für {company.name} ({company.customer_number}).'
            )
        )
        self.stdout.write('E-Mail-Versand: NEIN')
        self.stdout.write('MFA-Pflicht: JA')
        if temporary_password is not None:
            self.stdout.write(
                self.style.WARNING(
                    f'TEMPORARY_PASSWORD={temporary_password}'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    'Temporäres Passwort jetzt sicher notieren; es wird nicht per E-Mail versendet.'
                )
            )
        else:
            self.stdout.write('Passwort: unverändert')
