import requests
from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailMessage, EmailTemplate


class MailProviderError(RuntimeError):
    pass


def queue_email(code, recipient, context, *, scope_company=None, scope_user=None):
    template = EmailTemplate.objects.get(code=code, active=True)
    stored_context = dict(context)
    if scope_company is not None:
        stored_context['pm_scope_company_id'] = str(
            getattr(scope_company, 'pk', scope_company)
        )
    if scope_user is not None:
        stored_context['pm_scope_user_id'] = str(
            getattr(scope_user, 'pk', scope_user)
        )
    subject = template.subject.format(**stored_context)
    # Validate the body now too, so malformed template placeholders don't
    # create permanently broken queue records.
    template.body_text.format(**stored_context)
    message = EmailMessage.objects.create(
        template=template,
        recipient=recipient.strip().lower(),
        subject=subject,
        context=stored_context,
    )
    from .tasks import send_email_message

    # Never publish a task before the surrounding database transaction is
    # committed; a fast worker could otherwise see a message ID that is not
    # committed yet. A periodic dispatcher recovers queued rows if the broker
    # was unavailable at commit time.
    transaction.on_commit(lambda: send_email_message.delay(str(message.id)), robust=True)
    return message


def _send_smtp(message, body):
    send_mail(
        message.subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [message.recipient],
        fail_silently=False,
    )
    return ''


def _send_graph(message, body):
    required = [settings.GRAPH_TENANT_ID, settings.GRAPH_CLIENT_ID, settings.GRAPH_CLIENT_SECRET, settings.GRAPH_SENDER]
    if not all(required):
        raise MailProviderError('Microsoft Graph mail provider is not fully configured')

    token_response = requests.post(
        f'https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}/oauth2/v2.0/token',
        data={
            'client_id': settings.GRAPH_CLIENT_ID,
            'client_secret': settings.GRAPH_CLIENT_SECRET,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials',
        },
        timeout=(5, 20),
    )
    token_response.raise_for_status()
    access_token = token_response.json().get('access_token')
    if not access_token:
        raise MailProviderError('Microsoft Graph did not return an access token')

    response = requests.post(
        f'https://graph.microsoft.com/v1.0/users/{settings.GRAPH_SENDER}/sendMail',
        headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        json={
            'message': {
                'subject': message.subject,
                'body': {'contentType': 'Text', 'content': body},
                'toRecipients': [{'emailAddress': {'address': message.recipient}}],
            },
            'saveToSentItems': True,
        },
        timeout=(5, 20),
    )
    response.raise_for_status()
    return response.headers.get('request-id', '')[:160]


def send_now(message):
    if message.status == 'sent':
        return message
    template = message.template
    body = template.body_text.format(**message.context) if template else ''
    provider = settings.EMAIL_PROVIDER.lower().strip()
    if provider in {'smtp', 'mailpit'}:
        reference = _send_smtp(message, body)
    elif provider in {'graph', 'microsoft_graph'}:
        reference = _send_graph(message, body)
    else:
        raise MailProviderError(f'Unsupported mail provider: {provider}')

    message.status = 'sent'
    message.sent_at = timezone.now()
    message.provider_reference = reference
    message.error = ''
    message.save(update_fields=['status', 'sent_at', 'provider_reference', 'error', 'updated_at'])
    return message
