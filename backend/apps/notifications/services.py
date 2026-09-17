from string import Formatter
from urllib.parse import unquote, urlsplit

import requests
from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.core.crypto import decrypt, encrypt
from apps.core.security import token_hash

from .models import EmailMessage, EmailTemplate


class MailProviderError(RuntimeError):
    pass


class MailScopeInactive(MailProviderError):
    pass


_ENCRYPTED_PREFIX = 'pm_enc:v1:'
_SENSITIVE_CONTEXT_KEYS = {'url', 'link', 'token'}
_USER_SCOPED_TEMPLATES = {'verify_email', 'password_reset', 'staff_invite'}


def _extract_last_url_token(value):
    try:
        path = urlsplit(str(value or '')).path.rstrip('/')
        return unquote(path.rsplit('/', 1)[-1]) if path else ''
    except Exception:
        return ''


def _infer_message_scope(code, recipient, context, scope_company, scope_user):
    """Infer missing scope for authentication/capability e-mails.

    Callers should still pass explicit scope whenever they already own it. This
    fallback keeps security properties intact for legacy call sites without
    requiring raw capability tokens to remain stored in the mail queue.
    """
    if scope_user is None and code in _USER_SCOPED_TEMPLATES:
        user = get_user_model().objects.filter(email__iexact=recipient).only('id').first()
        if user:
            scope_user = user.pk

    raw_token = _extract_last_url_token(context.get('url'))
    if raw_token and code == 'invite' and scope_company is None:
        from apps.companies.models import Invitation

        invitation = (
            Invitation.objects.filter(
                token_hash=token_hash(raw_token),
                email__iexact=recipient,
            )
            .only('company_id')
            .first()
        )
        if invitation:
            scope_company = invitation.company_id

    if raw_token and code == 'assignment_link':
        from apps.licenses.models import LicenseAssignmentLink

        link = (
            LicenseAssignmentLink.objects.filter(token_hash=token_hash(raw_token))
            .only('company_id', 'target_user_id')
            .first()
        )
        if link:
            if scope_company is None:
                scope_company = link.company_id
            if scope_user is None:
                scope_user = link.target_user_id

    return scope_company, scope_user


def _protect_context(context):
    stored = dict(context or {})
    for key, value in list(stored.items()):
        if (
            key.lower() in _SENSITIVE_CONTEXT_KEYS
            and isinstance(value, str)
            and value
            and not value.startswith(_ENCRYPTED_PREFIX)
        ):
            stored[key] = _ENCRYPTED_PREFIX + encrypt(value)
    return stored


def _render_context(context):
    rendered = dict(context or {})
    for key, value in list(rendered.items()):
        if isinstance(value, str) and value.startswith(_ENCRYPTED_PREFIX):
            rendered[key] = decrypt(value[len(_ENCRYPTED_PREFIX):])
    return rendered


def sanitize_stored_email_contexts(*, batch_size=500):
    """Encrypt legacy plaintext capability fields already persisted in queue rows.

    Idempotent: values carrying the versioned encryption marker are left
    untouched, so this can safely run on every deploy through seed_defaults.
    """
    changed = 0
    ids = EmailMessage.objects.order_by('id').values_list('id', flat=True)
    for message_id in ids.iterator(chunk_size=batch_size):
        with transaction.atomic():
            message = EmailMessage.objects.select_for_update().get(pk=message_id)
            protected = _protect_context(message.context)
            if protected != (message.context or {}):
                message.context = protected
                message.save(update_fields=['context', 'updated_at'])
                changed += 1
    return changed


def _assert_sensitive_values_not_in_subject(template, context):
    fields = {
        (field_name or '').split('.', 1)[0].split('[', 1)[0]
        for _literal, field_name, _format_spec, _conversion in Formatter().parse(template.subject)
        if field_name
    }
    sensitive = {
        key for key, value in (context or {}).items()
        if key.lower() in _SENSITIVE_CONTEXT_KEYS and value
    }
    if fields.intersection(sensitive):
        raise ValueError('Sensitive URL/token fields are not allowed in persisted e-mail subjects')


def message_scope_active(message):
    """Revalidate a queued message's authorization scope immediately before send."""
    context = message.context or {}
    company_id = context.get('pm_scope_company_id')
    user_id = context.get('pm_scope_user_id')

    company_ok = True
    user_ok = True
    if company_id:
        from apps.companies.models import Company

        company_ok = Company.objects.filter(pk=company_id, status='active').exists()
    if user_id:
        user_ok = get_user_model().objects.filter(pk=user_id, is_active=True).exists()
    if not company_ok or not user_ok:
        return False

    # When both scopes are present the capability belongs to a user inside that
    # tenant. Require the relationship itself to still be active as well.
    if company_id and user_id:
        from apps.companies.models import Membership

        return Membership.objects.filter(
            company_id=company_id,
            user_id=user_id,
            company__status='active',
            active=True,
            user__is_active=True,
        ).exists()
    return True


def queue_email(code, recipient, context, *, scope_company=None, scope_user=None):
    template = EmailTemplate.objects.get(code=code, active=True)
    recipient = recipient.strip().lower()
    plain_context = dict(context)
    scope_company, scope_user = _infer_message_scope(
        code,
        recipient,
        plain_context,
        scope_company,
        scope_user,
    )

    # Persisted subjects are intentionally non-secret. A future template must
    # not move a capability URL/token into the subject line where it would be
    # stored and propagated outside the encrypted context field.
    _assert_sensitive_values_not_in_subject(template, plain_context)

    # Render/validate against plaintext only in memory. Capability URLs are
    # encrypted before the durable queue row is created.
    subject = template.subject.format(**plain_context)
    template.body_text.format(**plain_context)
    stored_context = _protect_context(plain_context)
    if scope_company is not None:
        stored_context['pm_scope_company_id'] = str(
            getattr(scope_company, 'pk', scope_company)
        )
    if scope_user is not None:
        stored_context['pm_scope_user_id'] = str(
            getattr(scope_user, 'pk', scope_user)
        )

    message = EmailMessage.objects.create(
        template=template,
        recipient=recipient,
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
    if not message_scope_active(message):
        raise MailScopeInactive('Queued e-mail authorization scope is no longer active')
    template = message.template
    context = _render_context(message.context)
    body = template.body_text.format(**context) if template else ''
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
