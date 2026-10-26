"""Session-bound, signed legal offers for account creation and invitations.

Separate from checkout snapshots; default-off until explicitly released.
These records establish the offered legal links, NOT proof of reading.
"""
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import get_language

from apps.legal.checkout_snapshot import (
    OFFER_FIELDS, SUPPORTED_LANGUAGES, _body_details, _current_document,
)


SIGNING_SALT = 'promptfinisher-account-legal-offer-v1'
MAX_AGE_SECONDS = 30 * 60
REQUIRED_DOCUMENTS = ('terms', 'privacy')
SUPPORTED_FLOWS = frozenset({'registration', 'invitation'})


def _session_binding(request, *, initialize=False):
    """Use the persistent Django session key, not a per-tab mutable nonce.

    Both already-cookie tabs remain valid until an actual session rotation;
    distinct sessions cannot reuse a signed offer.
    """
    if not request.session.session_key and initialize:
        request.session['account_legal_session_initialized'] = True
        request.session.save()
    key = request.session.session_key
    if not key:
        raise ValidationError('Legal account session unavailable.')
    return salted_hmac(
        'promptfinisher.account.legal.session-binding.v1',
        key, secret=settings.SECRET_KEY,
    ).hexdigest()


def _invitation_identity(invitation):
    if invitation is None:
        return None
    return {
        'id': str(invitation.pk),
        'company_id': str(invitation.company_id),
        'token_hash': invitation.token_hash,
        'email': invitation.email.lower(),
        'role': invitation.role,
    }


def _language():
    lang = (get_language() or 'de').lower().split('-', 1)[0]
    return lang if lang in SUPPORTED_LANGUAGES else 'de'


def _flow_identity(flow, invitation):
    if flow not in SUPPORTED_FLOWS:
        raise ValidationError('Invalid account legal offer flow.')
    if (flow == 'invitation') != (invitation is not None):
        raise ValidationError('Invalid invitation legal offer identity.')
    if invitation is not None and not invitation.is_valid():
        raise ValidationError('Invitation is no longer valid.')
    return _invitation_identity(invitation)


def issue_account_offer(request, *, flow, invitation=None):
    """Issue a read-only link manifest and signed hidden POST input."""
    if not settings.LEGAL_ACCOUNT_SNAPSHOT_REQUIRED:
        raise ValidationError('Account legal offers are disabled.')
    identity = _flow_identity(flow, invitation)
    language = _language()
    details = {
        kind: {
            key: value for key, value in _body_details(
                _current_document(kind), language,
            ).items() if key in OFFER_FIELDS
        }
        for kind in REQUIRED_DOCUMENTS
    }
    payload = {
        'version': 1,
        'flow': flow,
        'invitation': identity,
        'session_binding': _session_binding(request, initialize=True),
        'offered_at': timezone.now().isoformat(),
        'ui_language': language,
        'documents': details,
    }
    token = signing.dumps(payload, salt=SIGNING_SALT, compress=True)
    links = {
        kind: '/legal/' + kind + '/?' + urlencode({'account_snapshot': token})
        for kind in REQUIRED_DOCUMENTS
    }
    return {'token': token, 'links': links, 'expires_in_seconds': MAX_AGE_SECONDS}


def _decode(request, token):
    if not isinstance(token, str) or not token or len(token) > 12000:
        raise ValidationError('Missing account legal offer.')
    try:
        payload = signing.loads(token, salt=SIGNING_SALT, max_age=MAX_AGE_SECONDS)
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise ValidationError('Account legal offer invalid or expired.') from exc
    if (
        not isinstance(payload, dict)
        or payload.get('version') != 1
        or payload.get('flow') not in SUPPORTED_FLOWS
        or payload.get('ui_language') not in SUPPORTED_LANGUAGES
        or not isinstance(payload.get('documents'), dict)
        or set(payload['documents']) != set(REQUIRED_DOCUMENTS)
        or payload.get('session_binding') != _session_binding(request)
    ):
        raise ValidationError('Account legal offer does not match this session.')
    return payload


