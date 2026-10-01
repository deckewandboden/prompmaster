import logging

from django.db import transaction

from apps.audit.services import audit
from apps.notifications.services import queue_email

from .models import SupportMessage, SupportRequest

logger = logging.getLogger(__name__)


def is_demo_support_recipient(email):
    return (email or '').strip().lower().endswith('@promptmaster.invalid')


def _status_label(value):
    return dict(SupportRequest.STATUS).get(value, value)


def add_staff_message(
    support_request,
    *,
    author,
    body,
    visibility='customer',
    status_after_message='',
    request=None,
):
    body = (body or '').strip()
    if not body:
        raise ValueError('Bitte geben Sie eine Nachricht ein.')
    if visibility not in {value for value, _label in SupportMessage.VISIBILITY}:
        raise ValueError('Ungültige Sichtbarkeit.')

    allowed_status = {value for value, _label in SupportRequest.STATUS}
    if status_after_message and status_after_message not in allowed_status:
        raise ValueError('Ungültiger Supportstatus.')

    with transaction.atomic():
        locked = (
            SupportRequest.objects.select_for_update(of=('self',))
            .select_related('user', 'company')
            .get(pk=support_request.pk)
        )
        previous_status = locked.status

        message = SupportMessage.objects.create(
            support_request=locked,
            author_user=author,
            sender_type='staff',
            visibility=visibility,
            body=body,
        )

        if status_after_message:
            locked.status = status_after_message
        elif visibility == 'customer' and locked.status == 'new':
            locked.status = 'in_progress'

        if locked.status != previous_status:
            locked.save(update_fields=['status', 'updated_at'])

        audit(
            author,
            'support.reply_created' if visibility == 'customer' else 'support.note_created',
            message,
            {
                'support_request_id': str(locked.pk),
                'visibility': visibility,
                'status_before': previous_status,
                'status_after': locked.status,
            },
            request=request,
        )

    mail_queued = False
    mail_suppressed = False
    mail_error = ''
    recipient = (locked.user.email or '').strip().lower()

    if visibility == 'customer':
        presentation_demo = (
            locked.company_id
            and locked.company
            and locked.company.customer_number == 'DEMO-NETSTYLE'
        )
        if is_demo_support_recipient(recipient) or presentation_demo:
            mail_suppressed = True
        else:
            try:
                email_message = queue_email(
                    'support_reply',
                    recipient,
                    {
                        'subject': locked.subject,
                        'message': message.body,
                        'reply': message.body,
                        'responder': author.full_name or author.email,
                        'status': _status_label(locked.status),
                        'support_id': str(locked.pk),
                        'reference': str(locked.pk),
                    },
                    scope_company=locked.company_id,
                    scope_user=locked.user_id,
                )
            except Exception as exc:
                logger.exception(
                    'Support reply persisted but notification could not be queued',
                    extra={'support_request_id': str(locked.pk)},
                )
                mail_error = str(exc)[:500]
            else:
                message.notification_email = email_message
                message.save(update_fields=['notification_email', 'updated_at'])
                mail_queued = True

    return {
        'message': message,
        'support_request': locked,
        'mail_queued': mail_queued,
        'mail_suppressed': mail_suppressed,
        'mail_error': mail_error,
    }
