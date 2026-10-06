import requests
from urllib.parse import urlsplit

from django.conf import settings


# Mollie caches Idempotency-Key results for one hour. Keep automatic retries
# comfortably inside that provider window.
MOLLIE_IDEMPOTENCY_SAFE_RETRY_SECONDS = 55 * 60


def mollie_runtime_ready():
    """Return True only when the effective runtime payment configuration is usable.

    Secrets may live encrypted in the database, so this deliberately checks the
    same effective sources as MollieClient rather than only settings/.env.
    """
    try:
        from apps.core.settings_store import get_setting
        from apps.integrations.services import get_secret

        key = (get_secret('mollie_api_key', settings.MOLLIE_API_KEY) or '').strip()
        profile_id = (
            get_setting('mollie_profile_id', settings.MOLLIE_PROFILE_ID) or ''
        ).strip()
    except Exception:
        return False

    if not key or not profile_id:
        return False
    environment = str(getattr(settings, 'ENVIRONMENT', 'development') or '').strip().lower()
    return key.startswith('live_') if environment == 'production' else key.startswith('test_')



class MollieError(RuntimeError):
    """Sanitised provider error with retry-safety classification.

    ``ambiguous`` means the request may have reached Mollie and therefore a
    retry must reuse the exact same idempotency key. Deterministic failures may
    start a new provider attempt after the local business state is revalidated.
    """

    def __init__(self, message, *, ambiguous=False, status_code=None):
        super().__init__(message)
        self.ambiguous = bool(ambiguous)
        self.status_code = status_code


class MollieClient:
    base = 'https://api.mollie.com/v2'

    def __init__(self, key=None):
        if key is None:
            from apps.integrations.services import get_secret
            key = get_secret('mollie_api_key', settings.MOLLIE_API_KEY)
        self.key = (key or '').strip()

        if self.key:
            environment = str(getattr(settings, 'ENVIRONMENT', 'development') or '').strip().lower()
            if environment == 'production' and not self.key.startswith('live_'):
                raise MollieError(
                    'Production requires a Mollie live API key',
                    ambiguous=False,
                )
            if environment != 'production' and self.key.startswith('live_'):
                raise MollieError(
                    'Non-production environments refuse Mollie live API keys',
                    ambiguous=False,
                )

    def _request(self, method, path, **kwargs):
        if not self.key:
            raise MollieError('Mollie API key is not configured', ambiguous=False)
        headers = {'Authorization': f'Bearer {self.key}', 'Accept': 'application/json'}
        headers.update(kwargs.pop('headers', {}))
        try:
            response = requests.request(
                method,
                self.base + path,
                headers=headers,
                timeout=(5, 20),
                **kwargs,
            )
        except requests.RequestException as exc:
            # A timeout/connection reset after bytes were sent can mean Mollie
            # accepted the command. Never create a fresh idempotency key here.
            raise MollieError('Mollie request failed', ambiguous=True) from exc
        if not response.ok:
            # 5xx and timeout/rate/conflict responses can occur while the
            # provider-side outcome is still unknown. In particular Mollie
            # documents 409 for a duplicate idempotent request while the first
            # request is still being processed. Never rotate a financial
            # idempotency key for these outcomes.
            ambiguous = (
                response.status_code >= 500
                or response.status_code in {408, 409, 429}
            )
            raise MollieError(
                f'Mollie HTTP {response.status_code}',
                ambiguous=ambiguous,
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            # Successful HTTP status with an unreadable body leaves the provider
            # outcome unknown; retry only with the same idempotency key.
            raise MollieError('Mollie returned invalid JSON', ambiguous=True) from exc

    def create_payment(self, *, amount, currency, description, redirect_url, webhook_url, metadata, idempotency_key):
        return self._request(
            'POST',
            '/payments',
            headers={'Idempotency-Key': idempotency_key},
            json={
                'amount': {'currency': currency, 'value': f'{amount:.2f}'},
                'description': description,
                'redirectUrl': redirect_url,
                'webhookUrl': webhook_url,
                'metadata': metadata,
            },
        )

    def get_current_profile(self):
        return self._request('GET', '/profiles/me')

    def get_payment(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}')

    def create_refund(
        self,
        payment_id,
        amount,
        currency,
        description,
        idempotency_key,
        *,
        metadata=None,
    ):
        body = {
            'amount': {'currency': currency, 'value': f'{amount:.2f}'},
            'description': description,
        }
        if metadata is not None:
            body['metadata'] = metadata
        return self._request(
            'POST',
            f'/payments/{payment_id}/refunds',
            headers={'Idempotency-Key': idempotency_key},
            json=body,
        )

    def list_refunds(self, payment_id):
        path = f'/payments/{payment_id}/refunds?limit=250'
        rows = []
        first_payload = None
        seen = set()
        base_parts = urlsplit(self.base)
        api_prefix = base_parts.path.rstrip('/')

        for _ in range(20):
            if path in seen:
                raise MollieError(
                    'Mollie refund pagination loop detected',
                    ambiguous=False,
                )
            seen.add(path)
            payload = self._request('GET', path)
            if not isinstance(payload, dict):
                raise MollieError(
                    'Mollie returned invalid refund list data',
                    ambiguous=False,
                )
            if first_payload is None:
                first_payload = payload
            page_rows = (payload.get('_embedded') or {}).get('refunds') or []
            if not isinstance(page_rows, list):
                raise MollieError(
                    'Mollie returned invalid refund rows',
                    ambiguous=False,
                )
            rows.extend(page_rows)

            next_href = (
                ((payload.get('_links') or {}).get('next') or {}).get('href') or ''
            ).strip()
            if not next_href:
                result = dict(first_payload or {})
                embedded = dict(result.get('_embedded') or {})
                embedded['refunds'] = rows
                result['_embedded'] = embedded
                result['count'] = len(rows)
                return result

            parsed = urlsplit(next_href)
            if parsed.scheme or parsed.netloc:
                if (
                    parsed.scheme != base_parts.scheme
                    or parsed.netloc != base_parts.netloc
                ):
                    raise MollieError(
                        'Mollie refund pagination returned an unexpected host',
                        ambiguous=False,
                    )
            if not parsed.path.startswith(f'{api_prefix}/'):
                raise MollieError(
                    'Mollie refund pagination returned an unexpected API path',
                    ambiguous=False,
                )
            relative_path = parsed.path[len(api_prefix):]
            path = relative_path + (f'?{parsed.query}' if parsed.query else '')

        raise MollieError(
            'Mollie refund pagination exceeded the safety limit',
            ambiguous=False,
        )

    def list_chargebacks(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}/chargebacks')
