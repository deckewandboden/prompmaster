from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import audit
from apps.catalog.services import PRO_ACCESS_FEATURE
from apps.core.security import token_hash, token_pair
from apps.licenses.models import LicenseAssignment
from apps.licenses.services import has_current_term
from .models import DeviceRegistration


@transaction.atomic
def register_device(user, license, display_name, os_family='', browser_family=''):
    lic = type(license).objects.select_for_update().select_related('product').get(pk=license.pk)
    now = timezone.now()
    if lic.status != 'active' or not has_current_term(lic, now):
        raise ValidationError('Lizenz ist nicht aktiv.')
    if not LicenseAssignment.objects.filter(license=lic, user=user, ended_at__isnull=True).exists():
        raise ValidationError('Lizenz ist diesem Benutzer nicht zugewiesen.')

    # Limit applies per user/product, not merely per database license row. This
    # remains correct if a seat is replaced while the product stays Pro.
    active = DeviceRegistration.objects.select_for_update().filter(
        user=user,
        license__product=lic.product,
        revoked_at__isnull=True,
    ).count()
    if active >= lic.product.default_device_limit:
        raise ValidationError('Gerätelimit erreicht.')

    raw, hashed = token_pair()
    device = DeviceRegistration.objects.create(
        user=user,
        license=lic,
        token_hash=hashed,
        display_name=display_name.strip()[:120] or 'Browser',
        os_family=os_family.strip()[:80],
        browser_family=browser_family.strip()[:80],
        last_seen_at=now,
    )
    audit(user, 'device.registered', device, {'license': str(lic.id)})
    return device, raw


def validate_device_token(user, raw_token, *, feature_code=PRO_ACCESS_FEATURE, touch=True):
    if not raw_token:
        return None
    hashed = token_hash(raw_token)
    now = timezone.now()
    device = (
        DeviceRegistration.objects.select_related('license__product')
        .filter(
            user=user,
            token_hash=hashed,
            revoked_at__isnull=True,
            license__product__active=True,
            license__product__entitlements__feature__code=feature_code,
            license__product__entitlements__enabled=True,
            license__status='active',
        )
        .first()
    )
    if not device:
        return None
    lic = device.license
    if not LicenseAssignment.objects.filter(license=lic, user=user, ended_at__isnull=True).exists():
        return None
    if not has_current_term(lic, now):
        return None
    if touch and (not device.last_seen_at or device.last_seen_at < now - timedelta(minutes=5)):
        DeviceRegistration.objects.filter(pk=device.pk, revoked_at__isnull=True).update(last_seen_at=now)
        device.last_seen_at = now
    return device


@transaction.atomic
def revoke_device(device, actor, request=None):
    row = DeviceRegistration.objects.select_for_update().get(pk=device.pk)
    if not row.revoked_at:
        row.revoked_at = timezone.now()
        row.save(update_fields=['revoked_at', 'updated_at'])
        audit(actor, 'device.revoked', row, {'user': str(row.user_id)}, request=request)
    return row
