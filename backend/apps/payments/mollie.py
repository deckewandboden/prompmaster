import requests
from django.conf import settings


class MollieError(RuntimeError):
    pass


class MollieClient:
    base = 'https://api.mollie.com/v2'

    def __init__(self, key=None):
        if key is None:
            from apps.integrations.services import get_secret
            key = get_secret('mollie_api_key', settings.MOLLIE_API_KEY)
        self.key = key

    def _request(self, method, path, **kwargs):
        if not self.key:
            raise MollieError('Mollie API key is not configured')
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
            raise MollieError('Mollie request failed') from exc
        if not response.ok:
            raise MollieError(f'Mollie HTTP {response.status_code}')
        try:
            return response.json()
        except ValueError as exc:
            raise MollieError('Mollie returned invalid JSON') from exc

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
