from email.utils import formataddr
from string import Formatter
from urllib.parse import unquote, urlsplit

import requests
from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMessage as DjangoEmailMessage, get_connection
from django.utils import timezone

from apps.core.crypto import decrypt, encrypt
from apps.core.security import token_hash
from apps.core.settings_store import get_setting
from apps.integrations.services import get_secret

from .models import EmailMessage, EmailTemplate


class MailProviderError(RuntimeError):
    pass


class MailScopeInactive(MailProviderError):
    pass


_ENCRYPTED_PREFIX = 'pm_enc:v1:'
_SENSITIVE_CONTEXT_KEYS = {'url', 'link', 'token', 'message', 'reply'}
_USER_SCOPED_TEMPLATES = {'verify_email', 'password_reset', 'staff_invite', 'checkout_activation'}


def get_mail_identity():
    """Return the runtime mail identity stored in admin settings.

    DNS fields are documentation/desired-state values only. The sender identity
    is read for every delivery so an address/domain migration does not require
    rebuilding or restarting the application containers.
    """
    stored = get_setting('mail_identity', {}) or {}
    return {
        'from_email': str(stored.get('from_email') or settings.DEFAULT_FROM_EMAIL).strip(),
        'from_name': str(stored.get('from_name') or '').strip(),
        'reply_to': str(stored.get('reply_to') or '').strip(),
        'domain': str(stored.get('domain') or '').strip().lower().rstrip('.'),
        'spf_record': str(stored.get('spf_record') or '').strip(),
        'dkim_selector': str(stored.get('dkim_selector') or '').strip(),
        'dkim_record': str(stored.get('dkim_record') or '').strip(),
        'dmarc_record': str(stored.get('dmarc_record') or '').strip(),
    }


def get_smtp_transport():
    """Return runtime SMTP transport settings with encrypted password storage."""
    stored = get_setting('mail_transport', {}) or {}
    password = get_secret('smtp_password', settings.EMAIL_HOST_PASSWORD)
    return {
        'host': str(stored.get('host') or settings.EMAIL_HOST).strip(),
        'port': int(stored.get('port') or settings.EMAIL_PORT),
        'use_tls': bool(
            stored.get('use_tls')
            if 'use_tls' in stored
            else settings.EMAIL_USE_TLS
        ),
        'username': str(stored.get('username') or settings.EMAIL_HOST_USER).strip(),
        'password': password,
        'password_configured': bool(password),
    }


def get_mail_provider():
    provider = str(get_setting('mail_provider', settings.EMAIL_PROVIDER) or 'smtp').strip().lower()
    if provider in {'mailpit'}:
        return 'smtp'
    if provider in {'microsoft_graph'}:
        return 'graph'
    return provider


def get_graph_transport():
    """Return runtime Microsoft Graph configuration with encrypted client secret."""
    stored = get_setting('mail_graph', {}) or {}
    secret = get_secret('graph_client_secret', settings.GRAPH_CLIENT_SECRET)
    return {
        'tenant_id': str(stored.get('tenant_id') or settings.GRAPH_TENANT_ID).strip(),
        'client_id': str(stored.get('client_id') or settings.GRAPH_CLIENT_ID).strip(),
        'client_secret': secret,
        'sender': str(stored.get('sender') or settings.GRAPH_SENDER).strip(),
        'client_secret_configured': bool(secret),
    }


def _extract_last_url_token(value):
    try:
        path = urlsplit(str(value or '')).path.rstrip('/')
        return unquote(path.rsplit('/', 1)[-1]) if path else ''
    except Exception:
        return ''


def _infer_message_scope(code, recipient, context, scope_company, scope_user):
    """Infer missing scope for authentication/capability e-mails."""
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


def reminder_recipient_scopes(license_obj):
    """Return current reminder recipient e-mail -> user id mapping.

    This is the canonical source for both scheduling and last-second delivery
    authorization. A queued reminder therefore follows membership/admin changes
    instead of trusting a stale address captured hours earlier.
    """
    recipients = {}
    if license_obj.company_id:
        from apps.companies.models import Membership

        if not license_obj.company or license_obj.company.status != 'active':
            return recipients
        active_members = {
            row.user_id: row.user
            for row in Membership.objects.filter(
                company_id=license_obj.company_id,
                active=True,
                user__is_active=True,
            ).select_related('user')
        }
        active_assignment = (
            license_obj.assignments.filter(ended_at__isnull=True)
            .select_related('user')
            .first()
        )
        if active_assignment and active_assignment.user_id in active_members:
            user = active_members[active_assignment.user_id]
            recipients[user.email.lower()] = user.pk
        admin = (
            Membership.objects.filter(
                company_id=license_obj.company_id,
                active=True,
                role='admin',
                user__is_active=True,
            )
            .select_related('user')
            .first()
        )
        if admin:
            recipients[admin.user.email.lower()] = admin.user_id
    elif license_obj.owner_user_id and license_obj.owner_user.is_active:
        recipients[license_obj.owner_user.email.lower()] = license_obj.owner_user_id
    return recipients


