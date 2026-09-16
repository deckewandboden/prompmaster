from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Min, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.services import audit
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order
from .models import MollieEvent, Payment, Refund
from .mollie import MollieClient

CENT = Decimal('0.01')
STATUS_MAP = {
    'created': 'created',
    'open': 'open',
    'pending': 'pending',
    'authorized': 'authorized',
    'paid': 'paid',
    'failed': 'failed',
    'canceled': 'canceled',
    'expired': 'expired',
    'charged_back': 'chargeback',
}


def _provider_amount(payload):
    data = payload.get('amount') or {}
    try:
        value = Decimal(str(data.get('value'))).quantize(CENT)
    except Exception as exc:
        raise ValidationError('Ungültiger Zahlungsbetrag vom Zahlungsanbieter.') from exc
    currency = str(data.get('currency') or '').upper()
    return value, currency


def _provider_refunded_amount(payload):
    data = payload.get('amountRefunded') or {}
    raw = data.get('value')
    if raw in (None, ''):
        return Decimal('0.00')
    try:
        return Decimal(str(raw)).quantize(CENT)
    except Exception as exc:
        raise ValidationError('Ungültiger Erstattungsbetrag vom Zahlungsanbieter.') from exc


def _provider_paid_at(payload):
    raw = str(payload.get('paidAt') or '')
    parsed = parse_datetime(raw) if raw else None
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed or timezone.now()


def _order_recipient(order):
    if order.private_user_id:
        return order.private_user.email if order.private_user and order.private_user.is_active else ''
    if order.company_id:
        from apps.companies.models import Membership
        membership = (
            Membership.objects.filter(company_id=order.company_id, role='admin', active=True)
            .select_related('user').first()
        )
        if membership and membership.user.is_active:
            return membership.user.email
    return ''


def _queue_after_commit(code, recipient, context):
    if not recipient:
        return
    def send():
        from apps.notifications.services import queue_email
        queue_email(code, recipient, context)
    transaction.on_commit(send, robust=True)


def _license_state_from_assignments(license_obj, now):
    if not license_obj.valid_until or license_obj.valid_until <= now:
        return 'expired'
    assigned = LicenseAssignment.objects.filter(license=license_obj, ended_at__isnull=True).exists()
    return 'active' if assigned else 'free'


def _locked_order_licenses(order, *, active_terms_only=False):
    """Lock licenses touched by an order without FOR UPDATE + DISTINCT.

    PostgreSQL rejects SELECT DISTINCT ... FOR UPDATE. Resolve the unique
    license IDs first, then lock the concrete License rows in a second query.
    """
    terms = LicenseTerm.objects.filter(order_item__order=order)
    if active_terms_only:
        terms = terms.filter(status='active')
    license_ids = list(terms.values_list('license_id', flat=True).distinct())
    if not license_ids:
        return License.objects.none()
    return License.objects.select_for_update().filter(pk__in=license_ids).order_by('pk')


