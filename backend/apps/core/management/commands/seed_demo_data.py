from __future__ import annotations

import hashlib
import io
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
from apps.devices.models import DeviceRegistration
from apps.core.models import Lead
from apps.legal.models import LegalDocument
from apps.licenses.models import (
    License,
    LicenseAssignment,
    LicenseReminder,
    LicenseTerm,
    LicenseUpgradeRequest,
)
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.support.models import SupportRequest


DEMO_PREFIX = 'DEMO-'
DEMO_EMAIL_SUFFIX = '@promptmaster.invalid'
GROSS_PRICE = Decimal('35.88')
NET_PRICE = Decimal('30.15')
TAX_RATE = Decimal('19.00')


COMPANIES = (
    {
        'customer_number': 'DEMO-1001',
        'name': 'Musterwerk GmbH',
        'legal_form': 'GmbH',
        'email': 'info.musterwerk@promptmaster.invalid',
        'phone': '+49 271 5550101',
        'street': 'Beispielstraße',
        'house_number': '12',
        'postal_code': '57072',
        'city': 'Siegen',
        'vat_id': 'DEMO-DE111111111',
        'employees': 3,
        'seat_count': 3,
        'assigned_count': 2,
    },
    {
        'customer_number': 'DEMO-1002',
        'name': 'Westfalen Consulting GmbH',
        'legal_form': 'GmbH',
        'email': 'info.westfalen@promptmaster.invalid',
        'phone': '+49 231 5550202',
        'street': 'Testallee',
        'house_number': '8',
        'postal_code': '44135',
        'city': 'Dortmund',
        'vat_id': 'DEMO-DE222222222',
        'employees': 8,
        'seat_count': 8,
        'assigned_count': 6,
    },
    {
        'customer_number': 'DEMO-1003',
        'name': 'Nordlicht Digital AG',
        'legal_form': 'AG',
        'email': 'info.nordlicht@promptmaster.invalid',
        'phone': '+49 40 5550303',
        'street': 'Demoweg',
        'house_number': '24',
        'postal_code': '20095',
        'city': 'Hamburg',
        'vat_id': 'DEMO-DE333333333',
        'employees': 15,
        'seat_count': 12,
        'assigned_count': 9,
    },
    {
        'customer_number': 'DEMO-1004',
        'name': 'Südwest Logistik GmbH',
        'legal_form': 'GmbH',
        'email': 'info.suedwest@promptmaster.invalid',
        'phone': '+49 721 5550404',
        'street': 'Technologiepark',
        'house_number': '4',
        'postal_code': '76131',
        'city': 'Karlsruhe',
        'vat_id': 'DEMO-DE444444444',
        'employees': 25,
        'seat_count': 20,
        'assigned_count': 16,
    },
    {
        'customer_number': 'DEMO-1005',
        'name': 'RheinMain Engineering KG',
        'legal_form': 'KG',
        'email': 'info.rheinmain@promptmaster.invalid',
        'phone': '+49 69 5550505',
        'street': 'Mainufer',
        'house_number': '55',
        'postal_code': '60311',
        'city': 'Frankfurt am Main',
        'vat_id': 'DEMO-DE555555555',
        'employees': 40,
        'seat_count': 30,
        'assigned_count': 24,
    },
)


STAFF_ACCOUNTS = (
    (201, 'demo.superadmin1@promptmaster.invalid', 'Sarah', 'Administrator', 'superadmin', 'Superadmin'),
    (202, 'demo.superadmin2@promptmaster.invalid', 'Stefan', 'Administrator', 'superadmin', 'Superadmin'),
    (203, 'demo.support1@promptmaster.invalid', 'Sven', 'Support', 'support', 'Vertrieb / Support'),
    (204, 'demo.support2@promptmaster.invalid', 'Sabine', 'Kundenservice', 'support', 'Vertrieb / Support'),
    (205, 'demo.ops1@promptmaster.invalid', 'Olivia', 'Operations', 'ops', 'Technik / Operations'),
    (206, 'demo.ops2@promptmaster.invalid', 'Oliver', 'Technik', 'ops', 'Technik / Operations'),
    (207, 'demo.prompts1@promptmaster.invalid', 'Paula', 'Promptmanager', 'prompt_manager', 'Prompt Manager'),
    (208, 'demo.prompts2@promptmaster.invalid', 'Paul', 'Promptmanager', 'prompt_manager', 'Prompt Manager'),
)

DEMO_FIRST_NAMES = (
    'Anna', 'Jonas', 'Lea', 'Mara', 'Felix', 'Nina', 'David', 'Sophie',
    'Lukas', 'Miriam', 'Tobias', 'Julia', 'Daniel', 'Katharina', 'Robin',
    'Laura', 'Simon', 'Nora', 'Jan', 'Carolin', 'Martin', 'Sarah', 'Sebastian',
    'Elena',
)
DEMO_LAST_NAMES = (
    'Becker', 'Roth', 'Sommer', 'Krueger', 'Weber', 'Hartmann', 'Klein',
    'Schneider', 'Bauer', 'Koch', 'Richter', 'Wolf', 'Neumann', 'Schulz',
    'Vogel', 'Brandt', 'Krause', 'Zimmermann', 'Peters', 'Hoffmann', 'Jung',
    'Lorenz', 'Seidel', 'Fischer',
)

# Purchase ages deliberately overlap across companies so the Netstyle dashboard
# shows a plausible six-month revenue curve instead of one synthetic spike.
DEMO_PURCHASE_AGES = {
    1: (178, 112, 31),
    2: (163, 95, 22),
    3: (147, 80, 16),
    4: (132, 66, 11),
    5: (116, 51, 5),
}



def _plus_alias(base_email: str, number: int) -> str:
    base_email = (base_email or '').strip().lower()
    if '@' not in base_email:
        raise CommandError('Die Demo-Basisadresse ist ungültig.')
    local, domain = base_email.rsplit('@', 1)
    if not local or not domain or '+' in local:
        raise CommandError('Die Demo-Basisadresse muss eine ungetaggte E-Mail-Adresse sein.')
    return f'{local}+{int(number)}@{domain}'


