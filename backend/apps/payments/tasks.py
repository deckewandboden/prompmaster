import logging

from celery import shared_task

from .mollie import MollieClient
from .services import process_provider_state, reconcile_refunds, record_webhook_failure

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def retry_mollie_payment(self, payment_id):
    """Retry a known failed Mollie webhook through the canonical state machine."""
    try:
        payload = MollieClient().get_payment(payment_id)
        payment = process_provider_state(payment_id, payload)
        reconcile_refunds(payment)
        return {'payment_id': payment_id, 'status': payment.status}
    except Exception as exc:
        record_webhook_failure(payment_id, exc)
        logger.warning('Mollie retry failed for %s; scheduling retry', payment_id)
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 900))
