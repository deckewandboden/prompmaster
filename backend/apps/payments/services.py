from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Min, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit.services import audit
from apps.accounts.security import bump_security_version
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order
from .models import MollieEvent, Payment, Refund, RefundAttempt
from .mollie import MollieClient, MollieError

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


def _queue_after_commit(code, recipient, context, *, order=None):
    if not recipient:
        return

    def send():
        from apps.notifications.services import queue_email
        queue_email(
            code,
            recipient,
            context,
            scope_company=(order.company_id if order and order.company_id else None),
            scope_user=(order.private_user_id if order and order.private_user_id else None),
        )

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
        # Mollie reports a reversed chargeback as paid again. Preserve that
        # transition as its own internal state instead of collapsing it back
        # to the original paid state.
        status = 'chargeback_reversed'

    # Canonical provider result is the idempotency key. The previous internal
    # state must not be part of the key: otherwise a duplicate paid webhook
    # would create open->paid and paid->paid as two different events. A
    # chargeback reversal remains distinct because its canonical status is
    # chargeback_reversed.
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
            }, order=payment.order)
            for item in payment.order.items.select_related('target_license').filter(target_license__isnull=False):
                target = item.target_license
                _queue_after_commit('license_renewed', recipient, {
                    'license': target.license_number,
                    'expiry': timezone.localtime(target.valid_until).strftime('%d.%m.%Y'),
                }, order=payment.order)
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
        payment.failed_at = payment.failed_at or timezone.now()
        payment.order.status = 'canceled' if base_status == 'canceled' else 'failed'
        payment.order.save(update_fields=['status', 'updated_at'])
        if previous_status != status:
            _queue_after_commit('payment_failed', _order_recipient(payment.order), {
                'order': payment.order.order_number, 'status': base_status,
            }, order=payment.order)
    elif base_status == 'chargeback':
        if previous_status not in {'chargeback', 'charged_back'}:
            _queue_after_commit(
                'chargeback_review',
                _order_recipient(payment.order),
                {'order': payment.order.order_number},
                order=payment.order,
            )
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
            'failed_at',
            'processed_paid',
            'updated_at',
        ]
    )
    event.provider_status = status
    event.processed_at = timezone.now()
    event.error = ''
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


def _terminate_license_access(license_obj, now):
    """End active assignment credentials and invalidate existing sessions."""
    assignments = list(
        LicenseAssignment.objects.select_for_update()
        .filter(license=license_obj, ended_at__isnull=True)
        .select_related('user')
    )
    for assignment in assignments:
        assignment.ended_at = now
        assignment.save(update_fields=['ended_at'])
        bump_security_version(assignment.user)
    DeviceRegistration.objects.filter(
        license=license_obj, revoked_at__isnull=True
    ).update(revoked_at=now)


def _recalculate_license_after_refund(license_obj, now):
    active_terms = license_obj.terms.filter(status='active')
    bounds = active_terms.aggregate(start=Min('valid_from'), end=Max('valid_until'))
    if not bounds['end']:
        # No active paid period remains. Keep the historical dates on
        # LicenseTerm rows and clear the denormalised current window together;
        # the License constraint only permits both null or a strictly ordered
        # valid_from/valid_until pair.
        license_obj.valid_from = None
        license_obj.valid_until = None
        license_obj.status = 'refunded'
        _terminate_license_access(license_obj, now)
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
            _terminate_license_access(license_obj, now)
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
        Payment.objects.filter(
            order=locked.order_item.order,
            status__in=['paid', 'chargeback_reversed', 'refunded_partial'],
        )
        .order_by('-paid_at', '-created_at')
        .first()
    )
    if not payment:
        raise ValidationError('Keine bestätigte Mollie-Zahlung für diese Lizenzperiode gefunden.')

    refund = Refund.objects.select_for_update().filter(term=locked).first()
    if refund is None:
        refund = Refund.objects.create(
            term=locked,
            payment=payment,
            amount=amount,
            remaining_days=remaining_days,
            reason=reason.strip()[:2000],
        )
        audit(
            actor,
            'refund.created',
            refund,
            {'amount': str(amount), 'remaining_days': remaining_days},
        )
        return refund

    if refund.status == 'succeeded':
        raise ValidationError('Für diese Lizenzperiode wurde bereits eine Erstattung abgeschlossen.')
    if refund.status == 'submitted':
        # In-flight or ambiguous provider attempts must retain their original
        # quote and idempotency key. Requoting here could desynchronise the
        # local amount from a request Mollie may already have accepted.
        audit(
            actor,
            'refund.retry_requested',
            refund,
            {'status': refund.status, 'attempts': refund.attempts.count()},
        )
        return refund

    previous_amount = refund.amount
    previous_days = refund.remaining_days
    refund.payment = payment
    refund.amount = amount
    refund.remaining_days = remaining_days
    refund.reason = reason.strip()[:2000]
    refund.status = 'created'
    refund.provider_refund_id = None
    refund.save(
        update_fields=[
            'payment', 'amount', 'remaining_days', 'reason', 'status',
            'provider_refund_id', 'updated_at',
        ]
    )
    audit(
        actor,
        'refund.requoted',
        refund,
        {
            'previous_amount': str(previous_amount),
            'amount': str(amount),
            'previous_remaining_days': previous_days,
            'remaining_days': remaining_days,
        },
    )
    return refund


