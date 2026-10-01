import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.companies.models import Company, Invitation, Membership
from apps.licenses.models import (
    License,
    LicenseAssignment,
    LicenseTerm,
    LicenseUpgradeRequest,
)
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment


CONFIRM_VALUE = 'NETSTYLE-PRESENTATION-DEMO'
CUSTOMER_NUMBER = 'DEMO-NETSTYLE'
ADMIN_EMAIL = 'rspickermann@netstyle.de'

COMPANY = {
    'name': 'netstyle Informationstechnik GmbH',
    'legal_form': 'GmbH',
    'email': 'demo.netstyle@promptmaster.invalid',
    'phone': '',
    'street': 'Am Bühl',
    'house_number': '2',
    'postal_code': '57223',
    'city': 'Kreuztal',
    'country': 'DE',
    'vat_id': 'DE815319970',
    'tax_number': '342/5876/0379',
}

DEMO_PEOPLE = (
    ('Rainer', 'Spickermann', ADMIN_EMAIL),
    ('Anna', 'Becker', 'demo.netstyle.anna.becker@promptmaster.invalid'),
    ('Jonas', 'Roth', 'demo.netstyle.jonas.roth@promptmaster.invalid'),
    ('Lea', 'Sommer', 'demo.netstyle.lea.sommer@promptmaster.invalid'),
    ('Mara', 'Krueger', 'demo.netstyle.mara.krueger@promptmaster.invalid'),
    ('Felix', 'Weber', 'demo.netstyle.felix.weber@promptmaster.invalid'),
    ('Nina', 'Hartmann', 'demo.netstyle.nina.hartmann@promptmaster.invalid'),
    ('David', 'Klein', 'demo.netstyle.david.klein@promptmaster.invalid'),
    ('Sophie', 'Schneider', 'demo.netstyle.sophie.schneider@promptmaster.invalid'),
    ('Lukas', 'Bauer', 'demo.netstyle.lukas.bauer@promptmaster.invalid'),
    ('Miriam', 'Koch', 'demo.netstyle.miriam.koch@promptmaster.invalid'),
    ('Tobias', 'Richter', 'demo.netstyle.tobias.richter@promptmaster.invalid'),
)

# Presentation history: an older single-seat purchase, a seven-seat base purchase
# and a later two-seat add-on. Dates are deliberately synthetic presentation data.
PURCHASES = (
    ('DEMO-NS-O-0001', 1, 300, 'ältere Einzellizenz'),
    ('DEMO-NS-O-0002', 7, 120, '7-Sitz-Basiskauf'),
    ('DEMO-NS-O-0003', 2, 20, 'spätere Nachbuchung +2'),
)


