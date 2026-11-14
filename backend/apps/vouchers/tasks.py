"""Safe periodic reconciliation of long-unsettled voucher reservations.

Never releases a voucher on age or absence of a payment alone. Only provider
canonical terminal state can cause quota release through process_provider_state.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.payments.mollie import MollieClient
from apps.payments.models import Payment
from apps.payments.services import process_provider_state, record_webhook_failure

logger = logging.getLogger(__name__)


@shared_task
def reconcile_reserved_voucher_payments(limit=50, min_age_minutes=60):
    """Check old reserved payments at the provider without creating new payments."""
    limit = max(1, min(int(limit or 50), 100))
    min_age_minutes = max(30, min(int(min_age_minutes or 60), 10080))
    cutoff = timezone.now() - timedelta(minutes=min_age_minutes)

    pending_ids = list(
        Payment.objects.filter(
            order__voucher_redemption__status="reserved",
            order__voucher_redemption__created_at__lte=cutoff,
        )
        .exclude(provider_payment_id="")
        .order_by("created_at")
        .values_list("provider_payment_id", flat=True)[:limit]
    )
    if not pending_ids:
        return {"scanned": 0, "reconciled": 0, "errors": 0}

    client = MollieClient()
    processed = 0
    errors = 0
    for payment_id in pending_ids:
        try:
            payload = client.get_payment(payment_id)
            chargebacks = client.list_chargebacks(payment_id)
            process_provider_state(
                payment_id, payload, chargebacks_payload=chargebacks,
            )
            processed += 1
        except Exception as exc:
            # Preserve the reservation if the provider cannot confirm state.
            record_webhook_failure(payment_id, exc)
            errors += 1
            logger.warning(
                "Voucher reservation payment reconciliation failed for %s",
                payment_id, exc_info=True,
            )
    return {"scanned": len(pending_ids), "reconciled": processed, "errors": errors}