def _claim_offer_once(token):
    """Atomically consume a signed account offer before the user is created.

    A failed database transaction may burn the token, but never makes it
    reusable. The user must request a fresh offer after an unsuccessful POST.
    Do not use mutable Django session state as the authoritative replay lock.
    """
    key = 'promptfinisher:legal-account:consumed:' + salted_hmac(
        'promptfinisher.account.legal.consume-once.v1',
        token, secret=settings.SECRET_KEY,
    ).hexdigest()
    try:
        first_claim = cache.add(key, 'consumed', timeout=MAX_AGE_SECONDS + 60)
    except Exception as exc:
        raise ValidationError('Account legal replay store unavailable.') from exc
    if not first_claim:
        raise ValidationError('Account legal offer has already been used.')


def validate_account_offer(request, token, *, flow, invitation=None, lock=False):
    """Fail closed on source, translation, identity or flow drift.

    Call inside transaction.atomic(lock=True) BEFORE creating a user.
    """
    if not settings.LEGAL_ACCOUNT_SNAPSHOT_REQUIRED:
        raise ValidationError('Account legal offers are disabled.')
    expected_identity = _flow_identity(flow, invitation)
    payload = _decode(request, token)
    if payload.get('flow') != flow or payload.get('invitation') != expected_identity:
        raise ValidationError('Account legal offer flow or invitation changed.')
    checked = {}
    documents = {}
    for kind in REQUIRED_DOCUMENTS:
        offered = payload['documents'].get(kind)
        if not isinstance(offered, dict) or set(offered) != OFFER_FIELDS:
            raise ValidationError('Account legal document offer is incomplete.')
        current = _current_document(kind, lock=lock)
        actual = _body_details(current, payload['ui_language'])
        if any(offered[key] != actual[key] for key in OFFER_FIELDS):
            raise ValidationError('Account legal document changed; reload the page.')
        documents[kind] = current
        checked[kind] = actual
    if lock:
        # The transaction will now create the identity. Claim is atomic across
        # requests, including two concurrent POSTs with the same session key.
        _claim_offer_once(token)
    evidence = {
        'verification': 'signed_session_bound_document_offer',
        'presentation_proof': 'links_offered_not_read_receipts',
        'flow': flow,
        'offered_at': payload['offered_at'],
        'accepted_at': timezone.now().isoformat(),
        'ui_language': payload['ui_language'],
        'documents': checked,
    }
    return evidence, documents


def pinned_account_document(request, doc_type, token):
    """Resolve a signed account link to the still-current exact legal body."""
    if not settings.LEGAL_ACCOUNT_SNAPSHOT_REQUIRED:
        raise ValidationError('Account legal offers are disabled.')
    payload = _decode(request, token)
    if doc_type not in REQUIRED_DOCUMENTS:
        raise ValidationError('This legal document was not part of the offer.')
    identity = payload.get('invitation')
    if payload['flow'] == 'invitation':
        from apps.companies.models import Invitation

        if not isinstance(identity, dict) or 'id' not in identity:
            raise ValidationError('Invalid invitation offer.')
        invitation = Invitation.objects.filter(pk=identity['id']).select_related('company').first()
        if not invitation or not invitation.is_valid() or _invitation_identity(invitation) != identity:
            raise ValidationError('Invitation legal offer is no longer valid.')
    elif identity is not None:
        raise ValidationError('Unexpected invitation identity.')
    offered = payload['documents'][doc_type]
    if not isinstance(offered, dict) or set(offered) != OFFER_FIELDS:
        raise ValidationError('Invalid legal document offer.')
    current = _current_document(doc_type)
    actual = _body_details(current, payload['ui_language'])
    if any(offered[key] != actual[key] for key in OFFER_FIELDS):
        raise ValidationError('Account legal document changed.')
    return current, payload['ui_language']
