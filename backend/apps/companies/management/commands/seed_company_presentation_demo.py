import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.companies.models import Company, Membership
from apps.devices.models import DeviceRegistration
from apps.licenses.models import (
    License,
    LicenseAssignment,
    LicenseReminder,
    LicenseTerm,
    LicenseUpgradeRequest,
)
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment


DEMO_SUFFIX = '@promptmaster.invalid'
MEMBER_SPECS = (
    ('member01', 'Anna', 'Becker', 'pro_base', 90, 1),
    ('member02', 'Jonas', 'Roth', 'pro_base', 90, 2),
    ('member03', 'Lea', 'Sommer', 'pro_base', 90, 4),
    ('member04', 'Felix', 'Weber', 'pro_base', 90, 8),
    ('member05', 'Nina', 'Hartmann', 'pro_base', 90, 1),
    ('member06', 'Tobias', 'Richter', 'pro_expiring', 343, 3),
    ('member07', 'Sophie', 'Klein', 'free', 60, 2),
    ('member08', 'David', 'Schneider', 'free_upgrade_pending', 14, 1),
    ('member09', 'Julia', 'Wolf', 'pro_addon', 21, 1),
    ('member10', 'Daniel', 'Neumann', 'pro_addon', 21, 1),
    ('member11', 'Miriam', 'Koch', 'free_new', 3, None),
)


def _password():
    return 'PmDemo-' + secrets.token_urlsafe(14)


def _token_hash(seed):
    return hashlib.sha256(seed.encode('utf-8')).hexdigest()


