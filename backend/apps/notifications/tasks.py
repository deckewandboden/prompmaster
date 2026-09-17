from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.licenses.models import License, LicenseReminder
from .models import EmailMessage
from .services import (
    MailScopeInactive,
    message_scope_active,
    queue_email,
    reminder_recipient_scopes,
    send_now,
)


def _reminder_recipients(license_obj):
    """Compatibility helper returning the canonical current recipient set."""
    return sorted(reminder_recipient_scopes(license_obj))


def _sync_reminder_delivery(message):
    reminder_id = (message.context or {}).get('reminder_id')
    if not reminder_id:
        return
    try:
        reminder = LicenseReminder.objects.select_related(
            'license__company', 'license__owner_user'
        ).get(pk=reminder_id)
    except LicenseReminder.DoesNotExist:
        return

    intended = set(reminder_recipient_scopes(reminder.license))
    if not intended:
        reminder.status = 'error'
        reminder.error = 'Keine aktuellen Reminder-Empfänger verfügbar.'
        reminder.save(update_fields=['status', 'error', 'updated_at'])
        return

    related = EmailMessage.objects.filter(
        context__reminder_id=str(reminder.id),
        recipient__in=intended,
    )
    sent_recipients = set(
        related.filter(status='sent').values_list('recipient', flat=True)
    )
    if intended.issubset(sent_recipients):
        reminder.status = 'sent'
        reminder.sent_at = timezone.now()
        reminder.error = ''
        reminder.save(update_fields=['status', 'sent_at', 'error', 'updated_at'])
    elif related.filter(status='failed').exists():
        reminder.status = 'error'
        reminder.error = 'Mindestens eine aktuelle Reminder-E-Mail konnte nicht versendet werden.'
        reminder.save(update_fields=['status', 'error', 'updated_at'])


def _suppress_inactive_scope(message):
    message.status = 'failed'
    message.error = 'Versand verworfen: Capability/Benutzer-/Firmenscope ist nicht mehr aktiv.'
    message.save(update_fields=['status', 'error', 'updated_at'])
    _sync_reminder_delivery(message)
    return 'scope-inactive'


@shared_task(bind=True, max_retries=4, default_retry_delay=60)
def send_email_message(self, message_id):
    with transaction.atomic():
        message = EmailMessage.objects.select_for_update().select_related('template').get(pk=message_id)
        if message.status == 'sent':
            return 'already-sent'
        if not message_scope_active(message):
            return _suppress_inactive_scope(message)
        if message.status == 'sending' and message.updated_at > timezone.now() - timedelta(minutes=10):
            return 'already-sending'
        message.status = 'sending'
        message.error = ''
        message.save(update_fields=['status', 'error', 'updated_at'])
    try:
        send_now(message)
        _sync_reminder_delivery(message)
        return 'sent'
    except MailScopeInactive:
        with transaction.atomic():
            message = EmailMessage.objects.select_for_update().get(pk=message_id)
            if message.status != 'sent':
                return _suppress_inactive_scope(message)
        return 'already-sent'
    except Exception as exc:
        with transaction.atomic():
            message = EmailMessage.objects.select_for_update().get(pk=message_id)
            if message.status != 'sent':
                message.status = 'failed'
                message.retry_count += 1
                message.error = str(exc)[:500]
                message.save(update_fields=['status', 'retry_count', 'error', 'updated_at'])
        _sync_reminder_delivery(message)
        raise self.retry(exc=exc)


@shared_task
def dispatch_queued_emails():
    """Recover mail rows that were committed while the broker was down."""
    cutoff = timezone.now() - timedelta(minutes=2)
    ids = list(
        EmailMessage.objects.filter(status='queued', created_at__lte=cutoff)
        .order_by('created_at')
        .values_list('id', flat=True)[:500]
    )
    for message_id in ids:
        send_email_message.delay(str(message_id))
    return len(ids)