def _password():
    return 'PmDemo-' + secrets.token_urlsafe(16)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class Command(BaseCommand):
    help = (
        'Erzeugt einen sicheren, wiederholbaren Demo-Datenbestand. Staging/Development '
        'ist der Standard; Production erfordert einen ausdrücklich bestätigten '
        'Präsentationsmodus, der Staffkonten und Rechtstexte nicht verändert.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow-production-presentation',
            action='store_true',
            help=(
                'Erlaubt ausschließlich die klar gekennzeichneten DEMO-Kunden-/'
                'Verlaufsdaten in Production. Demo-Staff und Rechtstexte bleiben unberührt.'
            ),
        )
        parser.add_argument(
            '--demo-email-base',
            default='',
            help=(
                'Optional: echte Gmail-Basisadresse für Demo-Benutzer. '
                'Beispiel testnetstyle@gmail.com erzeugt testnetstyle+1@gmail.com usw.'
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.demo_email_base = (options.get('demo_email_base') or '').strip().lower()
        if self.demo_email_base and not self.demo_email_base.endswith('@gmail.com'):
            raise CommandError(
                '--demo-email-base ist derzeit ausschließlich für Gmail-Adressen vorgesehen.'
            )
        if self.demo_email_base:
            _plus_alias(self.demo_email_base, 1)

        production_presentation = (
            settings.ENVIRONMENT == 'production'
            and options['allow_production_presentation']
        )
        if settings.ENVIRONMENT == 'production' and not production_presentation:
            raise CommandError(
                'Demo-Daten dürfen niemals unbeabsichtigt in ENVIRONMENT=production '
                'angelegt werden; für die Präsentationsumgebung ist '
                '--allow-production-presentation ausdrücklich erforderlich.'
            )

        # In Production canonical products, prices, mail templates and RBAC are
        # operator-managed. Never let a presentation seed rewrite those.
        if not production_presentation:
            call_command('seed_defaults', verbosity=0, stdout=io.StringIO())

        now = timezone.now()
        product = Product.objects.get(code='PRO')
        price = (
            ProductPrice.objects.filter(
                product=product,
                price_type='new',
                active=True,
                valid_from__lte=now,
            )
            .filter(valid_until__isnull=True)
            .order_by('-valid_from')
            .first()
        )
        if price is None:
            raise CommandError('Aktiver PRO-Neukaufpreis fehlt; seed_defaults konnte keinen Preis bereitstellen.')

        if not production_presentation:
            # real customer. These records exist only because this command itself
            # is hard-blocked in production.
            demo_legal = {
                'terms': (
                    'DEMO-AGB für Staging-Funktionstests. Kein produktiver Rechtstext.'
                ),
                'privacy': (
                    'DEMO-Datenschutzhinweis für Staging-Funktionstests. Kein produktiver Rechtstext.'
                ),
                'withdrawal': (
                    'DEMO-Widerrufsinformation für Staging-Funktionstests. Kein produktiver Rechtstext.'
                ),
                'license': (
                    'DEMO-Lizenzbedingungen für Staging-Funktionstests. Kein produktiver Rechtstext.'
                ),
            }
            for doc_type, content in demo_legal.items():
                # Never replace an operator-maintained active staging document.
                # Only fill a missing contract with an unmistakable demo version.
                if LegalDocument.objects.filter(
                    doc_type=doc_type,
                    active=True,
                    valid_from__lte=now,
                ).exists():
                    continue
                demo_document, _ = LegalDocument.objects.update_or_create(
                    doc_type=doc_type,
                    version='demo-staging-v1',
                    defaults={
                        'content': content,
                        'valid_from': now - timedelta(minutes=1),
                        'active': False,
                    },
                )
                LegalDocument.objects.filter(
                    doc_type=doc_type,
                    active=True,
                ).exclude(pk=demo_document.pk).update(active=False)
                demo_document.active = True
                demo_document.save(update_fields=['active', 'updated_at'])
    
    
        credentials = []

        if not production_presentation:
            for alias_no, legacy_email, first_name, last_name, role_code, role_label in STAFF_ACCOUNTS:
                email = (
                    _plus_alias(self.demo_email_base, alias_no)
                    if self.demo_email_base
                    else legacy_email
                )
                if self.demo_email_base:
                    existing = User.objects.filter(email=email).first()
                    if existing is None:
                        existing = User.objects.filter(email=legacy_email).first()
                        if existing is not None:
                            existing.email = email
                            existing.save(update_fields=['email', 'updated_at'])
                password = _password()
                user = self._upsert_user(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password=password,
                    is_staff=True,
                    two_factor_required=True,
                    verified_at=now,
                )
                role = Role.objects.get(code=role_code, active=True)
                UserRole.objects.filter(user=user).exclude(role=role).delete()
                UserRole.objects.get_or_create(user=user, role=role)
                credentials.append((role_label, email, password, '2FA-Einrichtung beim ersten Login'))
    
    
        company_users = {}
        for company_index, spec in enumerate(COMPANIES, start=1):
            company = self._upsert_company(spec)
            Company.objects.filter(pk=company.pk).update(
                created_at=now - timedelta(days=DEMO_PURCHASE_AGES[company_index][0] + 24)
            )
            users = self._seed_company_users(company, spec, company_index, now, credentials)
            company_users[spec['customer_number']] = users
            self._seed_commercial_data(
                company=company,
                users=users,
                spec=spec,
                company_index=company_index,
                product=product,
                price=price,
                now=now,
            )

        private_users = self._seed_private_customers(
            product=product,
            price=price,
            now=now,
            credentials=credentials,
        )
        self._seed_demo_leads(now)
        self._seed_cross_function_demo_rows(company_users, private_users, now)

        self.stdout.write(self.style.SUCCESS('Demo-Daten erfolgreich gesetzt.'))
        if self.demo_email_base:
            self.stdout.write(
                f'Demo-Mail aktiv: {self.demo_email_base} mit Gmail-Plus-Aliassen.'
            )
        self.stdout.write(
            'Firmen: '
            + ', '.join(
                f"{spec['customer_number']}={spec['employees']} Benutzer/{spec['seat_count']} PRO-Sitze"
                for spec in COMPANIES
            )
        )
        self.stdout.write('Privatkunden: DEMO-P-2001, DEMO-P-2002, DEMO-P-2003.')
        if production_presentation:
            self.stdout.write(
                'Production-Präsentationsmodus: keine Demo-Staffkonten und keine Rechtstexte verändert.'
            )
        else:
            self.stdout.write(
                'Interne Rollen: je 2× Superadmin, Vertrieb / Support, Technik / Operations, Prompt Manager.'
            )
            self.stdout.write(
                'Der vorhandene echte Superadmin bleibt unverändert und wird für den Superadmin-Test verwendet.'
            )
        self.stdout.write('')
        self.stdout.write('TEMPORÄRE DEMO-ZUGÄNGE – Passwörter werden bei jedem Seed neu erzeugt:')
        for label, email, password, note in credentials:
            self.stdout.write(f'{label:24} | {email:42} | {password:32} | {note}')

    def _upsert_user(
        self,
        *,
        email,
        first_name,
        last_name,
        password=None,
        is_staff=False,
        two_factor_required=False,
        verified_at=None,
    ):
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.is_staff = is_staff
        user.email_verified_at = verified_at
        user.two_factor_required = two_factor_required
        # Demo privileged identities must always start a fresh MFA enrollment.
        if two_factor_required:
            user.totp_secret_enc = ''
            user.last_totp_step = -1
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_unusable_password()
        user.save()
        return user

    def _upsert_company(self, spec):
        company, _ = Company.objects.update_or_create(
            customer_number=spec['customer_number'],
            defaults={
                'name': spec['name'],
                'legal_form': spec['legal_form'],
                'email': spec['email'],
                'phone': spec['phone'],
                'street': spec['street'],
                'house_number': spec['house_number'],
                'postal_code': spec['postal_code'],
                'city': spec['city'],
                'country': 'DE',
                'vat_id': spec['vat_id'],
                'tax_number': f"DEMO-TAX-{spec['customer_number'][-4:]}",
                'status': 'active',
            },
        )
        return company

    def _seed_company_users(self, company, spec, company_index, now, credentials):
        users = []
        previous_people = sum(row['employees'] for row in COMPANIES[:company_index - 1])
        company_slug = company.customer_number.lower().replace('-', '')
        company_age_days = DEMO_PURCHASE_AGES[company_index][0] + 24
        join_span = max(1, company_age_days - 4)

        for index in range(spec['employees']):
            global_index = previous_people + index
            first_name = DEMO_FIRST_NAMES[global_index % len(DEMO_FIRST_NAMES)]
            # The quotient term changes the surname every time a first name
            # cycles, guaranteeing unique full names throughout the 91-person
            # demo estate while keeping the distribution natural.
            last_name = DEMO_LAST_NAMES[
                ((global_index * 7) + (global_index // len(DEMO_FIRST_NAMES)))
                % len(DEMO_LAST_NAMES)
            ]
            is_admin = index == 0
            legacy_email = (
                f'demo.kunde{company_index}.admin{DEMO_EMAIL_SUFFIX}'
                if is_admin
                else f'demo.kunde{company_index}.user{index + 1:02d}{DEMO_EMAIL_SUFFIX}'
            )
            descriptive_email = (
                f'demo.{company_slug}.{first_name.lower()}.'
                f'{last_name.lower()}.{index + 1:02d}{DEMO_EMAIL_SUFFIX}'
            )
            if self.demo_email_base:
                if is_admin:
                    alias_no = company_index
                else:
                    previous_members = sum(
                        row['employees'] - 1
                        for row in COMPANIES[:company_index - 1]
                    )
                    alias_no = 10 + previous_members + index
                email = _plus_alias(self.demo_email_base, alias_no)
            else:
                email = descriptive_email
            login_user = is_admin or index in {1, spec['employees'] - 1}
            password = _password() if login_user else None
            joined_days_ago = max(
                2,
                company_age_days - round((join_span * index) / max(1, spec['employees'] - 1)),
            )
            verified_at = now - timedelta(days=joined_days_ago)

            # Migrate the previous generic address in place. This avoids
            # duplicate memberships when an existing staging/demo database is
            # reseeded after the realistic identity upgrade.
            user = User.objects.filter(email=email).first()
            if user is None:
                candidates = [legacy_email]
                if descriptive_email != email:
                    candidates.insert(0, descriptive_email)
                user = User.objects.filter(email__in=candidates).first()
                if user is not None:
                    user.email = email
                    user.save(update_fields=['email', 'updated_at'])

            user = self._upsert_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                is_staff=False,
                two_factor_required=is_admin,
                verified_at=verified_at,
            )
            UserRole.objects.filter(user=user).delete()
            membership, _ = Membership.objects.update_or_create(
                company=company,
                user=user,
                defaults={'role': 'admin' if is_admin else 'member', 'active': True},
            )

            joined_at = now - timedelta(days=joined_days_ago)
            last_login = None if index % 9 == 8 else now - timedelta(
                days=(index * 3 + company_index) % 19,
                hours=(index * 5) % 12,
            )
            User.objects.filter(pk=user.pk).update(
                created_at=joined_at,
                last_login=last_login,
            )
            Membership.objects.filter(pk=membership.pk).update(created_at=joined_at)
            users.append(user)

            if login_user:
                license_note = (
                    'Firmenadmin · 2FA-Einrichtung beim ersten Login'
                    if is_admin
                    else (
                        'Mitarbeiter · PRO zugewiesen'
                        if index < spec['assigned_count']
                        else 'Mitarbeiter · Free / ohne PRO-Lizenz'
                    )
                )
                credentials.append(
                    (
                        f"{spec['customer_number']} {'Admin' if is_admin else 'Mitarbeiter'}",
                        email,
                        password,
                        license_note,
                    )
                )
        return users

    def _seed_commercial_data(self, *, company, users, spec, company_index, product, price, now):
        quantity = spec['seat_count']
        purchase_ages = DEMO_PURCHASE_AGES[company_index]

        def split_growth(total):
            if total <= 1:
                return (total,)
            if total == 2:
                return (1, 1)
            first = max(1, int(round(total * 0.55)))
            second = max(1, int(round(total * 0.25)))
            third = total - first - second
            if third < 1:
                third = 1
                if first >= second and first > 1:
                    first -= 1
                elif second > 1:
                    second -= 1
            return (first, second, third)

        def paid_order(*, code, seats, purchased_at, phase):
            gross_total = (GROSS_PRICE * seats).quantize(Decimal('0.01'))
            tax_total = (
                gross_total - (gross_total / Decimal('1.19'))
            ).quantize(Decimal('0.01'))
            order, _ = Order.objects.update_or_create(
                order_number=f"DEMO-{code}-{company_index:04d}",
                defaults={
                    'company': company,
                    'private_user': None,
                    'status': 'paid',
                    'currency': 'EUR',
                    'gross_total': gross_total,
                    'tax_total': tax_total,
                    'billing_snapshot': {
                        'company': company.name,
                        'street': company.street,
                        'house_number': company.house_number,
                        'postal_code': company.postal_code,
                        'city': company.city,
                        'country': company.country,
                        'vat_id': company.vat_id,
                        'demo': True,
                        'phase': phase,
                    },
                    'idempotency_key': f'demo:purchase:{company.customer_number}:{code.lower()}',
                },
            )
            item, _ = OrderItem.objects.update_or_create(
                order=order,
                product=product,
                target_license=None,
                defaults={
                    'price_version': price,
                    'quantity': seats,
                    'unit_gross': GROSS_PRICE,
                    'unit_net': NET_PRICE,
                    'tax_rate': TAX_RATE,
                    'product_name_snapshot': product.name,
                },
            )
            provider_payment_id = (
                f'tr_demo_{company_index:04d}_paid'
                if code == 'O'
                else f'tr_demo_{company_index:04d}_{code.lower()}_paid'
            )
            payment, _ = Payment.objects.update_or_create(
                provider_payment_id=provider_payment_id,
                defaults={
                    'order': order,
                    'provider': 'mollie',
                    'status': 'paid',
                    'amount': gross_total,
                    'currency': 'EUR',
                    'method': 'banktransfer' if code in {'O', 'LG'} else 'creditcard',
                    'paid_at': purchased_at,
                    'failed_at': None,
                    'processed_paid': True,
                    'last_provider_payload': {
                        'id': provider_payment_id,
                        'status': 'paid',
                        'method': 'banktransfer' if code in {'O', 'LG'} else 'creditcard',
                        'demo': True,
                        'phase': phase,
                    },
                },
            )
            Order.objects.filter(pk=order.pk).update(created_at=purchased_at)
            OrderItem.objects.filter(pk=item.pk).update(created_at=purchased_at)
            Payment.objects.filter(pk=payment.pk).update(created_at=purchased_at)
            return item, purchased_at

        special = None
        growth_quantity = quantity
        if company_index == 2:
            growth_quantity -= 1
            special = paid_order(
                code='LG',
                seats=1,
                purchased_at=now - timedelta(days=335),
                phase='Bestandslizenz vor aktuellem Wachstum',
            )
        elif company_index == 3:
            growth_quantity -= 1
            special = paid_order(
                code='LG',
                seats=1,
                purchased_at=now - timedelta(days=400),
                phase='Historische, inzwischen abgelaufene Lizenz',
            )

        phase_codes = ('O', 'A1', 'A2')
        phase_labels = (
            'Erstkauf',
            'erste Erweiterung',
            'spätere Nachbuchung',
        )
        cohorts = []
        for phase_index, seats in enumerate(split_growth(growth_quantity)):
            if seats <= 0:
                continue
            item, purchased_at = paid_order(
                code=phase_codes[phase_index],
                seats=seats,
                purchased_at=now - timedelta(days=purchase_ages[phase_index]),
                phase=phase_labels[phase_index],
            )
            cohorts.extend([(item, purchased_at)] * seats)

        if company_index == 2 and special is not None:
            cohorts.insert(min(2, len(cohorts)), special)
        elif company_index == 3 and special is not None:
            cohorts.append(special)

        if len(cohorts) != quantity:
            raise CommandError(
                f'Demo-Kaufhistorie für {company.customer_number} erzeugte '
                f'{len(cohorts)} statt {quantity} Lizenzkohorten.'
            )

        demo_license_numbers = [
            f"PM-DEMO-{company_index:02d}-{seat_index + 1:03d}"
            for seat_index in range(quantity)
        ]
        LicenseAssignment.objects.filter(
            license__license_number__in=demo_license_numbers,
            ended_at__isnull=True,
        ).delete()
        DeviceRegistration.objects.filter(
            license__license_number__in=demo_license_numbers,
        ).delete()

        licenses = []
        for seat_index, (number, cohort) in enumerate(zip(demo_license_numbers, cohorts)):
            item, valid_from = cohort
            valid_until = valid_from + timedelta(days=product.default_license_days)
            expired = valid_until <= now
            status = (
                'expired'
                if expired
                else ('active' if seat_index < spec['assigned_count'] else 'free')
            )

            license_obj, _ = License.objects.update_or_create(
                license_number=number,
                defaults={
                    'company': company,
                    'owner_user': None,
                    'product': product,
                    'status': status,
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                },
            )
            License.objects.filter(pk=license_obj.pk).update(created_at=valid_from)
            # A demo license represents one paid term in this seed. Remove an
            # older synthetic term if the historical cohort changed.
            LicenseTerm.objects.filter(license=license_obj).exclude(order_item=item).delete()
            LicenseTerm.objects.update_or_create(
                license=license_obj,
                order_item=item,
                defaults={
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                    'paid_gross_amount': GROSS_PRICE,
                    'status': 'active',
                    'refunded_at': None,
                },
            )
            licenses.append(license_obj)

            if not expired and seat_index < spec['assigned_count']:
                LicenseAssignment.objects.create(
                    license=license_obj,
                    user=users[seat_index],
                )

            remaining_days = (valid_until.date() - now.date()).days
            if not expired and remaining_days <= 30:
                LicenseReminder.objects.update_or_create(
                    license=license_obj,
                    kind='t30',
                    target_valid_until=valid_until,
                    defaults={'status': 'pending', 'error': ''},
                )
            if expired:
                LicenseReminder.objects.update_or_create(
                    license=license_obj,
                    kind='t0',
                    target_valid_until=valid_until,
                    defaults={
                        'status': 'sent',
                        'sent_at': valid_until + timedelta(hours=2),
                        'error': '',
                    },
                )

        # Add realistic registered devices without storing reusable bearer tokens.
        device_specs = []
        if licenses and spec['assigned_count'] >= 2:
            device_specs.extend(
                [
                    (users[0], licenses[0], 'Büro-PC', 'Windows', 'Edge', 2 + company_index),
                    (users[1], licenses[1], 'Notebook', 'Windows', 'Firefox', 7 + company_index),
                ]
            )
            if company_index in {1, 4, 5}:
                device_specs.append(
                    (users[1], licenses[1], 'Mobilgerät', 'iOS', 'Safari', 1)
                )
        if spec['assigned_count'] >= 6:
            device_specs.append(
                (users[5], licenses[5], 'Homeoffice-Notebook', 'Windows', 'Edge', 28)
            )

        for device_index, (user, license_obj, display, os_family, browser_family, hours_ago) in enumerate(device_specs):
            token_hash = _sha(f'demo-device:{company.customer_number}:{device_index}')
            DeviceRegistration.objects.update_or_create(
                token_hash=token_hash,
                defaults={
                    'user': user,
                    'license': license_obj,
                    'display_name': display,
                    'os_family': os_family,
                    'browser_family': browser_family,
                    'last_seen_at': now - timedelta(hours=hours_ago),
                    'revoked_at': None,
                },
            )

        # Unlicensed employee requests PRO to exercise the approval workflow.
        request_user = users[-1]
        if not LicenseAssignment.objects.filter(user=request_user, ended_at__isnull=True).exists():
            upgrade, _ = LicenseUpgradeRequest.objects.update_or_create(
                user=request_user,
                product=product,
                status='pending',
                defaults={
                    'company': company,
                    'note': 'Demo: Mitarbeiter benötigt PromptMaster Pro für tägliche Copilot-Aufgaben.',
                },
            )
            LicenseUpgradeRequest.objects.filter(pk=upgrade.pk).update(
                created_at=now - timedelta(days=3 + company_index * 2)
            )

        categories = ('license', 'technical', 'payment', 'device', 'user')
        support_states = ('new', 'in_progress', 'closed', 'new', 'in_progress')
        category = categories[(company_index - 1) % len(categories)]
        support_status = support_states[(company_index - 1) % len(support_states)]
        subject = f"[DEMO] {company.customer_number} – Beispielanfrage"
        support, _ = SupportRequest.objects.update_or_create(
            company=company,
            user=users[0],
            subject=subject,
            defaults={
                'license': licenses[0] if licenses else None,
                'category': category,
                'message': (
                    'Demo-Datensatz zur Prüfung von Kunden-, Lizenz-, Geräte-, '
                    'Zahlungs- und Supportansichten.'
                ),
                'status': support_status,
            },
        )
        SupportRequest.objects.filter(pk=support.pk).update(
            created_at=now - timedelta(days=(company_index * 9) - 4)
        )

        if company_index == 2:
            Invitation.objects.update_or_create(
                token_hash=_sha('demo-open-invitation-westfalen'),
                defaults={
                    'company': company,
                    'email': (
                        _plus_alias(self.demo_email_base, 401)
                        if self.demo_email_base
                        else 'eva.einladung.westfalen@promptmaster.invalid'
                    ),
                    'first_name': 'Eva',
                    'last_name': 'Reimann',
                    'expires_at': now + timedelta(days=7),
                    'accepted_at': None,
                    'revoked_at': None,
                    'invited_by': users[0],
                },
            )
            self._seed_secondary_payment(
                company=company,
                company_index=company_index,
                product=product,
                price=price,
                now=now,
                state='open',
            )
        elif company_index == 3:
            self._seed_secondary_payment(
                company=company,
                company_index=company_index,
                product=product,
                price=price,
                now=now,
                state='failed',
            )
        elif company_index == 4:
            self._seed_secondary_payment(
                company=company,
                company_index=company_index,
                product=product,
                price=price,
                now=now,
                state='chargeback',
            )

    def _seed_secondary_payment(self, *, company, company_index, product, price, now, state):
        if state == 'open':
            order_status = 'payment_open'
            occurred_at = now - timedelta(days=2)
            paid_at = None
            failed_at = None
            processed_paid = False
            method = 'banktransfer'
        elif state == 'failed':
            order_status = 'failed'
            occurred_at = now - timedelta(days=6)
            paid_at = None
            failed_at = occurred_at
            processed_paid = False
            method = 'creditcard'
        elif state == 'chargeback':
            order_status = 'paid'
            occurred_at = now - timedelta(days=18)
            paid_at = occurred_at - timedelta(days=3)
            failed_at = None
            processed_paid = True
            method = 'creditcard'
        else:
            raise CommandError(f'Unbekannter Demo-Zahlungsstatus: {state}')

        order, _ = Order.objects.update_or_create(
            order_number=f"DEMO-R-{company_index:04d}",
            defaults={
                'company': company,
                'private_user': None,
                'status': order_status,
                'currency': 'EUR',
                'gross_total': GROSS_PRICE,
                'tax_total': Decimal('5.73'),
                'billing_snapshot': {
                    'company': company.name,
                    'demo': True,
                    'scenario': state,
                },
                'idempotency_key': f'demo:secondary:{company.customer_number}',
            },
        )
        item, _ = OrderItem.objects.update_or_create(
            order=order,
            product=product,
            target_license=None,
            defaults={
                'price_version': price,
                'quantity': 1,
                'unit_gross': GROSS_PRICE,
                'unit_net': NET_PRICE,
                'tax_rate': TAX_RATE,
                'product_name_snapshot': product.name,
            },
        )
        payment, _ = Payment.objects.update_or_create(
            provider_payment_id=f'tr_demo_{company_index:04d}_{state}',
            defaults={
                'order': order,
                'provider': 'mollie',
                'status': state,
                'amount': GROSS_PRICE,
                'currency': 'EUR',
                'method': method,
                'paid_at': paid_at,
                'failed_at': failed_at,
                'processed_paid': processed_paid,
                'last_provider_payload': {
                    'id': f'tr_demo_{company_index:04d}_{state}',
                    'status': state,
                    'demo': True,
                },
            },
        )
        Order.objects.filter(pk=order.pk).update(created_at=occurred_at)
        OrderItem.objects.filter(pk=item.pk).update(created_at=occurred_at)
        Payment.objects.filter(pk=payment.pk).update(created_at=occurred_at)

    def _seed_private_customers(self, *, product, price, now, credentials):
        specs = (
            {
                'customer_number': 'DEMO-P-2001',
                'email': 'petra.hagedorn.privat@promptmaster.invalid',
                'legacy_email': 'demo.privat1@promptmaster.invalid',
                'alias_no': 101,
                'first_name': 'Petra',
                'last_name': 'Hagedorn',
                'street': 'Privatweg',
                'house_number': '1',
                'postal_code': '57072',
                'city': 'Siegen',
                'state': 'active',
                'registered_days': 128,
            },
            {
                'customer_number': 'DEMO-P-2002',
                'email': 'patrick.moeller.privat@promptmaster.invalid',
                'legacy_email': 'demo.privat2@promptmaster.invalid',
                'alias_no': 102,
                'first_name': 'Patrick',
                'last_name': 'Moeller',
                'street': 'Teststraße',
                'house_number': '22',
                'postal_code': '44135',
                'city': 'Dortmund',
                'state': 'expiring',
                'registered_days': 372,
            },
            {
                'customer_number': 'DEMO-P-2003',
                'email': 'pia.wendt.privat@promptmaster.invalid',
                'legacy_email': 'demo.privat3@promptmaster.invalid',
                'alias_no': 103,
                'first_name': 'Pia',
                'last_name': 'Wendt',
                'street': 'Musterallee',
                'house_number': '3',
                'postal_code': '20095',
                'city': 'Hamburg',
                'state': 'expired',
                'registered_days': 414,
            },
        )
        users = {}
        for index, spec in enumerate(specs, start=1):
            email = (
                _plus_alias(self.demo_email_base, spec['alias_no'])
                if self.demo_email_base
                else spec['email']
            )
            existing = User.objects.filter(email=email).first()
            if existing is None:
                candidates = [spec['legacy_email']]
                if spec['email'] != email:
                    candidates.insert(0, spec['email'])
                existing = User.objects.filter(email__in=candidates).first()
                if existing is not None:
                    existing.email = email
                    existing.save(update_fields=['email', 'updated_at'])

            password = _password()
            registered_at = now - timedelta(days=spec['registered_days'])
            user = self._upsert_user(
                email=email,
                first_name=spec['first_name'],
                last_name=spec['last_name'],
                password=password,
                is_staff=False,
                two_factor_required=False,
                verified_at=registered_at,
            )
            User.objects.filter(pk=user.pk).update(
                created_at=registered_at,
                last_login=now - timedelta(days=index * 4),
            )
            UserRole.objects.filter(user=user).delete()
            Membership.objects.filter(user=user, active=True).update(active=False)
            profile, _ = PrivateCustomerProfile.objects.update_or_create(
                user=user,
                defaults={
                    'customer_number': spec['customer_number'],
                    'street': spec['street'],
                    'house_number': spec['house_number'],
                    'postal_code': spec['postal_code'],
                    'city': spec['city'],
                    'country': 'DE',
                },
            )
            PrivateCustomerProfile.objects.filter(pk=profile.pk).update(
                created_at=registered_at
            )
            users[spec['customer_number']] = user
            credentials.append(
                (
                    f"{spec['customer_number']} Privatkunde",
                    user.email,
                    password,
                    {
                        'active': 'Privatkunde · aktive PRO-Lizenz',
                        'expiring': 'Privatkunde · PRO läuft in 30 Tagen aus',
                        'expired': 'Privatkunde · abgelaufene PRO-Lizenz / fehlgeschlagene Zahlung',
                    }[spec['state']],
                )
            )
            self._seed_private_commercial_data(
                user=user,
                spec=spec,
                index=index,
                product=product,
                price=price,
                now=now,
            )
        return users

    def _seed_private_commercial_data(self, *, user, spec, index, product, price, now):
        order, _ = Order.objects.update_or_create(
            order_number=f'DEMO-P-O-{index:04d}',
            defaults={
                'company': None,
                'private_user': user,
                'status': 'paid',
                'currency': 'EUR',
                'gross_total': GROSS_PRICE,
                'tax_total': Decimal('5.73'),
                'billing_snapshot': {
                    'customer_type': 'private',
                    'name': user.full_name,
                    'email': user.email,
                    'street': user.private_customer.street,
                    'house_number': user.private_customer.house_number,
                    'postal_code': user.private_customer.postal_code,
                    'city': user.private_customer.city,
                    'country': user.private_customer.country,
                    'demo': True,
                },
                'idempotency_key': f"demo:private:{spec['customer_number']}",
            },
        )
        item, _ = OrderItem.objects.update_or_create(
            order=order,
            product=product,
            target_license=None,
            defaults={
                'price_version': price,
                'quantity': 1,
                'unit_gross': GROSS_PRICE,
                'unit_net': NET_PRICE,
                'tax_rate': TAX_RATE,
                'product_name_snapshot': product.name,
            },
        )
        if spec['state'] == 'expired':
            valid_from = now - timedelta(days=400)
            valid_until = now - timedelta(days=35)
            license_status = 'expired'
        elif spec['state'] == 'expiring':
            valid_from = now - timedelta(days=358)
            valid_until = now + timedelta(days=30)
            license_status = 'active'
        else:
            valid_from = now - timedelta(days=90)
            valid_until = now + timedelta(days=275)
            license_status = 'active'

        license_obj, _ = License.objects.update_or_create(
            license_number=f'PM-DEMO-P-{index:03d}',
            defaults={
                'company': None,
                'owner_user': user,
                'product': product,
                'status': license_status,
                'valid_from': valid_from,
                'valid_until': valid_until,
            },
        )
        LicenseTerm.objects.update_or_create(
            license=license_obj,
            order_item=item,
            defaults={
                'valid_from': valid_from,
                'valid_until': valid_until,
                'paid_gross_amount': GROSS_PRICE,
                'status': 'active',
                'refunded_at': None,
            },
        )
        LicenseAssignment.objects.filter(license=license_obj).delete()
        DeviceRegistration.objects.filter(license=license_obj).delete()
        if license_status == 'active':
            LicenseAssignment.objects.create(license=license_obj, user=user)
            DeviceRegistration.objects.create(
                user=user,
                license=license_obj,
                token_hash=_sha(f"demo-private-device:{spec['customer_number']}"),
                display_name='Privates Notebook',
                os_family='Windows',
                browser_family='Firefox' if index == 2 else 'Edge',
                last_seen_at=now - timedelta(hours=index),
            )
        if spec['state'] == 'expiring':
            LicenseReminder.objects.update_or_create(
                license=license_obj,
                kind='t30',
                target_valid_until=valid_until,
                defaults={'status': 'pending', 'error': ''},
            )
        if spec['state'] == 'expired':
            LicenseReminder.objects.update_or_create(
                license=license_obj,
                kind='t0',
                target_valid_until=valid_until,
                defaults={'status': 'sent', 'sent_at': now - timedelta(days=35), 'error': ''},
            )

        payment, _ = Payment.objects.update_or_create(
            provider_payment_id=f'tr_demo_private_{index:04d}_paid',
            defaults={
                'order': order,
                'provider': 'mollie',
                'status': 'paid',
                'amount': GROSS_PRICE,
                'currency': 'EUR',
                'method': 'banktransfer',
                'paid_at': valid_from,
                'failed_at': None,
                'processed_paid': True,
                'last_provider_payload': {
                    'id': f'tr_demo_private_{index:04d}_paid',
                    'status': 'paid',
                    'demo': True,
                },
            },
        )
        Order.objects.filter(pk=order.pk).update(created_at=valid_from)
        OrderItem.objects.filter(pk=item.pk).update(created_at=valid_from)
        Payment.objects.filter(pk=payment.pk).update(created_at=valid_from)
        License.objects.filter(pk=license_obj.pk).update(created_at=valid_from)

        if spec['state'] == 'expired':
            failed_at = now - timedelta(days=4)
            failed_order, _ = Order.objects.update_or_create(
                order_number=f'DEMO-P-R-{index:04d}',
                defaults={
                    'company': None,
                    'private_user': user,
                    'status': 'failed',
                    'currency': 'EUR',
                    'gross_total': GROSS_PRICE,
                    'tax_total': Decimal('5.73'),
                    'billing_snapshot': {'customer_type': 'private', 'demo': True},
                    'idempotency_key': f"demo:private:failed:{spec['customer_number']}",
                },
            )
            failed_item, _ = OrderItem.objects.update_or_create(
                order=failed_order,
                product=product,
                target_license=license_obj,
                defaults={
                    'price_version': price,
                    'quantity': 1,
                    'unit_gross': GROSS_PRICE,
                    'unit_net': NET_PRICE,
                    'tax_rate': TAX_RATE,
                    'product_name_snapshot': product.name,
                },
            )
            failed_payment, _ = Payment.objects.update_or_create(
                provider_payment_id=f'tr_demo_private_{index:04d}_failed',
                defaults={
                    'order': failed_order,
                    'provider': 'mollie',
                    'status': 'failed',
                    'amount': GROSS_PRICE,
                    'currency': 'EUR',
                    'method': 'creditcard',
                    'paid_at': None,
                    'failed_at': failed_at,
                    'processed_paid': False,
                    'last_provider_payload': {
                        'id': f'tr_demo_private_{index:04d}_failed',
                        'status': 'failed',
                        'demo': True,
                    },
                },
            )
            Order.objects.filter(pk=failed_order.pk).update(created_at=failed_at)
            OrderItem.objects.filter(pk=failed_item.pk).update(created_at=failed_at)
            Payment.objects.filter(pk=failed_payment.pk).update(created_at=failed_at)

        support, _ = SupportRequest.objects.update_or_create(
            user=user,
            company=None,
            subject=f"[DEMO] {spec['customer_number']} – Privatanfrage",
            defaults={
                'license': license_obj,
                'category': 'technical' if spec['state'] != 'expired' else 'payment',
                'message': 'Demo-Datensatz zur Prüfung des Privatkundenportals.',
                'status': 'new' if spec['state'] != 'expired' else 'in_progress',
            },
        )
        SupportRequest.objects.filter(pk=support.pk).update(
            created_at=now - timedelta(days=(index * 11) + 2)
        )

    def _seed_demo_leads(self, now):
        support_one_email = (
            _plus_alias(self.demo_email_base, 203)
            if self.demo_email_base
            else 'demo.support1@promptmaster.invalid'
        )
        support_two_email = (
            _plus_alias(self.demo_email_base, 204)
            if self.demo_email_base
            else 'demo.support2@promptmaster.invalid'
        )
        support_one = User.objects.filter(email=support_one_email).first()
        support_two = User.objects.filter(email=support_two_email).first()
        if support_one is None:
            support_one = User.objects.filter(
                is_staff=True,
                is_active=True,
            ).order_by('-is_superuser', 'created_at').first()
        if support_two is None:
            support_two = (
                User.objects.filter(is_staff=True, is_active=True)
                .exclude(pk=getattr(support_one, 'pk', None))
                .order_by('-is_superuser', 'created_at')
                .first()
                or support_one
            )
        if support_one is None:
            raise CommandError(
                'Für Demo-Leads wird mindestens ein aktiver interner Staff-Benutzer benötigt.'
            )
        specs = (
            {
                'lead_number': 'LD-DEMO-0001',
                'kind': 'company',
                'company_name': 'Siegerland Automation GmbH',
                'first_name': 'Lena',
                'last_name': 'Althaus',
                'email': 'lena.althaus.siegerland@promptmaster.invalid',
                'phone': '+49 271 5557001',
                'source': 'website',
                'status': 'new',
                'priority': 'high',
                'assigned_to': support_one,
                'next_action_at': now + timedelta(days=1),
                'notes': 'Website-Anfrage nach einer Teamlizenz für Microsoft Copilot.',
                'age_days': 1,
            },
            {
                'lead_number': 'LD-DEMO-0002',
                'kind': 'company',
                'company_name': 'Ruhrtal Beratung KG',
                'first_name': 'Kai',
                'last_name': 'Hensel',
                'email': 'kai.hensel.ruhrtal@promptmaster.invalid',
                'phone': '+49 231 5557002',
                'source': 'free',
                'status': 'contacted',
                'priority': 'normal',
                'assigned_to': support_two,
                'next_action_at': now + timedelta(days=3),
                'notes': 'Mehrere Free-Registrierungen; Teamlizenz wurde telefonisch besprochen.',
                'age_days': 6,
            },
            {
                'lead_number': 'LD-DEMO-0003',
                'kind': 'private',
                'company_name': '',
                'first_name': 'Paula',
                'last_name': 'Westphal',
                'email': 'paula.westphal.prospekt@promptmaster.invalid',
                'phone': '',
                'source': 'contact',
                'status': 'qualified',
                'priority': 'low',
                'assigned_to': support_one,
                'next_action_at': now + timedelta(days=5),
                'notes': 'Privatinteressentin mit konkreter PRO-Nachfrage.',
                'age_days': 13,
            },
            {
                'lead_number': 'LD-DEMO-0004',
                'kind': 'company',
                'company_name': 'Mittelhessen Planung GmbH',
                'first_name': 'Henrik',
                'last_name': 'Sauer',
                'email': 'henrik.sauer.mittelhessen@promptmaster.invalid',
                'phone': '+49 641 5557004',
                'source': 'checkout',
                'status': 'qualified',
                'priority': 'high',
                'assigned_to': support_two,
                'next_action_at': now + timedelta(days=2),
                'notes': 'Checkout abgebrochen; Angebot für 18 Benutzer angefordert.',
                'age_days': 21,
            },
            {
                'lead_number': 'LD-DEMO-0005',
                'kind': 'company',
                'company_name': 'Südwest Prozess GmbH',
                'first_name': 'Clara',
                'last_name': 'Bender',
                'email': 'clara.bender.suedwest@promptmaster.invalid',
                'phone': '+49 721 5557005',
                'source': 'website',
                'status': 'won',
                'priority': 'normal',
                'assigned_to': support_one,
                'next_action_at': None,
                'notes': 'Historischer Demo-Lead, erfolgreich zum Kunden konvertiert.',
                'age_days': 52,
                'converted_customer': 'DEMO-1004',
            },
            {
                'lead_number': 'LD-DEMO-0006',
                'kind': 'company',
                'company_name': 'Rhein Data Services GmbH',
                'first_name': 'Malte',
                'last_name': 'Jansen',
                'email': 'malte.jansen.rheindata@promptmaster.invalid',
                'phone': '+49 221 5557006',
                'source': 'free',
                'status': 'lost',
                'priority': 'normal',
                'assigned_to': support_two,
                'next_action_at': None,
                'notes': 'Budgetentscheidung vertagt; aktuell kein weiterer Kontakt.',
                'age_days': 74,
            },
            {
                'lead_number': 'LD-DEMO-0007',
                'kind': 'company',
                'company_name': 'Mainwerk Engineering GmbH',
                'first_name': 'Theresa',
                'last_name': 'Kappel',
                'email': 'theresa.kappel.mainwerk@promptmaster.invalid',
                'phone': '+49 69 5557007',
                'source': 'contact',
                'status': 'won',
                'priority': 'high',
                'assigned_to': support_one,
                'next_action_at': None,
                'notes': 'Demo-Lead aus früherer Vertriebsphase, inzwischen Kunde.',
                'age_days': 108,
                'converted_customer': 'DEMO-1005',
            },
            {
                'lead_number': 'LD-DEMO-0008',
                'kind': 'company',
                'company_name': 'Nordwest Handel GmbH',
                'first_name': 'Oliver',
                'last_name': 'Dreyer',
                'email': 'oliver.dreyer.nordwest@promptmaster.invalid',
                'phone': '+49 421 5557008',
                'source': 'other',
                'status': 'lost',
                'priority': 'low',
                'assigned_to': support_two,
                'next_action_at': None,
                'notes': 'Historischer Demo-Lead ohne Abschluss.',
                'age_days': 151,
            },
        )
        keep = []
        for spec in specs:
            lead_number = spec['lead_number']
            keep.append(lead_number)
            converted_number = spec.get('converted_customer')
            converted_company = (
                Company.objects.get(customer_number=converted_number)
                if converted_number
                else None
            )
            defaults = {
                key: value
                for key, value in spec.items()
                if key not in {'lead_number', 'age_days', 'converted_customer'}
            }
            lead, _ = Lead.objects.update_or_create(
                lead_number=lead_number,
                defaults={
                    **defaults,
                    'created_by': support_one,
                    'converted_company': converted_company,
                    'converted_at': (
                        now - timedelta(days=max(1, spec['age_days'] - 7))
                        if converted_company
                        else None
                    ),
                    'deleted_at': None,
                },
            )
            Lead.objects.filter(pk=lead.pk).update(
                created_at=now - timedelta(days=spec['age_days'])
            )
        Lead.objects.filter(lead_number__startswith='LD-DEMO-').exclude(
            lead_number__in=keep
        ).delete()

    def _seed_cross_function_demo_rows(self, company_users, private_users, now):
        EmailMessage.objects.filter(subject__startswith='[DEMO]').delete()
        template_paid = EmailTemplate.objects.filter(code='payment_confirmed').first()
        template_support = EmailTemplate.objects.filter(code='support_confirmation').first()
        EmailMessage.objects.create(
            template=template_paid,
            recipient=company_users['DEMO-1001'][0].email,
            subject='[DEMO] Zahlung bestätigt',
            status='sent',
            sent_at=now - timedelta(days=1),
            provider_reference='demo-mail-1001',
            context={'order': 'DEMO-O-0001', 'amount': '107.64', 'currency': 'EUR', 'demo': True},
        )
        EmailMessage.objects.create(
            template=template_support,
            recipient=company_users['DEMO-1002'][0].email,
            subject='[DEMO] Supportanfrage eingegangen',
            status='queued',
            context={'subject': '[DEMO] Beispielanfrage', 'demo': True},
        )
        EmailMessage.objects.create(
            template=template_support,
            recipient=company_users['DEMO-1003'][0].email,
            subject='[DEMO] E-Mail mit Fehlerstatus',
            status='error',
            error='Demo: SMTP-Fehler zur Darstellung des Fehlerzustands.',
            retry_count=2,
            context={'subject': '[DEMO] Fehlerzustand', 'demo': True},
        )
        EmailMessage.objects.create(
            template=template_support,
            recipient=private_users['DEMO-P-2001'].email,
            subject='[DEMO] Privatkunden-Support',
            status='sent',
            sent_at=now - timedelta(hours=12),
            provider_reference='demo-mail-private-2001',
            context={'subject': '[DEMO] Privatkunden-Support', 'demo': True},
        )