class Command(BaseCommand):
    help = (
        'Create a deterministic 12-person company presentation scenario: one '
        'existing company administrator plus eleven non-deliverable demo users. '
        'No email is sent.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--company-name', required=True)
        parser.add_argument('--customer-number')
        parser.add_argument(
            '--confirm-presentation-demo',
            action='store_true',
            help='Required acknowledgement that presentation demo data may be created.',
        )
        parser.add_argument(
            '--allow-production',
            action='store_true',
            help='Required in ENVIRONMENT=production. The command only touches its own demo identities/assets.',
        )
        parser.add_argument(
            '--reset-demo-passwords',
            action='store_true',
            help='Generate new temporary passwords for already existing presentation demo users.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirm_presentation_demo']:
            raise CommandError('--confirm-presentation-demo ist erforderlich.')
        if settings.ENVIRONMENT == 'production' and not options['allow_production']:
            raise CommandError(
                'Presentation-Demo in Production nur mit --allow-production.'
            )

        company_name = options['company_name'].strip()
        customer_number = (options.get('customer_number') or '').strip()
        company_qs = Company.objects.select_for_update().filter(status='active')
        if customer_number:
            company_qs = company_qs.filter(customer_number=customer_number)
        else:
            company_qs = company_qs.filter(name__iexact=company_name)
        companies = list(company_qs[:2])
        if not companies:
            raise CommandError('Aktives Kundenunternehmen nicht gefunden.')
        if len(companies) > 1:
            raise CommandError('Firmenname nicht eindeutig; --customer-number angeben.')
        company = companies[0]

        admin_memberships = list(
            Membership.objects.select_for_update()
            .select_related('user')
            .filter(company=company, active=True, role='admin')
        )
        if len(admin_memberships) != 1:
            raise CommandError(
                'Für die Präsentationsdemo muss genau ein aktiver Firmenadministrator existieren.'
            )
        admin_membership = admin_memberships[0]
        admin = admin_membership.user
        if admin.is_staff:
            raise CommandError('Firmenadministrator darf kein interner Staff-Benutzer sein.')

        non_demo_memberships = (
            Membership.objects.filter(company=company)
            .exclude(user__email__endswith=DEMO_SUFFIX)
        )
        if non_demo_memberships.exclude(pk=admin_membership.pk).exists():
            raise CommandError(
                'Das Unternehmen enthält bereits weitere echte Benutzer. '
                'Die Präsentationsdemo verändert keine realen Kundenkonten.'
            )

        marker = company.id.hex[:8].upper()
        license_prefix = f'PM-PRES-{marker}-'
        order_prefix = f'PRES-{marker}-'
        payment_prefix = f'tr_pres_{marker.lower()}_'

        if company.licenses.exclude(license_number__startswith=license_prefix).exists():
            raise CommandError(
                'Das Unternehmen enthält bereits nicht zur Präsentationsdemo gehörende Lizenzen.'
            )
        if company.orders.exclude(order_number__startswith=order_prefix).exists():
            raise CommandError(
                'Das Unternehmen enthält bereits nicht zur Präsentationsdemo gehörende Bestellungen.'
            )

        now = timezone.now()
        product = Product.objects.filter(code='PRO', active=True).first()
        if not product:
            raise CommandError('Aktives Produkt PRO fehlt.')

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
        if not price:
            raise CommandError('Aktiver PRO-Neukaufpreis fehlt.')

        tax_rule = (
            TaxRule.objects.filter(
                country=company.country or 'DE',
                customer_type='company',
                active=True,
            )
            .order_by('-created_at')
            .first()
        )
        tax_rate = Decimal(str(tax_rule.tax_rate if tax_rule else '19.00'))
        divisor = Decimal('1') + tax_rate / Decimal('100')
        unit_gross = price.gross_amount
        unit_net = (unit_gross / divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        credentials = []
        users = {}
        for key, first_name, last_name, scenario, joined_days, last_login_days in MEMBER_SPECS:
            email = f'presentation.{marker.lower()}.{key}{DEMO_SUFFIX}'
            user = User.objects.select_for_update().filter(email=email).first()
            created = user is None
            password = None
            if user is None:
                password = _password()
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True,
                    email_verified_at=now - timedelta(days=joined_days),
                    two_factor_required=False,
                )
            else:
                foreign = (
                    Membership.objects.filter(user=user)
                    .exclude(company=company)
                    .exists()
                )
                if foreign:
                    raise CommandError(f'Demo-Identität {email} gehört zu einem anderen Unternehmen.')
                user.first_name = first_name
                user.last_name = last_name
                user.is_active = True
                if user.email_verified_at is None:
                    user.email_verified_at = now - timedelta(days=joined_days)
                user.two_factor_required = False
                if options['reset_demo_passwords']:
                    password = _password()
                    user.set_password(password)
                    user.security_version += 1
                user.save()
            UserRole.objects.filter(user=user).delete()

            membership = Membership.objects.filter(company=company, user=user).first()
            if membership is None:
                membership = Membership.objects.create(
                    company=company,
                    user=user,
                    role='member',
                    active=True,
                )
            elif membership.role != 'member' or not membership.active:
                membership.role = 'member'
                membership.active = True
                membership.save(update_fields=['role', 'active', 'updated_at'])

            joined_at = now - timedelta(days=joined_days)
            User.objects.filter(pk=user.pk).update(
                created_at=joined_at,
                last_login=(
                    now - timedelta(days=last_login_days)
                    if last_login_days is not None
                    else None
                ),
            )
            Membership.objects.filter(pk=membership.pk).update(created_at=joined_at)
            users[key] = user
            if created or password:
                credentials.append((scenario, email, password))

        if Membership.objects.filter(company=company).count() != 12:
            raise CommandError(
                'Presentation-Demo erwartet exakt 12 Benutzer inklusive Firmenadministrator.'
            )

        def order_bundle(suffix, quantity, purchased_at, method, label):
            gross_total = (unit_gross * quantity).quantize(Decimal('0.01'))
            net_total = (unit_net * quantity).quantize(Decimal('0.01'))
            tax_total = (gross_total - net_total).quantize(Decimal('0.01'))
            order, _ = Order.objects.update_or_create(
                order_number=f'{order_prefix}{suffix}',
                defaults={
                    'company': company,
                    'private_user': None,
                    'status': 'paid',
                    'currency': price.currency,
                    'gross_total': gross_total,
                    'tax_total': tax_total,
                    'billing_snapshot': {
                        'company': company.name,
                        'presentation_demo': True,
                        'scenario': label,
                    },
                    'idempotency_key': f'presentation:{company.id}:{suffix.lower()}',
                },
            )
            item, _ = OrderItem.objects.update_or_create(
                order=order,
                product=product,
                target_license=None,
                defaults={
                    'price_version': price,
                    'quantity': quantity,
                    'unit_gross': unit_gross,
                    'unit_net': unit_net,
                    'tax_rate': tax_rate,
                    'product_name_snapshot': product.name,
                },
            )
            payment, _ = Payment.objects.update_or_create(
                provider_payment_id=f'{payment_prefix}{suffix.lower()}',
                defaults={
                    'order': order,
                    'provider': 'mollie',
                    'status': 'paid',
                    'amount': gross_total,
                    'currency': price.currency,
                    'method': method,
                    'paid_at': purchased_at,
                    'failed_at': None,
                    'processed_paid': True,
                    'last_provider_payload': {
                        'presentation_demo': True,
                        'scenario': label,
                        'status': 'paid',
                    },
                },
            )
            Order.objects.filter(pk=order.pk).update(created_at=purchased_at)
            OrderItem.objects.filter(pk=item.pk).update(created_at=purchased_at)
            Payment.objects.filter(pk=payment.pk).update(created_at=purchased_at)
            return item

        legacy_at = now - timedelta(days=343)
        base_at = now - timedelta(days=90)
        addon_at = now - timedelta(days=21)
        legacy_item = order_bundle('LEGACY', 1, legacy_at, 'banktransfer', 'older_single_seat')
        base_item = order_bundle('BASE', 7, base_at, 'banktransfer', 'initial_team_purchase')
        addon_item = order_bundle('ADDON', 2, addon_at, 'creditcard', 'two_seats_added_later')

        generated_licenses = License.objects.filter(
            company=company,
            license_number__startswith=license_prefix,
        )
        LicenseAssignment.objects.filter(license__in=generated_licenses).delete()
        DeviceRegistration.objects.filter(license__in=generated_licenses).delete()

        def license_row(index, item, valid_from, valid_until, status='active'):
            number = f'{license_prefix}{index:02d}'
            lic, _ = License.objects.update_or_create(
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
                license=lic,
                order_item=item,
                defaults={
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                    'paid_gross_amount': unit_gross,
                    'status': 'active',
                    'refunded_at': None,
                },
            )
            return lic

        legacy_license = license_row(
            1,
            legacy_item,
            legacy_at,
            now + timedelta(days=22),
        )
        base_valid_until = base_at + timedelta(days=product.default_license_days)
        base_licenses = [
            license_row(index, base_item, base_at, base_valid_until)
            for index in range(2, 9)
        ]
        addon_valid_until = addon_at + timedelta(days=product.default_license_days)
        addon_licenses = [
            license_row(index, addon_item, addon_at, addon_valid_until)
            for index in range(9, 11)
        ]

        assignment_pairs = [
            (base_licenses[0], admin),
            (base_licenses[1], users['member01']),
            (base_licenses[2], users['member02']),
            (base_licenses[3], users['member03']),
            (base_licenses[4], users['member04']),
            (base_licenses[5], users['member05']),
            (legacy_license, users['member06']),
            (addon_licenses[0], users['member09']),
            (addon_licenses[1], users['member10']),
        ]
        for lic, user in assignment_pairs:
            lic.status = 'active'
            lic.save(update_fields=['status', 'updated_at'])
            LicenseAssignment.objects.create(license=lic, user=user)

        spare = base_licenses[6]
        spare.status = 'free'
        spare.save(update_fields=['status', 'updated_at'])

        LicenseReminder.objects.update_or_create(
            license=legacy_license,
            kind='t30',
            target_valid_until=legacy_license.valid_until,
            defaults={
                'status': 'pending',
                'queued_at': None,
                'sent_at': None,
                'error': '',
            },
        )

        LicenseUpgradeRequest.objects.filter(
            company=company,
            product=product,
            user__email__endswith=DEMO_SUFFIX,
            status='pending',
        ).exclude(user=users['member08']).update(status='cancelled', resolved_at=now)
        LicenseUpgradeRequest.objects.update_or_create(
            user=users['member08'],
            product=product,
            status='pending',
            defaults={
                'company': company,
                'note': 'Präsentationsdemo: PRO wird für regelmäßige Copilot-Arbeit benötigt.',
            },
        )

        device_specs = (
            (admin, base_licenses[0], 'Geschäftsführer-Notebook', 'Windows', 'Edge', 1),
            (users['member01'], base_licenses[1], 'Büro-PC', 'Windows', 'Edge', 1),
            (users['member01'], base_licenses[1], 'iPhone', 'iOS', 'Safari', 2),
            (users['member02'], base_licenses[2], 'Notebook', 'Windows', 'Edge', 4),
            (users['member04'], base_licenses[4], 'Surface', 'Windows', 'Edge', 2),
            (users['member06'], legacy_license, 'Arbeitsplatz-PC', 'Windows', 'Chrome', 6),
            (users['member10'], addon_licenses[1], 'Neues Notebook', 'Windows', 'Edge', 1),
        )
        for index, (user, lic, display, os_family, browser_family, hours_ago) in enumerate(device_specs):
            DeviceRegistration.objects.update_or_create(
                token_hash=_token_hash(f'presentation:{company.id}:device:{index}'),
                defaults={
                    'user': user,
                    'license': lic,
                    'display_name': display,
                    'os_family': os_family,
                    'browser_family': browser_family,
                    'last_seen_at': now - timedelta(hours=hours_ago),
                    'revoked_at': None,
                },
            )

        self.stdout.write(self.style.SUCCESS('Präsentationsdemo erfolgreich erstellt.'))
        self.stdout.write(f'Unternehmen: {company.name} ({company.customer_number})')
        self.stdout.write('Benutzer gesamt: 12')
        self.stdout.write('PRO-Nutzer: 9')
        self.stdout.write('Free-Nutzer: 3')
        self.stdout.write('PRO-Lizenzen gekauft: 10')
        self.stdout.write('PRO-Lizenzen zugewiesen: 9')
        self.stdout.write('Freie PRO-Lizenzen: 1')
        self.stdout.write('Nachgebuchte PRO-Lizenzen: 2')
        self.stdout.write('Offene PRO-Anfragen: 1')
        self.stdout.write('E-Mail-Versand: NEIN')
        if credentials:
            self.stdout.write('')
            self.stdout.write('NEU ERZEUGTE DEMO-ZUGÄNGE:')
            for scenario, email, password in credentials:
                self.stdout.write(f'{scenario:22} | {email:48} | {password}')
        else:
            self.stdout.write(
                'Demo-Benutzer bestanden bereits; Passwörter wurden nicht verändert. '
                'Für neue Passwörter --reset-demo-passwords verwenden.'
            )
