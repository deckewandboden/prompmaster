import smtplib

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


class SafeMailFailoverError(MailProviderError):
    """A provider failure known to happen before successful message acceptance."""

    def __init__(self, provider, original):
        self.provider = provider
        self.original = original
        super().__init__(f'{provider}: {original}')


def _smtp_error_allows_failover(exc):
    """Return True only when SMTP definitely did not accept the message.

    Authentication failures are explicitly failover-safe. SMTP 4xx responses
    are temporary rejections and are also safe to try on the next provider.
    Permanent 5xx recipient/sender/data rejections stay on the normal retry/
    failure path instead of blindly switching providers.
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = []
        for response in exc.recipients.values():
            if isinstance(response, tuple) and response:
                try:
                    codes.append(int(response[0]))
                except (TypeError, ValueError):
                    return False
        return bool(codes) and all(400 <= code < 500 for code in codes)
    if isinstance(exc, smtplib.SMTPResponseException):
        try:
            code = int(exc.smtp_code)
        except (TypeError, ValueError):
            return False
        return 400 <= code < 500
    return False


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


def _normalize_provider(value):
    value = str(value or '').strip().lower()
    if value in {'smtp', 'mailpit'}:
        return 'smtp1'
    if value == 'microsoft_graph':
        return 'graph'
    return value


def get_smtp_transport(slot='smtp1'):
    """Return runtime SMTP transport settings for SMTP 1 or SMTP 2."""
    slot = _normalize_provider(slot)
    if slot not in {'smtp1', 'smtp2'}:
        raise MailProviderError(f'Unknown SMTP slot: {slot}')
    if slot == 'smtp1':
        stored = get_setting('mail_transport', {}) or {}
        password = get_secret('smtp_password', settings.EMAIL_HOST_PASSWORD)
        fallback = {
            'host': settings.EMAIL_HOST,
            'port': settings.EMAIL_PORT,
            'use_tls': settings.EMAIL_USE_TLS,
            'username': settings.EMAIL_HOST_USER,
        }
    else:
        stored = get_setting('mail_transport_2', {}) or {}
        password = get_secret('smtp_password_2', '')
        fallback = {
            'host': '',
            'port': 587,
            'use_tls': True,
            'username': '',
        }
    return {
        'slot': slot,
        'host': str(stored.get('host') or fallback['host']).strip(),
        'port': int(stored.get('port') or fallback['port']),
        'use_tls': bool(
            stored.get('use_tls')
            if 'use_tls' in stored
            else fallback['use_tls']
        ),
        'username': str(stored.get('username') or fallback['username']).strip(),
        'password': password,
        'password_configured': bool(password),
    }


def get_mail_provider():
    provider = _normalize_provider(
        get_setting('mail_provider', settings.EMAIL_PROVIDER) or 'smtp1'
    )
    return provider or 'smtp1'


def get_mail_delivery():
    """Return manual/automatic provider routing in delivery order."""
    stored = get_setting('mail_delivery', {}) or {}
    mode = str(stored.get('mode') or 'manual').strip().lower()
    if mode not in {'manual', 'failover'}:
        mode = 'manual'
    primary = _normalize_provider(stored.get('primary') or get_mail_provider()) or 'smtp1'
    fallbacks = []
    for key in ('fallback_1', 'fallback_2'):
        provider = _normalize_provider(stored.get(key))
        if provider and provider != primary and provider not in fallbacks:
            fallbacks.append(provider)
    route = [primary]
    if mode == 'failover':
        route.extend(fallbacks)
    return {
        'mode': mode,
        'primary': primary,
        'fallback_1': fallbacks[0] if len(fallbacks) > 0 else '',
        'fallback_2': fallbacks[1] if len(fallbacks) > 1 else '',
        'route': route,
    }


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


def _smtp_message_id(message, identity):
    """Return a stable RFC-style Message-ID using the configured sender domain.

    Using the database UUID keeps the Message-ID stable across SMTP failover
    attempts and avoids leaking ephemeral Docker/container hostnames.
    """
    domain = str(identity.get('domain') or '').strip().lower().rstrip('.')
    if not domain:
        from_email = str(identity.get('from_email') or '').strip()
        domain = from_email.rsplit('@', 1)[-1].lower() if '@' in from_email else ''
    if not domain:
        domain = 'localhost'
    identifier = str(getattr(message, 'id', '') or getattr(message, 'pk', '') or 'promptmaster')
    return f'<{identifier}@{domain}>'


def _send_smtp(message, body, slot='smtp1'):
    identity = get_mail_identity()
    transport = get_smtp_transport(slot)
    if not transport['host']:
        raise SafeMailFailoverError(slot, 'SMTP host is not configured')
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
    try:
        connection.open()
    except Exception as exc:
        # The SMTP session did not open, so the message cannot have been accepted.
        raise SafeMailFailoverError(slot, exc) from exc
    try:
        email = DjangoEmailMessage(
            subject=message.subject,
            body=body,
            from_email=from_header,
            to=[message.recipient],
            reply_to=reply_to,
            headers={'Message-ID': _smtp_message_id(message, identity)},
            connection=connection,
        )
        try:
            email.send(fail_silently=False)
        except (
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
            smtplib.SMTPDataError,
            smtplib.SMTPAuthenticationError,
        ) as exc:
            if _smtp_error_allows_failover(exc):
                # Authentication failed or the provider issued a temporary 4xx
                # rejection; the message was definitely not accepted.
                raise SafeMailFailoverError(slot, exc) from exc
            raise
    finally:
        connection.close()
    return ''


def _send_graph(message, body):
    graph = get_graph_transport()
    required = [graph['tenant_id'], graph['client_id'], graph['client_secret'], graph['sender']]
    if not all(required):
        raise SafeMailFailoverError('graph', 'Microsoft Graph mail provider is not fully configured')

    try:
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
    except Exception as exc:
        # No sendMail request has been made yet, so SMTP failover is safe.
        raise SafeMailFailoverError('graph', exc) from exc
    if not access_token:
        raise SafeMailFailoverError('graph', 'Microsoft Graph did not return an access token')

    identity = get_mail_identity()
    graph_message = {
        'subject': message.subject,
        'body': {'contentType': 'Text', 'content': body},
        'toRecipients': [{'emailAddress': {'address': message.recipient}}],
    }
    if identity['reply_to']:
        graph_message['replyTo'] = [
            {'emailAddress': {'address': identity['reply_to']}}
        ]

    response = requests.post(
        f"https://graph.microsoft.com/v1.0/users/{graph['sender']}/sendMail",
        headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        json={
            'message': graph_message,
            'saveToSentItems': True,
        },
        timeout=(5, 20),
    )
    if 400 <= response.status_code < 500:
        # A definite Graph rejection means the message was not accepted.
        try:
            response.raise_for_status()
        except Exception as exc:
            raise SafeMailFailoverError('graph', exc) from exc
    response.raise_for_status()
    if response.status_code != 202:
        raise MailProviderError(
            f'Microsoft Graph sendMail returned HTTP {response.status_code}; expected 202'
        )
    return response.headers.get('request-id', '')[:160]


def _send_via_provider(provider, message, body):
    provider = _normalize_provider(provider)
    if provider in {'smtp1', 'smtp2'}:
        return _send_smtp(message, body, provider)
    if provider == 'graph':
        return _send_graph(message, body)
    raise SafeMailFailoverError(provider or 'unknown', 'Unsupported or empty mail provider')


def send_now(message):
    if message.status == 'sent':
        return message
    if not message_scope_active(message):
        raise MailScopeInactive('Queued e-mail authorization scope is no longer active')
    template = message.template
    context = _render_context(message.context)
    body = template.body_text.format(**context) if template else ''
    delivery = get_mail_delivery()
    attempts = []
    reference = ''
    used_provider = ''
    for index, provider in enumerate(delivery['route']):
        try:
            reference = _send_via_provider(provider, message, body)
            used_provider = provider
            attempts.append({'provider': provider, 'result': 'sent'})
            break
        except SafeMailFailoverError as exc:
            attempts.append(
                {
                    'provider': provider,
                    'result': 'failed-safe',
                    'error': str(exc.original)[:240],
                }
            )
            if delivery['mode'] != 'failover' or index == len(delivery['route']) - 1:
                message.delivery_attempts = attempts
                message.save(update_fields=['delivery_attempts', 'updated_at'])
                raise
            continue
        except Exception:
            # Ambiguous provider failures are intentionally not failed over:
            # the upstream provider may already have accepted the message.
            attempts.append({'provider': provider, 'result': 'failed-uncertain'})
            message.delivery_attempts = attempts
            message.save(update_fields=['delivery_attempts', 'updated_at'])
            raise
    if not used_provider:
        raise MailProviderError('No configured mail provider completed delivery')

    message.status = 'sent'
    message.sent_at = timezone.now()
    message.provider_reference = reference
    message.provider_used = used_provider
    message.delivery_attempts = attempts
    message.error = ''
    message.save(
        update_fields=[
            'status',
            'sent_at',
            'provider_reference',
            'provider_used',
            'delivery_attempts',
            'error',
            'updated_at',
        ]
    )
    return message
