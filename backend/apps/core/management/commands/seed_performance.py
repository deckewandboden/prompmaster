import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import Product
from apps.companies.models import Company
from apps.licenses.models import License
from apps.orders.models import Order
from apps.payments.models import Payment


NAMESPACE = uuid.UUID('5c773e42-f1c9-4c3b-9292-0f2c1e3f9d90')
DEFAULT_PREFIX = 'PMPERF'


def stable_uuid(kind, number):
    return uuid.uuid5(NAMESPACE, f'{kind}:{number}')


class Command(BaseCommand):
    help = 'Erzeugt deterministische synthetische Lastdaten für Staging-Performanceprüfungen.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100000)
        parser.add_argument('--batch-size', type=int, default=2000)
        parser.add_argument('--prefix', default=DEFAULT_PREFIX)

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'production':
            raise CommandError('Performance-Seeding ist in Production grundsätzlich gesperrt.')

        count = options['count']
        batch_size = options['batch_size']
        prefix = str(options['prefix']).strip().upper()
        if count < 1 or count > 1_000_000:
            raise CommandError('--count muss zwischen 1 und 1.000.000 liegen.')
        if batch_size < 100 or batch_size > 10000:
            raise CommandError('--batch-size muss zwischen 100 und 10.000 liegen.')
        if not prefix or len(prefix) > 12 or not prefix.replace('-', '').isalnum():
            raise CommandError('--prefix muss kurz und alphanumerisch sein.')

        product, _ = Product.objects.get_or_create(
            code=f'{prefix}-PRO',
            defaults={
                'name': 'Synthetic Performance Product',
                'description': 'Ausschließlich synthetische Staging-Lastdaten.',
                'default_license_days': 365,
                'default_device_limit': 2,
                'reminder_1_days': 60,
                'reminder_2_days': 30,
                'critical_warning_days': 7,
            },
        )
        now = timezone.now()

        for start in range(1, count + 1, batch_size):
            stop = min(start + batch_size, count + 1)
            numbers = range(start, stop)

            companies = []
            orders = []
            licenses = []
            payments = []
            for number in numbers:
                suffix = f'{number:07d}'
                company_id = stable_uuid('company', number)
                order_id = stable_uuid('order', number)
                license_id = stable_uuid('license', number)

                companies.append(
                    Company(
                        id=company_id,
                        customer_number=f'{prefix}-C-{suffix}',
                        name=f'Performance Firma {suffix}',
                        email=f'perf-{suffix}@example.invalid',
                        city='Synthetic',
                        country='DE',
                    )
                )

                gross = Decimal('35.88')
                orders.append(
                    Order(
                        id=order_id,
                        order_number=f'{prefix}-O-{suffix}',
                        company_id=company_id,
                        status='paid' if number % 5 else 'payment_open',
                        currency='EUR',
                        gross_total=gross,
                        tax_total=Decimal('5.73'),
                        billing_snapshot={'synthetic': True, 'dataset': prefix},
                        idempotency_key=f'{prefix.lower()}-order-{suffix}',
                    )
                )

                if number % 7 == 0:
                    license_status = 'expired'
                    valid_from = now - timedelta(days=400)
                    valid_until = now - timedelta(days=35)
                else:
                    license_status = 'active' if number % 3 else 'free'
                    valid_from = now - timedelta(days=180)
                    valid_until = now + timedelta(days=185)
                licenses.append(
                    License(
                        id=license_id,
                        license_number=f'{prefix}-L-{suffix}',
                        company_id=company_id,
                        product_id=product.id,
                        status=license_status,
                        valid_from=valid_from,
                        valid_until=valid_until,
                    )
                )

                payment_status = 'paid' if number % 5 else 'open'
                payments.append(
                    Payment(
                        id=stable_uuid('payment', number),
                        order_id=order_id,
                        provider='mollie',
                        provider_payment_id=f'tr_{prefix.lower()}_{suffix}',
                        status=payment_status,
                        amount=gross,
                        currency='EUR',
                        method='synthetic',
                        paid_at=now if payment_status == 'paid' else None,
                        processed_paid=(payment_status == 'paid'),
                        last_provider_payload={'synthetic': True},
                    )
                )

            Company.objects.bulk_create(companies, batch_size=batch_size, ignore_conflicts=True)
            Order.objects.bulk_create(orders, batch_size=batch_size, ignore_conflicts=True)
            License.objects.bulk_create(licenses, batch_size=batch_size, ignore_conflicts=True)
            Payment.objects.bulk_create(payments, batch_size=batch_size, ignore_conflicts=True)
            self.stdout.write(f'{stop - 1}/{count} synthetische Datensätze je Kernliste vorbereitet')

        summary = {
            'companies': Company.objects.filter(customer_number__startswith=f'{prefix}-C-').count(),
            'orders': Order.objects.filter(order_number__startswith=f'{prefix}-O-').count(),
            'licenses': License.objects.filter(license_number__startswith=f'{prefix}-L-').count(),
            'payments': Payment.objects.filter(provider_payment_id__startswith=f'tr_{prefix.lower()}_').count(),
        }
        if any(value < count for value in summary.values()):
            raise CommandError(f'Performance-Seeding unvollständig: {summary}')
        self.stdout.write(self.style.SUCCESS(f'Performance-Dataset bereit: {summary}'))
