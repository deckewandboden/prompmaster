from apps.core.crypto import decrypt, encrypt
from .models import IntegrationSecret


def get_secret(code, default=''):
    row = IntegrationSecret.objects.filter(code=code, active=True).first()
    if not row:
        return default
    return decrypt(row.encrypted_value)


def set_secret(code, value):
    row, _ = IntegrationSecret.objects.update_or_create(
        code=code,
        defaults={'encrypted_value': encrypt(value), 'active': True},
    )
    return row
