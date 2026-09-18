import math
import time
from statistics import mean

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog.models import Product
from apps.companies.models import Company
from apps.licenses.models import License
from apps.orders.models import Order
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Misst repräsentative 100k-DataGrid-Abfragen gegen die Staging-Datenbank.'

    def add_arguments(self, parser):
        parser.add_argument('--prefix', default='PMPERF')
        parser.add_argument('--min-rows', type=int, default=100000)
        parser.add_argument('--iterations', type=int, default=20)
        parser.add_argument('--max-ms', type=float, default=500.0)

    @staticmethod
    def _p95(values):
        ordered = sorted(values)
        return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]

    def _measure(self, name, callback, iterations, max_ms):
        callback()
        samples = []
        for _ in range(iterations):
            started = time.perf_counter()
            callback()
            samples.append((time.perf_counter() - started) * 1000)
        p95 = self._p95(samples)
        avg = mean(samples)
        self.stdout.write(f'{name}: avg={avg:.1f}ms p95={p95:.1f}ms max={max(samples):.1f}ms')
        if p95 > max_ms:
            raise CommandError(f'{name}: p95 {p95:.1f}ms überschreitet Ziel {max_ms:.1f}ms')
        return p95

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'production':
            raise CommandError('Performance-Smoke ist gegen Production gesperrt; Staging verwenden.')

        prefix = str(options['prefix']).strip().upper()
        min_rows = options['min_rows']
        iterations = options['iterations']
        max_ms = options['max_ms']
        if min_rows < 1:
            raise CommandError('--min-rows muss positiv sein.')
        if iterations < 5 or iterations > 100:
            raise CommandError('--iterations muss zwischen 5 und 100 liegen.')
        if max_ms <= 0:
            raise CommandError('--max-ms muss positiv sein.')

        product = Product.objects.filter(code=f'{prefix}-PRO').first()
        if not product:
            raise CommandError('Performance-Produkt fehlt. Zuerst seed_performance ausführen.')

        counts = {
            'companies': Company.objects.filter(customer_number__startswith=f'{prefix}-C-').count(),
            'orders': Order.objects.filter(order_number__startswith=f'{prefix}-O-').count(),
            'licenses': License.objects.filter(license_number__startswith=f'{prefix}-L-').count(),
            'payments': Payment.objects.filter(provider_payment_id__startswith=f'tr_{prefix.lower()}_').count(),
        }
        if any(value < min_rows for value in counts.values()):
            raise CommandError(f'Mindestens {min_rows} synthetische Zeilen je Kernliste erforderlich: {counts}')
        self.stdout.write(f'Dataset: {counts}')

        midpoint = max(1, min_rows // 2)
        suffix = f'{midpoint:07d}'
        deep_offset = min_rows // 2

        def company_deep_page():
            list(
                Company.objects.filter(customer_number__startswith=f'{prefix}-C-')
                .order_by('name', 'id')[deep_offset:deep_offset + 50]
            )

        def company_search():
            query = Company.objects.filter(
                Q(customer_number__icontains=suffix)
                | Q(name__icontains=suffix)
                | Q(email__icontains=suffix)
            ).order_by('name', 'id')
            query.count()
            list(query[:50])

        def license_grid():
            query = License.objects.filter(product=product, status='active').order_by('valid_until', 'license_number')
            query.count()
            list(query[:50])

        def order_search():
            query = Order.objects.filter(order_number__icontains=f'{prefix}-O-{suffix}').order_by('-created_at', 'id')
            query.count()
            list(query[:50])

        def payment_search():
            query = Payment.objects.filter(
                provider_payment_id__icontains=f'tr_{prefix.lower()}_{suffix}'
            ).order_by('-created_at', 'id')
            query.count()
            list(query[:50])

        results = {
            'company_deep_page': self._measure('company_deep_page', company_deep_page, iterations, max_ms),
            'company_search': self._measure('company_search', company_search, iterations, max_ms),
            'license_grid': self._measure('license_grid', license_grid, iterations, max_ms),
            'order_search': self._measure('order_search', order_search, iterations, max_ms),
            'payment_search': self._measure('payment_search', payment_search, iterations, max_ms),
        }
        self.stdout.write(self.style.SUCCESS(f'PERFORMANCE SMOKE OK: {results}'))