@transaction.atomic
def _prepare_refund_attempt(refund_id):
    row = (
        Refund.objects.select_for_update()
        .select_related('payment', 'term__license')
        .get(pk=refund_id)
    )
    if row.status == 'succeeded':
        raise ValidationError('Erstattung ist bereits abgeschlossen.')

    active_attempt = (
        row.attempts.select_for_update()
        .filter(status__in=['submitted', 'ambiguous'])
        .order_by('-number')
        .first()
    )
    if row.status == 'submitted' and active_attempt:
        return row, active_attempt

    max_number = row.attempts.aggregate(value=Max('number'))['value'] or 0
    number = max_number + 1
    # Legacy submitted refunds created before RefundAttempt used refund:<uuid>.
    # Reusing that original key is the only safe recovery for an unknown
    # pre-migration provider outcome.
    legacy_submitted = row.status == 'submitted' and max_number == 0
    idempotency_key = (
        f'refund:{row.id}'
        if legacy_submitted
        else f'refund:{row.id}:attempt:{number}'
    )
    attempt = RefundAttempt.objects.create(
        refund=row,
        number=number,
        idempotency_key=idempotency_key,
        amount=row.amount,
        provider_refund_id=row.provider_refund_id if legacy_submitted else None,
        status='submitted',
    )
    row.status = 'submitted'
    if not legacy_submitted:
        row.provider_refund_id = None
    row.save(update_fields=['status', 'provider_refund_id', 'updated_at'])
    return row, attempt


def _record_refund_attempt_error(refund_id, attempt_id, exc):
    with transaction.atomic():
        row = Refund.objects.select_for_update().get(pk=refund_id)
        attempt = RefundAttempt.objects.select_for_update().get(pk=attempt_id)
        now = timezone.now()
        attempt.error_class = type(exc).__name__[:120]
        attempt.resolved_at = None if exc.ambiguous else now
        if exc.ambiguous:
            attempt.status = 'ambiguous'
            row.status = 'submitted'
        else:
            attempt.status = 'failed'
            row.status = 'failed'
            row.provider_refund_id = None
        attempt.save(
            update_fields=['status', 'error_class', 'resolved_at', 'updated_at']
        )
        row.save(update_fields=['status', 'provider_refund_id', 'updated_at'])
    audit(
        None,
        'refund.provider_attempt_failed',
        row,
        {
            'attempt': attempt.number,
            'ambiguous': bool(exc.ambiguous),
            'error_class': type(exc).__name__,
        },
    )