@shared_task
def schedule_license_reminders():
    now = timezone.now()
    today = timezone.localdate()
    queued = 0
    queryset = (
        License.objects.filter(valid_until__gte=now - timedelta(days=2), status__in=['active', 'free', 'expired'])
        .select_related('product', 'company', 'owner_user')
        .prefetch_related('assignments__user')
    )
    for license_obj in queryset.iterator(chunk_size=500):
        remaining = (timezone.localtime(license_obj.valid_until).date() - today).days
        candidates = []
        if license_obj.status == 'expired' or remaining < 0:
            candidates.append(('t0', 'license_expired'))
        elif license_obj.product.reminder_2_days < remaining <= license_obj.product.reminder_1_days:
            candidates.append(('t60', 't60'))
        elif 0 <= remaining <= license_obj.product.reminder_2_days:
            candidates.append(('t30', 't30'))

        for kind, template_code in candidates:
            with transaction.atomic():
                reminder, _ = LicenseReminder.objects.select_for_update().get_or_create(
                    license=license_obj,
                    kind=kind,
                    target_valid_until=license_obj.valid_until,
                )
                if reminder.status in {'queued', 'sent'}:
                    continue
                try:
                    recipient_scopes = reminder_recipient_scopes(license_obj)
                    if not recipient_scopes:
                        raise RuntimeError('Keine Reminder-Empfänger verfügbar.')
                    context = {
                        'license': license_obj.license_number,
                        'expiry': timezone.localtime(license_obj.valid_until).strftime('%d.%m.%Y'),
                        'reminder_id': str(reminder.id),
                    }
                    reminder_messages = EmailMessage.objects.select_for_update().filter(
                        context__reminder_id=str(reminder.id)
                    )
                    for recipient, recipient_user_id in recipient_scopes.items():
                        recipient_messages = reminder_messages.filter(recipient=recipient)
                        if recipient_messages.filter(status='sent').exists():
                            continue
                        existing = recipient_messages.order_by('-created_at').first()
                        if existing:
                            stale_sending = (
                                existing.status == 'sending'
                                and existing.updated_at <= now - timedelta(minutes=10)
                            )
                            if existing.status == 'failed' or stale_sending:
                                existing.context = dict(existing.context or {})
                                existing.context['pm_scope_company_id'] = str(license_obj.company_id) if license_obj.company_id else ''
                                existing.context['pm_scope_user_id'] = str(recipient_user_id)
                                existing.status = 'queued'
                                existing.error = ''
                                existing.save(update_fields=['context', 'status', 'error', 'updated_at'])
                                transaction.on_commit(
                                    lambda message_id=str(existing.id): send_email_message.delay(message_id),
                                    robust=True,
                                )
                            continue
                        queue_email(
                            template_code,
                            recipient,
                            context,
                            scope_company=license_obj.company_id,
                            scope_user=recipient_user_id,
                        )

                    related = EmailMessage.objects.filter(
                        context__reminder_id=str(reminder.id)
                    )
                    probe = related.first()
                    if probe:
                        _sync_reminder_delivery(probe)
                        reminder.refresh_from_db(fields=['status', 'sent_at', 'error'])
                    if reminder.status != 'sent':
                        reminder.status = 'queued'
                        reminder.queued_at = timezone.now()
                        reminder.error = ''
                        reminder.save(update_fields=['status', 'queued_at', 'error', 'updated_at'])
                    queued += 1
                except Exception as exc:
                    reminder.status = 'error'
                    reminder.error = str(exc)[:1000]
                    reminder.save(update_fields=['status', 'error', 'updated_at'])
    return queued


@shared_task
def sync_license_states():
    """Keep denormalised License.status aligned with paid term coverage."""
    from apps.licenses.services import effective_license_status

    mutable_states = {'active', 'free', 'expired'}
    ids = License.objects.filter(status__in=mutable_states).values_list('id', flat=True)
    changed = 0
    for license_id in ids.iterator(chunk_size=500):
        with transaction.atomic():
            license_obj = (
                License.objects.select_for_update()
                .select_related('product')
                .get(pk=license_id)
            )
            if license_obj.status not in mutable_states:
                continue
            desired = effective_license_status(license_obj, timezone.now())
            if desired != license_obj.status:
                license_obj.status = desired
                license_obj.save(update_fields=['status', 'updated_at'])
                changed += 1
    return changed