@transaction.atomic
def process_provider_state(payment_id, payload):
    # Lock only the payment row. Joining nullable order owners here would make
    # PostgreSQL apply FOR UPDATE to the nullable side of LEFT OUTER JOINs,
    # which PostgreSQL rejects. Related order/customer data is read separately;
    # _activate_order obtains its own row lock before mutating the order.
    payment = Payment.objects.select_for_update().get(provider_payment_id=payment_id)
    order = Order.objects.select_related('private_user', 'company').get(pk=payment.order_id)
    payment.order = order
    provider_amount, provider_currency = _provider_amount(payload)
    if provider_amount != payment.amount.quantize(CENT) or provider_currency != payment.currency.upper():
        raise ValidationError('Mollie-Betrag oder Währung stimmen nicht mit der Bestellung überein.')
    if payment.order.gross_total.quantize(CENT) != payment.amount.quantize(CENT) or payment.order.currency.upper() != payment.currency.upper():
        raise ValidationError('Interne Bestell- und Zahlungsbeträge stimmen nicht überein.')
    previous_status = payment.status
    provider_status = str(payload.get('status') or 'unknown')[:40]
    base_status = STATUS_MAP.get(provider_status, 'unknown')
    refunded_amount = _provider_refunded_amount(payload)
    refunded = (payload.get('amountRefunded') or {}).get('value', '')
    remaining = (payload.get('amountRemaining') or {}).get('value', '')
    status = base_status
    if base_status == 'paid' and refunded_amount > 0:
        status = 'refunded_full' if refunded_amount >= payment.amount.quantize(CENT) else 'refunded_partial'
    elif base_status == 'paid' and previous_status in {'chargeback', 'charged_back', 'chargeback_reversed'}:
        # Mollie's payment endpoint returns to a paid state after a reversed
        # chargeback. Preserve that business transition as its own internal
        # state and keep it stable across duplicate webhook deliveries.
        status = 'chargeback_reversed'

    # Canonical provider/business state plus refund amounts is the idempotency
    # key. Including previous_status would create one extra event on the first
    # duplicate delivery after every legitimate transition.
    event_key = f'{payment_id}:{status}:{refunded}:{remaining}'[:180]
    event, _ = MollieEvent.objects.get_or_create(
        payment=payment,
        event_key=event_key,
        defaults={'provider_status': status},
    )

    payment.status = status
    payment.method = str(payload.get('method') or '')[:50]
    payment.last_provider_payload = payload

    if base_status == 'paid':
        if not payment.processed_paid:
            payment.paid_at = payment.paid_at or _provider_paid_at(payload)
            _activate_order(payment.order, payment.paid_at)
            payment.processed_paid = True
            recipient = _order_recipient(payment.order)
            _queue_after_commit('payment_confirmed', recipient, {
                'order': payment.order.order_number,
                'amount': f'{payment.amount:.2f}',
                'currency': payment.currency,
            })
            for item in payment.order.items.select_related('target_license').filter(target_license__isnull=False):
                target = item.target_license
                _queue_after_commit('license_renewed', recipient, {
                    'license': target.license_number,
                    'expiry': timezone.localtime(target.valid_until).strftime('%d.%m.%Y'),
                })
        else:
            # A previously charged-back payment may become paid again after a
            # reversal. Re-enable only licenses that still have paid active
            # terms; refunded terms remain excluded.
            now = timezone.now()
            for license_obj in _locked_order_licenses(payment.order):
                has_terms = license_obj.terms.filter(status='active', valid_until__gt=now).exists()
                if has_terms and license_obj.status == 'payment_review':
                    license_obj.status = _license_state_from_assignments(license_obj, now)
                    license_obj.save(update_fields=['status', 'updated_at'])
                    audit(None, 'license.chargeback_reversed', license_obj, {'payment': payment.provider_payment_id})
    elif base_status in {'failed', 'canceled', 'expired'} and payment.order.status != 'paid':
        payment.order.status = 'canceled' if base_status == 'canceled' else 'failed'
        payment.order.save(update_fields=['status', 'updated_at'])
        if previous_status != status:
            _queue_after_commit('payment_failed', _order_recipient(payment.order), {
                'order': payment.order.order_number, 'status': base_status,
            })
    elif base_status == 'chargeback':
        if previous_status not in {'chargeback', 'charged_back'}:
            _queue_after_commit('chargeback_review', _order_recipient(payment.order), {'order': payment.order.order_number})
        for license_obj in _locked_order_licenses(payment.order, active_terms_only=True):
            if license_obj.status != 'payment_review':
                license_obj.status = 'payment_review'
                license_obj.save(update_fields=['status', 'updated_at'])
                audit(None, 'license.chargeback_review', license_obj, {'payment': payment.provider_payment_id})

    payment.save(
        update_fields=[
            'status',
            'method',
            'last_provider_payload',
            'paid_at',
            'processed_paid',
            'updated_at',
        ]
    )
    event.provider_status = status
    event.processed_at = timezone.now()
    event.error = ''
    # Avoid QuerySet.update on audit only; normal event rows are mutable retry logs.
    event.save(update_fields=['provider_status', 'processed_at', 'error', 'updated_at'])
    MollieEvent.objects.filter(payment=payment, event_key=f'{payment_id}:webhook-error').update(
        error='', processed_at=timezone.now(), provider_status='recovered', updated_at=timezone.now()
    )
    return payment


def record_webhook_failure(payment_id, exc):
    """Persist a sanitised retry/error signal for known Mollie payments."""
    payment = Payment.objects.filter(provider_payment_id=payment_id).first()
    if not payment:
        return None
    safe_error = f'{type(exc).__name__}: webhook processing failed'[:500]
    with transaction.atomic():
        event, _ = MollieEvent.objects.select_for_update().get_or_create(
            payment=payment,
            event_key=f'{payment_id}:webhook-error',
            defaults={'provider_status': 'error'},
        )
        event.provider_status = 'error'
        event.error = safe_error
        event.retry_count += 1
        event.processed_at = None
        event.save(update_fields=['provider_status', 'error', 'retry_count', 'processed_at', 'updated_at'])
    return event


