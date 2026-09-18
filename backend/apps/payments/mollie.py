import requests
from django.conf import settings


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
        self.key = key

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
            # 5xx can occur after Mollie accepted/processed the request. 4xx is
            # a deterministic rejection of this exact attempt.
            ambiguous = response.status_code >= 500
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

    def get_payment(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}')

    def create_refund(self, payment_id, amount, currency, description, idempotency_key):
        return self._request(
            'POST',
            f'/payments/{payment_id}/refunds',
            headers={'Idempotency-Key': idempotency_key},
            json={
                'amount': {'currency': currency, 'value': f'{amount:.2f}'},
                'description': description,
            },
        )

    def list_refunds(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}/refunds')

    def list_chargebacks(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}/chargebacks')
