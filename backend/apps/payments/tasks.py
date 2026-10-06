import logging

from celery import shared_task
from django.db.models import Q

from .mollie import MollieClient
from .services import process_provider_state, reconcile_refunds, record_webhook_failure

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def retry_mollie_payment(self, payment_id):
    """Retry a known failed Mollie webhook through the canonical state machine."""
    try:
        client = MollieClient()
        payload = client.get_payment(payment_id)
        chargebacks = client.list_chargebacks(payment_id)
        payment = process_provider_state(
            payment_id,
            payload,
            chargebacks_payload=chargebacks,
        )
        reconcile_refunds(payment)
        return {'payment_id': payment_id, 'status': payment.status}
    except Exception as exc:
        record_webhook_failure(payment_id, exc)
        logger.warning('Mollie retry failed for %s; scheduling retry', payment_id)
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 900))


@shared_task
def reconcile_mollie_unsettled_states(limit=100):
    """Reconcile only payment states that can remain unresolved without a webhook.

    Classic payment webhooks reliably notify us about the initial chargeback and
    refund changes, but recovery must not depend on a later delivery. A narrow
    periodic sweep covers active chargebacks and locally submitted refunds.
    """
    limit = max(1, min(int(limit or 100), 500))
    payment_ids = list(
        Payment.objects.filter(
            Q(status='chargeback')
            | Q(refunds__status='submitted')
        )
        .distinct()
        .order_by('updated_at')
        .values_list('provider_payment_id', flat=True)[:limit]
    )
    if not payment_ids:
        return {'scanned': 0, 'updated': 0, 'errors': 0}

    client = MollieClient()
    updated = 0
    errors = 0
    for payment_id in payment_ids:
        try:
            payload = client.get_payment(payment_id)
            chargebacks = client.list_chargebacks(payment_id)
            payment = process_provider_state(
                payment_id,
                payload,
                chargebacks_payload=chargebacks,
            )
            reconcile_refunds(payment)
            updated += 1
        except Exception as exc:
            record_webhook_failure(payment_id, exc)
            errors += 1
            logger.warning(
                'Periodic Mollie reconciliation failed for %s',
                payment_id,
                exc_info=True,
            )
    return {
        'scanned': len(payment_ids),
        'updated': updated,
        'errors': errors,
    }