class Command(BaseCommand):
    help = (
        'Erzeugt die separate netstyle-Präsentationsfirma mit 12 aktiven Benutzern, '
        '10 bezahlten PRO-Lizenzen (9 zugewiesen, 1 frei), drei Demo-Bestellungen '
        'und einer offenen PRO-Anfrage. Es werden keine E-Mails und keine echten '
        'Payment-Provider aufgerufen.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--confirm', required=True)
        parser.add_argument(
            '--allow-production-presentation',
            action='store_true',
            help=(
                'Erlaubt die ausschließlich synthetischen Präsentationsdatensätze '
                'auch in ENVIRONMENT=production. Es werden keine Provideraktionen ausgeführt.'
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['confirm'] != CONFIRM_VALUE:
            raise CommandError(
                f'Abbruch. Explizit --confirm {CONFIRM_VALUE} angeben.'
            )
        if (
            settings.ENVIRONMENT == 'production'
            and not options['allow_production_presentation']
        ):
            raise CommandError(
                'Die netstyle-Präsentationsdemo ist in Produktion nur mit '
                '--allow-production-presentation zulässig.'
            )

        now = timezone.now()
        product = Product.objects.filter(code='PRO', active=True).first()
        if product is None:
            raise CommandError('Aktives Produkt PRO fehlt; zuerst seed_defaults ausführen.')
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
            raise CommandError('Aktiver PRO-Neukaufpreis fehlt.')
        tax_rule = TaxRule.objects.filter(
            country='DE',
            customer_type='company',
            active=True,
        ).first()
        tax_rate = tax_rule.tax_rate if tax_rule else Decimal('19.00')

        company, _ = Company.objects.update_or_create(
            customer_number=CUSTOMER_NUMBER,
            defaults={**COMPANY, 'status': 'active'},
        )

        # If an older presentation seed left another company admin behind,
        # deactivate that demo membership before assigning the canonical admin.
        Membership.objects.filter(
            company=company,
            active=True,
            role='admin',
        ).exclude(user__email__iexact=ADMIN_EMAIL).update(active=False)

        users = []
        admin_password = None
        for index, (first_name, last_name, email) in enumerate(DEMO_PEOPLE):
            is_admin = index == 0
            user = User.objects.filter(email__iexact=email).first()
            if user and user.is_staff:
                raise CommandError(
                    f'{email} ist ein interner Staff-Benutzer und darf nicht in die Kunden-Demo übernommen werden.'
                )
            if user:
                foreign_membership = (
                    Membership.objects.filter(user=user, active=True)
                    .exclude(company=company)
                    .select_related('company')
                    .first()
                )
                if foreign_membership:
                    raise CommandError(
                        f'{email} besitzt bereits eine aktive Mitgliedschaft bei '
                        f'{foreign_membership.company.customer_number}.'
                    )
            else:
                user = User(email=email)

            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_staff = False
            user.email_verified_at = now
            user.two_factor_required = is_admin
            if is_admin:
                if not user.pk or not user.has_usable_password():
                    admin_password = 'PmDemo-' + secrets.token_urlsafe(16)
                    user.set_password(admin_password)
                user.totp_secret_enc = ''
                user.last_totp_step = -1
            elif not user.pk:
                user.set_unusable_password()
            user.save()

            Membership.objects.filter(user=user, active=True).exclude(company=company).update(
                active=False
            )
            membership, _ = Membership.objects.update_or_create(
                company=company,
                user=user,
                defaults={
                    'role': 'admin' if is_admin else 'member',
                    'active': True,
                },
            )
            users.append(user)

        keep_ids = [user.pk for user in users]
        Membership.objects.filter(company=company, active=True).exclude(
            user_id__in=keep_ids
        ).update(active=False)
        Invitation.objects.filter(
            company=company,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=now)

        unit_gross = price.gross_amount
        divisor = Decimal('1') + (tax_rate / Decimal('100'))
        unit_net = (unit_gross / divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        cohorts = []
        for number, quantity, age_days, phase in PURCHASES:
            purchased_at = now - timedelta(days=age_days)
            gross_total = (unit_gross * quantity).quantize(Decimal('0.01'))
            net_total = (gross_total / divisor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            tax_total = gross_total - net_total
            order, _ = Order.objects.update_or_create(
                order_number=number,
                defaults={
                    'company': company,
                    'private_user': None,
                    'status': 'paid',
                    'currency': price.currency,
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
                        'tax_number': company.tax_number,
                        'demo': True,
                        'presentation': 'netstyle',
                        'phase': phase,
                    },
                    'idempotency_key': f'demo:netstyle:{number.lower()}',
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
            provider_payment_id = f"tr_demo_netstyle_{number.lower()}"
            Payment.objects.update_or_create(
                provider_payment_id=provider_payment_id,
                defaults={
                    'order': order,
                    'provider': 'mollie',
                    'status': 'paid',
                    'amount': gross_total,
                    'currency': price.currency,
                    'method': 'banktransfer' if number.endswith('0001') else 'creditcard',
                    'paid_at': purchased_at,
                    'failed_at': None,
                    'processed_paid': True,
                    'last_provider_payload': {
                        'demo': True,
                        'presentation': 'netstyle',
                        'phase': phase,
                    },
                },
            )
            Order.objects.filter(pk=order.pk).update(created_at=purchased_at)
            OrderItem.objects.filter(pk=item.pk).update(created_at=purchased_at)
            Payment.objects.filter(
                provider_payment_id=provider_payment_id
            ).update(created_at=purchased_at)
            cohorts.extend([(item, purchased_at)] * quantity)

        if len(cohorts) != 10:
            raise CommandError('Interner Fehler: netstyle-Demo muss exakt 10 Lizenzkohorten erzeugen.')

        license_numbers = [f'PM-DEMO-NS-{index:03d}' for index in range(1, 11)]
        for seat_index, (license_number, cohort) in enumerate(zip(license_numbers, cohorts)):
            item, valid_from = cohort
            valid_until = valid_from + timedelta(days=product.default_license_days)
            license_obj, _ = License.objects.update_or_create(
                license_number=license_number,
                defaults={
                    'company': company,
                    'owner_user': None,
                    'product': product,
                    'status': 'active' if seat_index < 9 else 'free',
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                },
            )
            LicenseTerm.objects.filter(license=license_obj).exclude(
                order_item=item
            ).delete()
            LicenseTerm.objects.update_or_create(
                license=license_obj,
                order_item=item,
                defaults={
                    'valid_from': valid_from,
                    'valid_until': valid_until,
                    'paid_gross_amount': unit_gross,
                    'status': 'active',
                    'refunded_at': None,
                },
            )
            LicenseAssignment.objects.filter(
                license=license_obj,
                ended_at__isnull=True,
            ).delete()
            if seat_index < 9:
                LicenseAssignment.objects.create(
                    license=license_obj,
                    user=users[seat_index],
                )

        License.objects.filter(
            company=company,
            license_number__startswith='PM-DEMO-NS-',
        ).exclude(license_number__in=license_numbers).delete()

        request_user = users[9]
        LicenseUpgradeRequest.objects.filter(
            company=company,
            product=product,
            status='pending',
        ).exclude(user=request_user).update(status='cancelled', resolved_at=now)
        LicenseUpgradeRequest.objects.update_or_create(
            user=request_user,
            product=product,
            status='pending',
            defaults={
                'company': company,
                'note': 'Präsentationsdemo: Free-Benutzer beantragt PromptMaster Pro.',
                'resolved_by': None,
                'resolved_at': None,
                'assigned_license': None,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            'NETSTYLE PRESENTATION DEMO OK: '
            '12 aktive Benutzer · 10 PRO-Lizenzen · 9 zugewiesen · 1 frei · '
            '3 Free-Benutzer · 3 Demo-Bestellungen · 1 offene PRO-Anfrage'
        ))
        self.stdout.write(f'Firmenadmin: {ADMIN_EMAIL}')
        self.stdout.write(
            f"Temporäres Passwort: {admin_password or 'unverändert (bereits gesetzt)'}"
        )
        self.stdout.write('MFA: beim ersten Login erforderlich')
        self.stdout.write('E-Mail-Versand: keiner')
        self.stdout.write('Provider-Aufrufe: keine (nur synthetische Mollie-Demo-Datensätze)')
