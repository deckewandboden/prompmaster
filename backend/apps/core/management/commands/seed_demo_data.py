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
    ('demo.superadmin1@promptmaster.invalid', 'Sarah', 'Administrator', 'superadmin', 'Superadmin'),
    ('demo.superadmin2@promptmaster.invalid', 'Stefan', 'Administrator', 'superadmin', 'Superadmin'),
    ('demo.support1@promptmaster.invalid', 'Sven', 'Support', 'support', 'Vertrieb / Support'),
    ('demo.support2@promptmaster.invalid', 'Sabine', 'Kundenservice', 'support', 'Vertrieb / Support'),
    ('demo.ops1@promptmaster.invalid', 'Olivia', 'Operations', 'ops', 'Technik / Operations'),
    ('demo.ops2@promptmaster.invalid', 'Oliver', 'Technik', 'ops', 'Technik / Operations'),
    ('demo.prompts1@promptmaster.invalid', 'Paula', 'Promptmanager', 'prompt_manager', 'Prompt Manager'),
    ('demo.prompts2@promptmaster.invalid', 'Paul', 'Promptmanager', 'prompt_manager', 'Prompt Manager'),
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



def _password():
    return 'PmDemo-' + secrets.token_urlsafe(16)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class Command(BaseCommand):
    help = (
        'Erzeugt einen sicheren, wiederholbaren Demo-Datenbestand für Staging/Development. '
        'Produktion wird ausdrücklich verweigert.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'production':
            raise CommandError('Demo-Daten dürfen niemals in ENVIRONMENT=production angelegt werden.')

        # The demo command depends only on canonical product/RBAC defaults and
        # intentionally does not alter the Prompt Golden Masters.
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

        # Demo checkout must exercise the same legal-acceptance contract as a
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

        for email, first_name, last_name, role_code, role_label in STAFF_ACCOUNTS:
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
        self.stdout.write(
            'Firmen: '
            + ', '.join(
                f"{spec['customer_number']}={spec['employees']} Benutzer/{spec['seat_count']} PRO-Sitze"
                for spec in COMPANIES
            )
        )
        self.stdout.write('Privatkunden: DEMO-P-2001, DEMO-P-2002, DEMO-P-2003.')
        self.stdout.write('Interne Rollen: je 2× Superadmin, Vertrieb / Support, Technik / Operations, Prompt Manager.')
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
            email = (
                f'demo.{company_slug}.{first_name.lower()}.'
                f'{last_name.lower()}.{index + 1:02d}{DEMO_EMAIL_SUFFIX}'
            )
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
                user = User.objects.filter(email=legacy_email).first()
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
            payment, _ = Payment.objects.update_or_create(
                provider_payment_id=f'tr_demo_{company_index:04d}_{code.lower()}_paid',
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
                        'id': f'tr_demo_{company_index:04d}_{code.lower()}_paid',
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
                    'email': 'eva.einladung.westfalen@promptmaster.invalid',
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

    def _seed_secondary_payment(self, *, company, company_index, product, price, now, state):
        order_status = 'payment_open' if state == 'open' else 'failed'
        order, _ = Order.objects.update_or_create(
            order_number=f"DEMO-R-{company_index:04d}",
            defaults={
                'company': company,
                'private_user': None,
                'status': order_status,
                'currency': 'EUR',
                'gross_total': GROSS_PRICE,
                'tax_total': Decimal('5.73'),
                'billing_snapshot': {'company': company.name, 'demo': True},
                'idempotency_key': f'demo:secondary:{company.customer_number}',
            },
        )
        OrderItem.objects.update_or_create(
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
        Payment.objects.update_or_create(
            provider_payment_id=f'tr_demo_{company_index:04d}_{state}',
            defaults={
                'order': order,
                'provider': 'mollie',
                'status': state,
                'amount': GROSS_PRICE,
                'currency': 'EUR',
                'method': 'creditcard' if state == 'failed' else 'banktransfer',
                'paid_at': None,
                'failed_at': now - timedelta(hours=4) if state == 'failed' else None,
                'processed_paid': False,
                'last_provider_payload': {
                    'id': f'tr_demo_{company_index:04d}_{state}',
                    'status': state,
                    'demo': True,
                },
            },
        )

    def _seed_private_customers(self, *, product, price, now, credentials):
        specs = (
            {
                'customer_number': 'DEMO-P-2001',
                'email': 'demo.privat1@promptmaster.invalid',
                'first_name': 'Petra',
                'last_name': 'Privat',
                'street': 'Privatweg',
                'house_number': '1',
                'postal_code': '57072',
                'city': 'Siegen',
                'state': 'active',
            },
            {
                'customer_number': 'DEMO-P-2002',
                'email': 'demo.privat2@promptmaster.invalid',
                'first_name': 'Patrick',
                'last_name': 'Persönlich',
                'street': 'Teststraße',
                'house_number': '22',
                'postal_code': '44135',
                'city': 'Dortmund',
                'state': 'expiring',
            },
            {
                'customer_number': 'DEMO-P-2003',
                'email': 'demo.privat3@promptmaster.invalid',
                'first_name': 'Pia',
                'last_name': 'Probe',
                'street': 'Musterallee',
                'house_number': '3',
                'postal_code': '20095',
                'city': 'Hamburg',
                'state': 'expired',
            },
        )
        users = {}
        for index, spec in enumerate(specs, start=1):
            password = _password()
            user = self._upsert_user(
                email=spec['email'],
                first_name=spec['first_name'],
                last_name=spec['last_name'],
                password=password,
                is_staff=False,
                two_factor_required=False,
                verified_at=now,
            )
            UserRole.objects.filter(user=user).delete()
            Membership.objects.filter(user=user, active=True).update(active=False)
            PrivateCustomerProfile.objects.update_or_create(
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

        Payment.objects.update_or_create(
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

        if spec['state'] == 'expired':
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
            OrderItem.objects.update_or_create(
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
            Payment.objects.update_or_create(
                provider_payment_id=f'tr_demo_private_{index:04d}_failed',
                defaults={
                    'order': failed_order,
                    'provider': 'mollie',
                    'status': 'failed',
                    'amount': GROSS_PRICE,
                    'currency': 'EUR',
                    'method': 'creditcard',
                    'paid_at': None,
                    'failed_at': now - timedelta(hours=8),
                    'processed_paid': False,
                    'last_provider_payload': {
                        'id': f'tr_demo_private_{index:04d}_failed',
                        'status': 'failed',
                        'demo': True,
                    },
                },
            )

        SupportRequest.objects.update_or_create(
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

    def _seed_demo_leads(self, now):
        support_one = User.objects.get(email='demo.support1@promptmaster.invalid')
        support_two = User.objects.get(email='demo.support2@promptmaster.invalid')
        specs = (
            {
                'lead_number': 'LD-DEMO-0001',
                'kind': 'company',
                'company_name': 'Demo Interessent GmbH',
                'first_name': 'Lena',
                'last_name': 'Lead',
                'email': 'demo.lead1@promptmaster.invalid',
                'phone': '+49 271 5557001',
                'source': 'website',
                'status': 'new',
                'priority': 'high',
                'assigned_to': support_one,
                'next_action_at': now + timedelta(days=1),
                'notes': 'Demo-Lead für Listen-, Detail-, Zuweisungs- und Konvertierungsprüfung.',
            },
            {
                'lead_number': 'LD-DEMO-0002',
                'kind': 'company',
                'company_name': 'Demo Beratung KG',
                'first_name': 'Kai',
                'last_name': 'Kontakt',
                'email': 'demo.lead2@promptmaster.invalid',
                'phone': '+49 231 5557002',
                'source': 'free',
                'status': 'contacted',
                'priority': 'normal',
                'assigned_to': support_two,
                'next_action_at': now + timedelta(days=3),
                'notes': 'Demo-Lead nach Erstkontakt.',
            },
            {
                'lead_number': 'LD-DEMO-0003',
                'kind': 'private',
                'company_name': '',
                'first_name': 'Paula',
                'last_name': 'Prospekt',
                'email': 'demo.lead3@promptmaster.invalid',
                'phone': '',
                'source': 'contact',
                'status': 'qualified',
                'priority': 'low',
                'assigned_to': support_one,
                'next_action_at': None,
                'notes': 'Privat-Leads werden nicht intern in Kundenkonten umgewandelt.',
            },
        )
        keep = []
        for spec in specs:
            lead_number = spec['lead_number']
            keep.append(lead_number)
            Lead.objects.update_or_create(
                lead_number=lead_number,
                defaults={
                    **{key: value for key, value in spec.items() if key != 'lead_number'},
                    'created_by': support_one,
                    'converted_company': None,
                    'converted_at': None,
                    'deleted_at': None,
                },
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