def submit_refund(refund):
    # Reserve/reuse an attempt while holding a row lock, then release the DB
    # transaction before waiting on Mollie. Concurrent callers converge on the
    # same active attempt and therefore the same provider idempotency key.
    row, attempt = _prepare_refund_attempt(refund.pk)
    try:
        response = MollieClient().create_refund(
            row.payment.provider_payment_id,
            attempt.amount,
            row.payment.currency,
            f'PromptMaster Erstattung {row.term.license.license_number}',
            attempt.idempotency_key,
        )
    except MollieError as exc:
        _record_refund_attempt_error(row.pk, attempt.pk, exc)
        raise

    provider_id = str(response.get('id') or '')[:100]
    provider_status = str(response.get('status') or 'pending').lower()
    now = timezone.now()
    with transaction.atomic():
        row = Refund.objects.select_for_update().get(pk=row.pk)
        attempt = RefundAttempt.objects.select_for_update().get(pk=attempt.pk)
        if provider_id:
            attempt.provider_refund_id = provider_id
        attempt.error_class = ''
        if provider_status == 'refunded':
            attempt.status = 'succeeded'
            attempt.resolved_at = now
            row.status = 'succeeded'
            row.provider_refund_id = provider_id or row.provider_refund_id
        elif provider_status in {'failed', 'canceled'}:
            attempt.status = 'failed'
            attempt.resolved_at = now
            row.status = 'failed'
            row.provider_refund_id = None
        else:
            attempt.status = 'submitted'
            attempt.resolved_at = None
            row.status = 'submitted'
            row.provider_refund_id = provider_id or row.provider_refund_id
        attempt.save(
            update_fields=[
                'provider_refund_id', 'status', 'error_class', 'resolved_at',
                'updated_at',
            ]
        )
        row.save(update_fields=['provider_refund_id', 'status', 'updated_at'])

    if provider_status == 'refunded':
        return mark_refund_success(row, row.provider_refund_id)
    if provider_status in {'failed', 'canceled'}:
        audit(
            None,
            'refund.provider_attempt_failed',
            row,
            {'attempt': attempt.number, 'ambiguous': False, 'provider_status': provider_status},
        )
        raise MollieError(f'Mollie refund {provider_status}', ambiguous=False)
    return row


@transaction.atomic
def mark_refund_success(refund, provider_id):
    row = Refund.objects.select_for_update().select_related('term__license').get(pk=refund.pk)
    if row.status == 'succeeded' and row.term.status == 'refunded':
        return row
    row.provider_refund_id = provider_id or row.provider_refund_id
    row.status = 'succeeded'
    row.save(update_fields=['provider_refund_id', 'status', 'updated_at'])

    now = timezone.now()
    attempt = None
    if row.provider_refund_id:
        attempt = row.attempts.select_for_update().filter(
            provider_refund_id=row.provider_refund_id
        ).order_by('-number').first()
    if attempt is None:
        attempt = row.attempts.select_for_update().filter(
            status__in=['submitted', 'ambiguous']
        ).order_by('-number').first()
    if attempt is not None and attempt.status != 'succeeded':
        attempt.status = 'succeeded'
        attempt.provider_refund_id = row.provider_refund_id or attempt.provider_refund_id
        attempt.error_class = ''
        attempt.resolved_at = now
        attempt.save(
            update_fields=[
                'status', 'provider_refund_id', 'error_class', 'resolved_at',
                'updated_at',
            ]
        )

    payment = Payment.objects.select_for_update().get(pk=row.payment_id)
    refunded_total = payment.refunds.filter(status='succeeded').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if payment.status != 'chargeback':
        desired_payment_status = 'refunded_full' if refunded_total >= payment.amount else 'refunded_partial'
        if payment.status != desired_payment_status:
            payment.status = desired_payment_status
            payment.save(update_fields=['status', 'updated_at'])

    term = LicenseTerm.objects.select_for_update().get(pk=row.term_id)
    if term.status != 'refunded':
        term.status = 'refunded'
        term.refunded_at = now
        term.save(update_fields=['status', 'refunded_at', 'updated_at'])

    license_obj = License.objects.select_for_update().get(pk=term.license_id)
    _recalculate_license_after_refund(license_obj, now)
    audit(None, 'refund.succeeded', row, {'amount': str(row.amount), 'term': str(term.id), 'license': str(license_obj.id)})
    order = row.payment.order
    _queue_after_commit('refund_confirmed', _order_recipient(order), {
        'amount': f'{row.amount:.2f}', 'currency': row.payment.currency, 'license': license_obj.license_number,
    }, order=order)
    return row


def reconcile_refunds(payment):
    """Reconcile provider-visible submitted refunds using Mollie's refund list."""
    pending = list(
        payment.refunds.filter(status='submitted')
        .exclude(provider_refund_id__isnull=True)
        .exclude(provider_refund_id='')
    )
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
            with transaction.atomic():
                current = Refund.objects.select_for_update().get(pk=refund.pk)
                provider_id = current.provider_refund_id
                attempt = current.attempts.select_for_update().filter(
                    provider_refund_id=provider_id
                ).order_by('-number').first()
                if attempt is not None:
                    attempt.status = 'failed'
                    attempt.resolved_at = timezone.now()
                    attempt.error_class = ''
                    attempt.save(
                        update_fields=['status', 'resolved_at', 'error_class', 'updated_at']
                    )
                current.status = 'failed'
                current.provider_refund_id = None
                current.save(update_fields=['status', 'provider_refund_id', 'updated_at'])
    return count