def _activate_order(order, paid_at):
    order = type(order).objects.select_for_update().get(pk=order.pk)
    if order.status == 'paid':
        return

    for item in order.items.select_related('product', 'target_license').all():
        if item.target_license_id:
            license_obj = License.objects.select_for_update().get(pk=item.target_license_id)
            start = license_obj.valid_until if license_obj.valid_until and license_obj.valid_until > paid_at else paid_at
            end = start + timedelta(days=item.product.default_license_days)
            LicenseTerm.objects.create(
                license=license_obj,
                order_item=item,
                valid_from=start,
                valid_until=end,
                paid_gross_amount=item.unit_gross,
            )
            if not license_obj.valid_from:
                license_obj.valid_from = start
            license_obj.valid_until = end
            license_obj.status = _license_state_from_assignments(license_obj, paid_at)
            license_obj.save(update_fields=['valid_from', 'valid_until', 'status', 'updated_at'])
        else:
            for _ in range(item.quantity):
                start = paid_at
                end = start + timedelta(days=item.product.default_license_days)
                license_obj = License.objects.create(
                    company=order.company,
                    owner_user=order.private_user,
                    product=item.product,
                    status='free' if order.company_id else 'active',
                    valid_from=start,
                    valid_until=end,
                )
                LicenseTerm.objects.create(
                    license=license_obj,
                    order_item=item,
                    valid_from=start,
                    valid_until=end,
                    paid_gross_amount=item.unit_gross,
                )
                if order.private_user_id:
                    LicenseAssignment.objects.create(license=license_obj, user=order.private_user)

    order.status = 'paid'
    order.save(update_fields=['status', 'updated_at'])