def _capability_message_active(message, rendered_context):
    code = message.template.code if message.template_id and message.template else ''
    raw_token = _extract_last_url_token(rendered_context.get('url'))
    if code == 'invite':
        if not raw_token:
            return False
        from apps.companies.models import Invitation

        invitation = (
            Invitation.objects.select_related('company')
            .filter(
                token_hash=token_hash(raw_token),
                email__iexact=message.recipient,
            )
            .first()
        )
        return bool(
            invitation
            and invitation.company.status == 'active'
            and invitation.is_valid()
        )

    if code == 'assignment_link':
        if not raw_token:
            return False
        from apps.licenses.models import LicenseAssignmentLink
        from apps.licenses.services import has_current_term

        link = (
            LicenseAssignmentLink.objects.select_related(
                'company', 'target_user', 'license__company'
            )
            .filter(token_hash=token_hash(raw_token))
            .first()
        )
        if not link or not link.is_valid():
            return False
        if link.company.status != 'active' or not link.target_user.is_active:
            return False
        if link.target_user.email.lower() != message.recipient.lower():
            return False
        if not link.target_user.company_memberships.filter(
            company=link.company,
            active=True,
        ).exists():
            return False
        if (
            link.license.company_id != link.company_id
            or link.license.status != 'free'
            or not has_current_term(link.license)
        ):
            return False
    return True


def message_scope_active(message):
    """Revalidate authorization and concrete capability immediately before send."""
    stored_context = message.context or {}
    company_id = stored_context.get('pm_scope_company_id')
    user_id = stored_context.get('pm_scope_user_id')

    company_ok = True
    user_ok = True
    if company_id:
        from apps.companies.models import Company
        company_ok = Company.objects.filter(pk=company_id, status='active').exists()
    if user_id:
        user_ok = get_user_model().objects.filter(pk=user_id, is_active=True).exists()
    if not company_ok or not user_ok:
        return False

    if company_id and user_id:
        from apps.companies.models import Membership
        if not Membership.objects.filter(
            company_id=company_id,
            user_id=user_id,
            company__status='active',
            active=True,
            user__is_active=True,
        ).exists():
            return False

    try:
        rendered_context = _render_context(stored_context)
    except Exception:
        return False

    if not _capability_message_active(message, rendered_context):
        return False

    reminder_id = rendered_context.get('reminder_id')
    if reminder_id:
        from apps.licenses.models import LicenseReminder

        reminder = (
            LicenseReminder.objects.select_related(
                'license__company', 'license__owner_user'
            )
            .filter(pk=reminder_id)
            .first()
        )
        if not reminder:
            return False
        current = reminder_recipient_scopes(reminder.license)
        current_user_id = current.get(message.recipient.lower())
        if not current_user_id:
            return False
        if user_id and str(current_user_id) != str(user_id):
            return False
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

    _assert_sensitive_values_not_in_subject(template, plain_context)
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
    transaction.on_commit(lambda: send_email_message.delay(str(message.id)), robust=True)
    return message


def _send_smtp(message, body):
    identity = get_mail_identity()
    transport = get_smtp_transport()
    from_email = identity['from_email']
    from_header = (
        formataddr((identity['from_name'], from_email))
        if identity['from_name']
        else from_email
    )
    reply_to = [identity['reply_to']] if identity['reply_to'] else None
    connection = get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=transport['host'],
        port=transport['port'],
        username=transport['username'] or None,
        password=transport['password'] or None,
        use_tls=transport['use_tls'],
        timeout=settings.EMAIL_TIMEOUT,
    )
    email = DjangoEmailMessage(
        subject=message.subject,
        body=body,
        from_email=from_header,
        to=[message.recipient],
        reply_to=reply_to,
        connection=connection,
    )
    email.send(fail_silently=False)
    return ''


def _send_graph(message, body):
    graph = get_graph_transport()
    required = [graph['tenant_id'], graph['client_id'], graph['client_secret'], graph['sender']]
    if not all(required):
        raise MailProviderError('Microsoft Graph mail provider is not fully configured')

    token_response = requests.post(
        f"https://login.microsoftonline.com/{graph['tenant_id']}/oauth2/v2.0/token",
        data={
            'client_id': graph['client_id'],
            'client_secret': graph['client_secret'],
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
        f"https://graph.microsoft.com/v1.0/users/{graph['sender']}/sendMail",
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
    if response.status_code != 202:
        raise MailProviderError(
            f'Microsoft Graph sendMail returned HTTP {response.status_code}; expected 202'
        )
    return response.headers.get('request-id', '')[:160]


def send_now(message):
    if message.status == 'sent':
        return message
    if not message_scope_active(message):
        raise MailScopeInactive('Queued e-mail authorization scope is no longer active')
    template = message.template
    context = _render_context(message.context)
    body = template.body_text.format(**context) if template else ''
    provider = get_mail_provider()
    if provider == 'smtp':
        reference = _send_smtp(message, body)
    elif provider == 'graph':
        reference = _send_graph(message, body)
    else:
        raise MailProviderError(f'Unsupported mail provider: {provider}')

    message.status = 'sent'
    message.sent_at = timezone.now()
    message.provider_reference = reference
    message.error = ''
    message.save(update_fields=['status', 'sent_at', 'provider_reference', 'error', 'updated_at'])
    return message
