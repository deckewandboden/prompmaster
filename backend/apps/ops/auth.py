from datetime import timedelta

from django.utils import timezone

from apps.core.security import token_hash
from apps.integrations.models import ServiceAccount


def service_account(request, scope):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    raw = header[7:].strip()
    if len(raw) < 32 or len(raw) > 512:
        return None
    try:
        account = ServiceAccount.objects.get(token_hash=token_hash(raw), active=True)
    except ServiceAccount.DoesNotExist:
        return None
    now = timezone.now()
    if account.expires_at and account.expires_at <= now:
        return None
    if scope not in (account.scopes or []):
        return None
    if not account.last_used_at or account.last_used_at < now - timedelta(minutes=5):
        ServiceAccount.objects.filter(pk=account.pk, active=True).update(last_used_at=now)
        account.last_used_at = now
    return account