def calculate_refund(term, today=None):
    """Return unused whole calendar days and the pro-rata gross refund.

    A future prepaid term is capped at its purchased 365-day duration, so a
    renewal bought early can never produce a refund greater than its price.
    """
    today = today or timezone.localdate()
    start_date = timezone.localtime(term.valid_from).date()
    end_date = timezone.localtime(term.valid_until).date()
    total_days = max((end_date - start_date).days, 0)
    if today <= start_date:
        remaining = total_days
    elif today >= end_date:
        remaining = 0
    else:
        remaining = (end_date - today).days
    remaining = max(0, min(remaining, total_days, 365))
    amount = (
        term.paid_gross_amount * Decimal(remaining) / Decimal(365)
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    return remaining, amount


def _recalculate_license_after_refund(license_obj, now):
    active_terms = license_obj.terms.filter(status='active')
    bounds = active_terms.aggregate(start=Min('valid_from'), end=Max('valid_until'))
    if not bounds['end']:
        license_obj.valid_from = None
        license_obj.valid_until = now
        license_obj.status = 'refunded'
        LicenseAssignment.objects.filter(license=license_obj, ended_at__isnull=True).update(ended_at=now)
        DeviceRegistration.objects.filter(license=license_obj, revoked_at__isnull=True).update(revoked_at=now)
    else:
        license_obj.valid_from = bounds['start']
        license_obj.valid_until = bounds['end']
        currently_covered = active_terms.filter(valid_from__lte=now, valid_until__gt=now).exists()
        if currently_covered:
            license_obj.status = _license_state_from_assignments(license_obj, now)
        else:
            license_obj.status = 'expired'
            # A future prepaid term may remain. Access stays off until its
            # valid_from date; no term dates are silently shifted.
            LicenseAssignment.objects.filter(license=license_obj, ended_at__isnull=True).update(ended_at=now)
            DeviceRegistration.objects.filter(license=license_obj, revoked_at__isnull=True).update(revoked_at=now)
    license_obj.save(update_fields=['valid_from', 'valid_until', 'status', 'updated_at'])


@transaction.atomic
def create_refund_request(*, term, actor, reason=''):
    locked = LicenseTerm.objects.select_for_update().select_related(
        'license', 'order_item__order'
    ).get(pk=term.pk)
    if locked.status != 'active':
        raise ValidationError('Diese Lizenzperiode wurde bereits beendet oder refundiert.')
    if locked.license.status in {'blocked', 'payment_review', 'refunded'}:
        raise ValidationError('Diese Lizenz kann derzeit nicht erstattet werden.')

    latest = locked.license.terms.filter(status='active').order_by('-valid_until').first()
    if latest and latest.pk != locked.pk:
        raise ValidationError('Zuerst muss die zuletzt gekaufte Lizenzperiode refundiert werden.')

    remaining_days, amount = calculate_refund(locked)
    if remaining_days <= 0 or amount <= 0:
        raise ValidationError('Für diese Lizenzperiode besteht kein erstattungsfähiger Restzeitraum.')

    payment = (
        Payment.objects.filter(order=locked.order_item.order, status__in=['paid', 'refunded_partial'])
        .order_by('-paid_at', '-created_at')
        .first()
    )
    if not payment:
        raise ValidationError('Keine bestätigte Mollie-Zahlung für diese Lizenzperiode gefunden.')

    refund, created = Refund.objects.get_or_create(
        term=locked,
        defaults={
            'payment': payment,
            'amount': amount,
            'remaining_days': remaining_days,
            'reason': reason.strip()[:2000],
        },
    )
    if not created and refund.status in {'submitted', 'succeeded'}:
        raise ValidationError('Für diese Lizenzperiode wurde bereits eine Erstattung ausgelöst.')
    audit(actor, 'refund.created', refund, {'amount': str(amount), 'remaining_days': remaining_days})
    return refund


def submit_refund(refund):
    # No database transaction is held while waiting for the external provider.
    response = MollieClient().create_refund(
        refund.payment.provider_payment_id,
        refund.amount,
        refund.payment.currency,
        f'PromptMaster Erstattung {refund.term.license.license_number}',
        f'refund:{refund.id}',
    )
    refund.provider_refund_id = response.get('id') or refund.provider_refund_id
    status = str(response.get('status') or 'pending')
    refund.status = 'succeeded' if status == 'refunded' else 'submitted'
    refund.save(update_fields=['provider_refund_id', 'status', 'updated_at'])
    if refund.status == 'succeeded':
        mark_refund_success(refund, refund.provider_refund_id)
    return refund


@transaction.atomic
def mark_refund_success(refund, provider_id):
    row = Refund.objects.select_for_update().select_related('term__license').get(pk=refund.pk)
    if row.status == 'succeeded' and row.term.status == 'refunded':
        return row
    row.provider_refund_id = provider_id or row.provider_refund_id
    row.status = 'succeeded'
    row.save(update_fields=['provider_refund_id', 'status', 'updated_at'])

    payment = Payment.objects.select_for_update().get(pk=row.payment_id)
    refunded_total = payment.refunds.filter(status='succeeded').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if payment.status not in {'chargeback', 'charged_back'}:
        desired_payment_status = 'refunded_full' if refunded_total >= payment.amount else 'refunded_partial'
        if payment.status != desired_payment_status:
            payment.status = desired_payment_status
            payment.save(update_fields=['status', 'updated_at'])

    term = LicenseTerm.objects.select_for_update().get(pk=row.term_id)
    if term.status != 'refunded':
        term.status = 'refunded'
        term.refunded_at = timezone.now()
        term.save(update_fields=['status', 'refunded_at', 'updated_at'])

    license_obj = License.objects.select_for_update().get(pk=term.license_id)
    _recalculate_license_after_refund(license_obj, timezone.now())
    audit(None, 'refund.succeeded', row, {'amount': str(row.amount), 'term': str(term.id), 'license': str(license_obj.id)})
    order = row.payment.order
    _queue_after_commit('refund_confirmed', _order_recipient(order), {
        'amount': f'{row.amount:.2f}', 'currency': row.payment.currency, 'license': license_obj.license_number,
    })
    return row


def reconcile_refunds(payment):
    """Reconcile submitted refunds using Mollie's canonical refund list."""
    pending = list(payment.refunds.filter(status='submitted').exclude(provider_refund_id__isnull=True))
    if not pending:
        return 0
    payload = MollieClient().list_refunds(payment.provider_payment_id)
    rows = (payload.get('_embedded') or {}).get('refunds') or []
    by_id = {row.get('id'): row for row in rows if row.get('id')}
    count = 0
    for refund in pending:
        provider = by_id.get(refund.provider_refund_id)
        if provider and provider.get('status') == 'refunded':
            mark_refund_success(refund, refund.provider_refund_id)
            count += 1
        elif provider and provider.get('status') in {'failed', 'canceled'}:
            refund.status = 'failed'
            refund.save(update_fields=['status', 'updated_at'])
    return count
