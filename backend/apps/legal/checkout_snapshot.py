"""Signed, version-bound evidence for the static public checkout.

This records which immutable legal-document versions were made available in
the purchase flow, not proof that a customer actually opened/read each link.
Legacy checkout can be gated off through LEGAL_CHECKOUT_SNAPSHOT_REQUIRED.
"""
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import get_language

from apps.legal.models import LegalDocument, LegalDocumentTranslation
from apps.legal.checkout_clause import early_performance_statement
from apps.legal.translation_display import resolve_public_legal_text


SIGNING_SALT = 'promptfinisher-public-checkout-legal-snapshot-v1'
SESSION_NONCE = 'checkout_legal_snapshot_nonce'
MAX_AGE_SECONDS = 30 * 60
SUPPORTED_LANGUAGES = frozenset({'de', 'en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl'})
# Do not expose internal approval references or reviewer user IDs in URL tokens.
OFFER_FIELDS = frozenset({
    'document_id', 'document_type', 'document_version',
    'source_identity_sha256', 'body_language', 'body_sha256',
})


def _required_types(customer_type):
    if customer_type not in ('company', 'private'):
        raise ValidationError('Invalid legal snapshot customer type.')
    return ('terms', 'privacy', 'license') + (
        ('withdrawal',) if customer_type == 'private' else ()
    )


def _language():
    language = (get_language() or 'de').lower().split('-', 1)[0]
    return language if language in SUPPORTED_LANGUAGES else 'de'


def _current_document(doc_type, *, lock=False):
    queryset = LegalDocument.objects.filter(
        doc_type=doc_type, active=True, valid_from__lte=timezone.now(),
    ).order_by('-valid_from')
    if lock:
        queryset = queryset.select_for_update()
    document = queryset.first()
    if document is None:
        raise ValidationError(f'No active legal document: {doc_type}')
    return document


def _body_details(document, language):
    _body, body_language, _notice, body_sha256 = resolve_public_legal_text(
        document, language,
        translations_enabled=settings.LEGAL_TRANSLATIONS_PUBLIC_ENABLED,
    )
    approved = None
    if body_language != 'de':
        approved = document.translations.filter(
            language=body_language, status='approved',
        ).first()
        if not approved or not approved.is_publishable():
            raise ValidationError('Legal translation approval changed.')
    return {
        'document_id': str(document.pk),
        'document_type': document.doc_type,
        'document_version': document.version,
        'source_identity_sha256': LegalDocumentTranslation(
            document=document,
        )._current_source_identity_fingerprint(),
        'body_language': body_language,
        'body_sha256': body_sha256,
        'source_content_sha256': LegalDocumentTranslation.fingerprint(document.content),
        'translation_id': str(approved.pk) if approved else None,
        'approval_reference': approved.approval_reference if approved else None,
        'approved_by_id': str(approved.approved_by_id) if approved else None,
        'approved_at': approved.approved_at.isoformat() if approved else None,
    }


def _nonce_cache_key(request):
    """Never put a user/session identifier directly in a cache key."""
    session_key = request.session.session_key
    if not session_key:
        return None
    digest = salted_hmac(
        'promptfinisher.checkout.legal.nonce-cache-key.v1',
        session_key,
        secret=settings.SECRET_KEY,
    ).hexdigest()
    return 'promptfinisher:legal-checkout:nonce:' + digest


def _nonce_cache_ttl():
    # Never let a normal cache expiration resurrect an old offer after a
    # successful provider handoff. A missing entry invalidates old offers.
    return max(MAX_AGE_SECONDS * 2, settings.SESSION_COOKIE_AGE + MAX_AGE_SECONDS)


def _effective_session_nonce(request, *, create=False):
    """Atomic checkout nonce, independent of mutable Django session payloads.

    On an established browser session, concurrent GETs see one nonce from
    Redis (cache.add is atomic). Session middleware may independently modify
    and save a stale session; that cannot revert payment-handoff rotation.
    On cache unavailability we fail closed instead of creating unsigned or
    session-only legal evidence.
    """
    if not request.session.session_key:
        if not create:
            return None
        # The very first request needs a real session cookie. Unlike two
        # requests sharing an existing cookie, separate no-cookie requests
        # cannot be bound together and must remain separate sessions.
        request.session['checkout_legal_session_initialized'] = True
        request.session.save()
    cache_key = _nonce_cache_key(request)
    if not cache_key:
        raise ValidationError('Legal checkout session unavailable.')
    try:
        nonce = cache.get(cache_key)
        if not nonce and create:
            cache.add(cache_key, secrets.token_urlsafe(24), timeout=_nonce_cache_ttl())
            nonce = cache.get(cache_key)
    except Exception as exc:
        raise ValidationError('Legal checkout nonce store unavailable.') from exc
    return nonce or None


def rotate_session_nonce(request):
    """Revoke all earlier offers across tabs after provider handoff.

    The Redis state is authoritative; stale Django session saves cannot undo
    this rotation. Do not silently treat cache failures as success.
    """
    cache_key = _nonce_cache_key(request)
    if not cache_key:
        raise ValidationError('Legal checkout session unavailable.')
    try:
        next_nonce = secrets.token_urlsafe(24)
        cache.set(cache_key, next_nonce, timeout=_nonce_cache_ttl())
        if cache.get(cache_key) != next_nonce:
            raise ValidationError('Legal checkout nonce rotation failed.')
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError('Legal checkout nonce store unavailable.') from exc


