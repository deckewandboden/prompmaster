from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.core.management.commands.seed_demo_data import STAFF_ACCOUNTS, _plus_alias, _sha


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

        companies = list(
            Company.objects.filter(customer_number__startswith='DEMO-')
            .order_by('customer_number')
        )
        if not companies:
            raise CommandError('Keine DEMO-Unternehmen gefunden.')

        member_alias = 11
        for company_index, company in enumerate(companies, start=1):
            memberships = list(
                Membership.objects.filter(company=company, active=True)
                .select_related('user')
                .order_by('created_at', 'user__email')
            )
            admins = [row for row in memberships if row.role == 'admin']
            if len(admins) != 1:
                raise CommandError(
                    f'{company.customer_number}: erwartet genau einen aktiven Demo-Admin.'
                )
            readdress(
                admins[0].user,
                company_index,
                f'{company.customer_number} Admin',
            )
            for membership in memberships:
                if membership.pk == admins[0].pk:
                    continue
                readdress(
                    membership.user,
                    member_alias,
                    f'{company.customer_number} Benutzer',
                )
                member_alias += 1

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
