from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.core.management.commands.seed_demo_data import (
    COMPANIES,
    DEMO_FIRST_NAMES,
    DEMO_LAST_NAMES,
    STAFF_ACCOUNTS,
    _plus_alias,
    _sha,
)


CONFIRM_VALUE = 'READDRESS-DEMO-USERS'


class Command(BaseCommand):
    help = (
        'Stellt bestehende PromptMaster-Demo-Benutzer auf Gmail-Plus-Aliasse um, '
        'ohne Passwörter oder Benutzerbeziehungen zu verändern.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--base-email', required=True)
        parser.add_argument('--confirm', required=True)
        parser.add_argument(
            '--include-staff',
            action='store_true',
            help='Auch die internen Demo-Staffkonten auf Gmail-Aliasse umstellen.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['confirm'] != CONFIRM_VALUE:
            raise CommandError(
                f'Abbruch. Explizit --confirm {CONFIRM_VALUE} angeben.'
            )

        base_email = options['base_email'].strip().lower()
        if not base_email.endswith('@gmail.com'):
            raise CommandError(
                '--base-email ist derzeit ausschließlich für Gmail-Adressen vorgesehen.'
            )
        _plus_alias(base_email, 1)

        changes = []

        def readdress(user, alias_no, label):
            target = _plus_alias(base_email, alias_no)
            conflict = User.objects.filter(email__iexact=target).exclude(pk=user.pk).first()
            if conflict:
                raise CommandError(
                    f'Zieladresse {target} wird bereits von Benutzer {conflict.pk} verwendet.'
                )
            old = user.email
            if old.lower() != target.lower():
                user.email = target
                user.save(update_fields=['email', 'updated_at'])
            changes.append((label, old, target))

        companies = {
            company.customer_number: company
            for company in Company.objects.filter(
                customer_number__in=[spec['customer_number'] for spec in COMPANIES]
            )
        }
        if len(companies) != len(COMPANIES):
            raise CommandError('Der vollständige DEMO-Unternehmensbestand ist nicht vorhanden.')

        for company_index, spec in enumerate(COMPANIES, start=1):
            company = companies[spec['customer_number']]
            previous_people = sum(
                row['employees'] for row in COMPANIES[:company_index - 1]
            )
            previous_members = sum(
                row['employees'] - 1 for row in COMPANIES[:company_index - 1]
            )
            for index in range(spec['employees']):
                global_index = previous_people + index
                first_name = DEMO_FIRST_NAMES[
                    global_index % len(DEMO_FIRST_NAMES)
                ]
                last_name = DEMO_LAST_NAMES[
                    ((global_index * 7) + (global_index // len(DEMO_FIRST_NAMES)))
                    % len(DEMO_LAST_NAMES)
                ]
                membership = (
                    Membership.objects.filter(
                        company=company,
                        active=True,
                        user__first_name=first_name,
                        user__last_name=last_name,
                    )
                    .select_related('user')
                    .first()
                )
                if membership is None:
                    raise CommandError(
                        f'{company.customer_number}: Demo-Benutzer '
                        f'{first_name} {last_name} fehlt.'
                    )
                if index == 0:
                    alias_no = company_index
                    label = f'{company.customer_number} Admin'
                else:
                    alias_no = 10 + previous_members + index
                    label = f'{company.customer_number} Benutzer'
                readdress(membership.user, alias_no, label)

        private_profiles = list(
            PrivateCustomerProfile.objects.filter(
                customer_number__startswith='DEMO-P-'
            )
            .select_related('user')
            .order_by('customer_number')
        )
        for offset, profile in enumerate(private_profiles, start=101):
            readdress(
                profile.user,
                offset,
                f'{profile.customer_number} Privatkunde',
            )

        if options['include_staff']:
            for alias_no, legacy_email, _first, _last, _role_code, role_label in STAFF_ACCOUNTS:
                user = User.objects.filter(email__iexact=legacy_email).first()
                if user is None:
                    target = _plus_alias(base_email, alias_no)
                    user = User.objects.filter(email__iexact=target).first()
                if user is not None:
                    readdress(user, alias_no, f'Intern {role_label}')

        invitation = Invitation.objects.filter(
            token_hash=_sha('demo-open-invitation-westfalen'),
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).first()
        if invitation is not None:
            invitation.email = _plus_alias(base_email, 401)
            invitation.save(update_fields=['email', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f'{len(changes)} Demo-Benutzer auf Gmail-Plus-Aliasse umgestellt.'
        ))
        for label, old, new in changes:
            self.stdout.write(f'{label:28} | {old} -> {new}')
        if invitation is not None:
            self.stdout.write(
                f'Offene Demo-Einladung          | -> {_plus_alias(base_email, 401)}'
            )
