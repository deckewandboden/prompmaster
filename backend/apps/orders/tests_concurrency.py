import threading
import time
from decimal import Decimal
from unittest import skipUnless

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from apps.accounts.models import User

from .models import Order


@skipUnless(connection.vendor == 'postgresql', 'Concurrency regression requires PostgreSQL row locking.')
class OrderStatusConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        self.user = User.objects.create_user('order-race@example.test', None)
        self.order = Order.objects.create(
            order_number='PM-O-CONCURRENT-PAID-GUARD',
            private_user=self.user,
            status='payment_open',
            currency='EUR',
            gross_total=Decimal('35.88'),
            tax_total=Decimal('5.73'),
            billing_snapshot={'customer_type': 'private'},
            idempotency_key='concurrent-paid-guard',
        )

    def test_stale_non_paid_save_cannot_overwrite_uncommitted_paid_transition(self):
        # Keep a stale in-memory copy from before the provider payment commits.
        stale = Order.objects.get(pk=self.order.pk)
        paid_written = threading.Event()
        release_paid = threading.Event()
        failures = []

        def provider_commit():
            close_old_connections()
            try:
                with transaction.atomic():
                    current = Order.objects.select_for_update().get(pk=self.order.pk)
                    current.status = 'paid'
                    current.save(update_fields=['status', 'updated_at'])
                    paid_written.set()
                    if not release_paid.wait(timeout=5):
                        raise AssertionError('test synchronization timeout')
            except Exception as exc:  # pragma: no cover - surfaced below
                failures.append(exc)
            finally:
                close_old_connections()

        def stale_checkout_write():
            close_old_connections()
            try:
                stale.status = 'failed'
                stale.save(update_fields=['status', 'updated_at'])
            except Exception as exc:  # pragma: no cover - surfaced below
                failures.append(exc)
            finally:
                close_old_connections()

        paid_thread = threading.Thread(target=provider_commit, daemon=True)
        paid_thread.start()
        self.assertTrue(paid_written.wait(timeout=5))

        stale_thread = threading.Thread(target=stale_checkout_write, daemon=True)
        stale_thread.start()

        # Give the stale writer time to reach the locked order row. Under the
        # former read-then-save implementation its non-locking SELECT completed
        # here and its UPDATE waited, then overwrote `paid` after release.
        time.sleep(0.25)
        release_paid.set()

        paid_thread.join(timeout=5)
        stale_thread.join(timeout=5)
        self.assertFalse(paid_thread.is_alive())
        self.assertFalse(stale_thread.is_alive())
        self.assertEqual(failures, [])

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