def issue_snapshot(request, customer_type):
    """Create an expiring session-bound signed manifest and pinned legal URLs."""
    required = _required_types(customer_type)
    language = _language()
    details = {
        kind: {key: value for key, value in _body_details(
            _current_document(kind), language,
        ).items() if key in OFFER_FIELDS}
        for kind in required
    }
    # A shared, pre-existing cookie needs no write on its first snapshot.
    # This also keeps simultaneous first GETs across two tabs equivalent.
    nonce = _effective_session_nonce(request, create=True)
    payload = {
        'version': 1,
        'nonce': nonce,
        'customer_type': customer_type,
        'ui_language': language,
        'offered_at': timezone.now().isoformat(),
        'documents': details,
    }
    if customer_type == 'private':
        clause = early_performance_statement(language)
        payload['early_performance'] = {
            key: value for key, value in clause.items() if key != 'text'
        }
    token = signing.dumps(payload, salt=SIGNING_SALT, compress=True)
    return {
        'token': token,
        # Client renewal threshold: one minute before the 30-minute signature
        # limit. Only the server's signed timestamp determines true validity.
        'expiresInSeconds': MAX_AGE_SECONDS - 60,
        'customerType': customer_type,
        'uiLanguage': language,
        'earlyPerformance': early_performance_statement(language) if customer_type == 'private' else None,
        'documents': {
            kind: {
                'url': '/legal/' + kind + '/?' + urlencode({'checkout_snapshot': token}),
                'documentVersion': details[kind]['document_version'],
                'bodyLanguage': details[kind]['body_language'],
            }
            for kind in required
        },
    }


def _decode(request, token):
    if not token or not isinstance(token, str) or len(token) > 12000:
        raise ValidationError('Missing legal checkout snapshot.')
    try:
        payload = signing.loads(
            token, salt=SIGNING_SALT, max_age=MAX_AGE_SECONDS,
        )
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise ValidationError('Legal checkout snapshot expired or invalid.') from exc
    expected_nonce = _effective_session_nonce(request)
    if (
        not isinstance(payload, dict)
        or payload.get('version') != 1
        or not expected_nonce
        or payload.get('nonce') != expected_nonce
        or payload.get('ui_language') not in SUPPORTED_LANGUAGES
        or not isinstance(payload.get('documents'), dict)
    ):
        raise ValidationError('Legal checkout snapshot does not match session.')
    return payload


def validate_snapshot(request, token, customer_type, *, lock=False):
    """Revalidate offered versions and return evidence plus authoritative rows.

    Run with lock=True only inside transaction.atomic() before order creation.
    """
    payload = _decode(request, token)
    kinds = _required_types(customer_type)
    if payload.get('customer_type') != customer_type:
        raise ValidationError('Legal checkout customer type has changed.')
    if set(payload['documents']) != set(kinds):
        raise ValidationError('Legal checkout document list does not match.')
    clause_evidence = None
    if customer_type == 'private':
        clause_evidence = early_performance_statement(payload['ui_language'])
        expected_clause = {key: value for key, value in clause_evidence.items() if key != 'text'}
        if payload.get('early_performance') != expected_clause:
            raise ValidationError('Early performance consent wording changed; refresh checkout.')
    elif payload.get('early_performance') is not None:
        raise ValidationError('Unexpected early performance consent on company order.')
    checked = {}
    documents = {}
    for kind in kinds:
        offered = payload['documents'].get(kind)
        if not isinstance(offered, dict):
            raise ValidationError('Invalid legal checkout document version.')
        current = _current_document(kind, lock=lock)
        actual = _body_details(current, payload['ui_language'])
        if (set(offered) != OFFER_FIELDS or any(
            offered[key] != actual[key] for key in OFFER_FIELDS
        )):
            raise ValidationError('Legal document was updated; refresh the purchase page.')
        documents[kind] = current
        checked[kind] = actual
    return {
        'verification': 'signed_session_bound_document_offer',
        'offered_at': payload['offered_at'],
        'accepted_at': timezone.now().isoformat(),
        'ui_language': payload['ui_language'],
        'documents': checked,
        'early_performance_clause': clause_evidence,
        'presentation_proof': 'links_offered_not_read_receipts',
    }, documents


def pinned_public_document(request, doc_type, token):
    """Resolve a legal link to the exact version in the signed offer.

    Refuse drift instead of silently substituting today's live text.
    """
    payload = _decode(request, token)
    offered = payload['documents'].get(doc_type)
    if not isinstance(offered, dict):
        raise ValidationError('This legal document is not part of the offer.')
    document = _current_document(doc_type)
    actual = _body_details(document, payload['ui_language'])
    if (set(offered) != OFFER_FIELDS or any(
            offered[key] != actual[key] for key in OFFER_FIELDS
        )):
        raise ValidationError('The legal document has changed.')
    return document, payload['ui_language']
