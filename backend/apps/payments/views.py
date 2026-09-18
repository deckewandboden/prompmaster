import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Payment
from .mollie import MollieClient
from .services import process_provider_state, reconcile_refunds, record_webhook_failure

logger = logging.getLogger(__name__)


@csrf_exempt
def mollie_webhook(request):
    # Mollie webhooks don't carry a Django CSRF token. Authenticity is not
    # trusted from the POST body; the canonical payment is always re-fetched
    # with our server-side API credential before state changes are applied.
    if request.method != 'POST':
        return HttpResponse(status=405)
    payment_id = request.POST.get('id', '').strip()
    if not payment_id or len(payment_id) > 100:
        return HttpResponse(status=400)

    # Never turn an unauthenticated public webhook into an arbitrary Mollie API
    # oracle/amplifier. Only provider IDs already linked to one of our orders
    # are eligible for a canonical provider fetch. A very early legitimate
    # webhook can be retried by Mollie once the local payment row exists.
    if not Payment.objects.filter(provider_payment_id=payment_id).exists():
        return HttpResponse(status=404)

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
    except Exception as exc:
        event = record_webhook_failure(payment_id, exc)
        if event:
            from .tasks import retry_mollie_payment

            retry_mollie_payment.apply_async(args=[payment_id], countdown=30)
        logger.exception('Mollie webhook processing failed for %s', payment_id)
        return HttpResponse(status=500)
    return HttpResponse('OK')
