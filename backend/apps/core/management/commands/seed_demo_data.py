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
from apps.companies.models import Company, Invitation, Membership
from apps.devices.models import DeviceRegistration
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
)


STAFF_ACCOUNTS = (
    ('demo.support@promptmaster.invalid', 'Sven', 'Support', 'support', 'Vertrieb / Support'),
    ('demo.ops@promptmaster.invalid', 'Olivia', 'Operations', 'ops', 'Technik / Operations'),
    ('demo.prompts@promptmaster.invalid', 'Paul', 'Promptmanager', 'prompt_manager', 'Prompt Manager'),
)


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

        self._seed_cross_function_demo_rows(company_users, now)

        self.stdout.write(self.style.SUCCESS('Demo-Daten erfolgreich gesetzt.'))
        self.stdout.write(
            'Firmen: '
            + ', '.join(
                f"{spec['customer_number']}={spec['employees']} Benutzer/{spec['seat_count']} PRO-Sitze"
                for spec in COMPANIES
            )
        )
        self.stdout.write('Interne Rollen: Vertrieb / Support, Technik / Operations, Prompt Manager.')
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
        first_names = [
            'Anna', 'Jonas', 'Lea', 'Mara', 'Felix', 'Nina', 'David', 'Sophie',
            'Lukas', 'Miriam', 'Tobias', 'Julia', 'Daniel', 'Katharina', 'Robin',
        ]
        last_names = [
            'Becker', 'Roth', 'Sommer', 'Krüger', 'Weber', 'Hartmann', 'Klein',
            'Schneider', 'Bauer', 'Koch', 'Richter', 'Wolf', 'Neumann', 'Schulz', 'Vogel',
        ]
        users = []
        slug = f'kunde{company_index}'
        for index in range(spec['employees']):
            is_admin = index == 0
            email = (
                f'demo.{slug}.admin{DEMO_EMAIL_SUFFIX}'
                if is_admin
                else f'demo.{slug}.user{index + 1:02d}{DEMO_EMAIL_SUFFIX}'
            )
            login_user = is_admin or index in {1, spec['employees'] - 1}
            password = _password() if login_user else None
            user = self._upsert_user(
                email=email,
                first_name=first_names[index],
                last_name=last_names[index],
                password=password,
                is_staff=False,
                two_factor_required=is_admin,
                verified_at=now,
            )
            UserRole.objects.filter(user=user).delete()
            Membership.objects.update_or_create(
                company=company,
                user=user,
                defaults={'role': 'admin' if is_admin else 'member', 'active': True},
            )
            users.append(user)
            if login_user:
                license_note = (
                    'Firmenadmin · 2FA-Einrichtung beim ersten Login'
                    if is_admin
                    else (
                        'Mitarbeiter · PRO zugewiesen'
                        if index < spec['assigned_count']
                        else 'Mitarbeiter · ohne PRO-Lizenz'
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
        gross_total = (GROSS_PRICE * quantity).quantize(Decimal('0.01'))
        tax_total = (gross_total - (gross_total / Decimal('1.19'))).quantize(Decimal('0.01'))
        order, _ = Order.objects.update_or_create(
            order_number=f"DEMO-O-{company_index:04d}",
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
                },
                'idempotency_key': f'demo:purchase:{company.customer_number}',
            },
        )
        item, _ = OrderItem.objects.update_or_create(
            order=order,
            product=product,
            target_license=None,
            defaults={
                'price_version': price,
                'quantity': quantity,
                'unit_gross': GROSS_PRICE,
                'unit_net': NET_PRICE,
                'tax_rate': TAX_RATE,
                'product_name_snapshot': product.name,
            },
        )
        Payment.objects.update_or_create(
            provider_payment_id=f'tr_demo_{company_index:04d}_paid',
            defaults={
                'order': order,
                'provider': 'mollie',
                'status': 'paid',
                'amount': gross_total,
                'currency': 'EUR',
                'method': 'banktransfer',
                'paid_at': now - timedelta(days=90),
                'failed_at': None,
                'processed_paid': True,
                'last_provider_payload': {
                    'id': f'tr_demo_{company_index:04d}_paid',
                    'status': 'paid',
                    'method': 'banktransfer',
                    'demo': True,
                },
            },
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
        for seat_index, number in enumerate(demo_license_numbers):
            expired = company_index == 3 and seat_index == quantity - 1
            expiring = company_index == 2 and seat_index == 2
            if expired:
                valid_from = now - timedelta(days=400)
                valid_until = now - timedelta(days=35)
                status = 'expired'
            elif expiring:
                valid_from = now - timedelta(days=335)
                valid_until = now + timedelta(days=30)
                status = 'active'
            else:
                valid_from = now - timedelta(days=90)
                valid_until = now + timedelta(days=275)
                status = 'active' if seat_index < spec['assigned_count'] else 'free'

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
                target = users[seat_index]
                LicenseAssignment.objects.create(
                    license=license_obj,
                    user=target,
                )

            if expiring:
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
                    defaults={'status': 'sent', 'sent_at': now - timedelta(days=35), 'error': ''},
                )

        # Add realistic registered devices without storing reusable bearer tokens.
        device_specs = []
        if licenses and spec['assigned_count'] >= 2:
            device_specs.extend(
                [
                    (users[0], licenses[0], 'Büro-PC', 'Windows', 'Edge'),
                    (users[1], licenses[1], 'Notebook', 'Windows', 'Firefox'),
                ]
            )
            if company_index == 1:
                device_specs.append((users[1], licenses[1], 'iPhone', 'iOS', 'Safari'))
        for device_index, (user, license_obj, display, os_family, browser_family) in enumerate(device_specs):
            token_hash = _sha(f'demo-device:{company.customer_number}:{device_index}')
            DeviceRegistration.objects.update_or_create(
                token_hash=token_hash,
                defaults={
                    'user': user,
                    'license': license_obj,
                    'display_name': display,
                    'os_family': os_family,
                    'browser_family': browser_family,
                    'last_seen_at': now - timedelta(hours=device_index + 1),
                    'revoked_at': None,
                },
            )

        # Unlicensed employee requests PRO to exercise the approval workflow.
        request_user = users[-1]
        if not LicenseAssignment.objects.filter(user=request_user, ended_at__isnull=True).exists():
            LicenseUpgradeRequest.objects.update_or_create(
                user=request_user,
                product=product,
                status='pending',
                defaults={
                    'company': company,
                    'note': 'Demo: Mitarbeiter benötigt PromptMaster Pro für tägliche Copilot-Aufgaben.',
                },
            )

        category = ('license', 'technical', 'payment')[company_index - 1]
        support_status = ('new', 'in_progress', 'closed')[company_index - 1]
        subject = f"[DEMO] {company.customer_number} – Beispielanfrage"
        SupportRequest.objects.update_or_create(
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

        if company_index == 2:
            Invitation.objects.update_or_create(
                token_hash=_sha('demo-open-invitation-westfalen'),
                defaults={
                    'company': company,
                    'email': 'demo.einladung@promptmaster.invalid',
                    'first_name': 'Eva',
                    'last_name': 'Einladung',
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

    def _seed_cross_function_demo_rows(self, company_users, now):
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
