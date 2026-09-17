from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.companies.models import Membership
from apps.licenses.models import License, LicenseReminder
from .models import EmailMessage
from .services import queue_email, send_now


def _sync_reminder_delivery(message):
    reminder_id = (message.context or {}).get('reminder_id')
    if not reminder_id:
        return
    try:
        reminder = LicenseReminder.objects.get(pk=reminder_id)
    except LicenseReminder.DoesNotExist:
        return
    related = EmailMessage.objects.filter(context__reminder_id=str(reminder.id))
    recipients = set(related.values_list('recipient', flat=True))
    sent_recipients = set(
        related.filter(status='sent').values_list('recipient', flat=True)
    )
    # Historical duplicate queue rows must not keep a reminder in error once
    # every intended recipient has at least one confirmed successful delivery.
    if recipients and recipients.issubset(sent_recipients):
        reminder.status = 'sent'
        reminder.sent_at = timezone.now()
        reminder.error = ''
        reminder.save(update_fields=['status', 'sent_at', 'error', 'updated_at'])
    elif related.filter(status='failed').exists():
        reminder.status = 'error'
        reminder.error = 'Mindestens eine Reminder-E-Mail konnte nicht versendet werden.'
        reminder.save(update_fields=['status', 'error', 'updated_at'])


@shared_task(bind=True, max_retries=4, default_retry_delay=60)
def send_email_message(self, message_id):
    # Claim the row before contacting an external provider. Duplicate Celery
    # deliveries then collapse into one active sender.
    with transaction.atomic():
        message = EmailMessage.objects.select_for_update().select_related('template').get(pk=message_id)
        if message.status == 'sent':
            return 'already-sent'
        if message.status == 'sending' and message.updated_at > timezone.now() - timedelta(minutes=10):
            return 'already-sending'
        message.status = 'sending'
        message.error = ''
        message.save(update_fields=['status', 'error', 'updated_at'])
    try:
        send_now(message)
        _sync_reminder_delivery(message)
        return 'sent'
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


def _reminder_recipients(license_obj):
    recipients = set()
    active_assignment = license_obj.assignments.filter(ended_at__isnull=True).select_related('user').first()
    if active_assignment and active_assignment.user.is_active:
        recipients.add(active_assignment.user.email.lower())
    if license_obj.company_id:
        admin = (
            Membership.objects.filter(company_id=license_obj.company_id, active=True, role='admin')
            .select_related('user')
            .first()
        )
        if admin and admin.user.is_active:
            recipients.add(admin.user.email.lower())
    elif license_obj.owner_user_id and license_obj.owner_user.is_active:
        recipients.add(license_obj.owner_user.email.lower())
    return sorted(recipients)


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
        # Windows avoid sending T-60 and T-30 together after a long outage.
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
                    recipients = _reminder_recipients(license_obj)
                    if not recipients:
                        raise RuntimeError('Keine Reminder-Empfänger verfügbar.')
                    context = {
                        'license': license_obj.license_number,
                        'expiry': timezone.localtime(license_obj.valid_until).strftime('%d.%m.%Y'),
                        'reminder_id': str(reminder.id),
                    }
                    reminder_messages = EmailMessage.objects.select_for_update().filter(
                        context__reminder_id=str(reminder.id)
                    )
                    for recipient in recipients:
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
                                existing.status = 'queued'
                                existing.error = ''
                                existing.save(update_fields=['status', 'error', 'updated_at'])
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
                            scope_user=license_obj.owner_user_id,
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

    now = timezone.now()
    changed = 0
    queryset = License.objects.filter(status__in=['active', 'free', 'expired']).select_related('product')
    for license_obj in queryset.iterator(chunk_size=500):
        desired = effective_license_status(license_obj, now)
        if desired != license_obj.status:
            license_obj.status = desired
            license_obj.save(update_fields=['status', 'updated_at'])
            changed += 1
    return changed
