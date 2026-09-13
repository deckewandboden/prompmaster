from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import audit
from .models import License, LicenseAssignment, LicenseTerm


def has_current_term(license_obj, now=None):
    """Return whether an unrefunded paid term covers ``now``."""
    now = now or timezone.now()
    return LicenseTerm.objects.filter(
        license=license_obj,
        status='active',
        valid_from__lte=now,
        valid_until__gt=now,
    ).exists()


def effective_license_status(license_obj, now=None):
    now = now or timezone.now()
    if license_obj.status in {'blocked', 'payment_review', 'refunded'}:
        return license_obj.status
    if not has_current_term(license_obj, now):
        return 'expired'
    assigned = LicenseAssignment.objects.filter(license=license_obj, ended_at__isnull=True).exists()
    return 'active' if assigned else 'free'


@transaction.atomic
def assign_license(license, user, actor):
    from apps.devices.models import DeviceRegistration

    lic = License.objects.select_for_update().select_related('product').get(pk=license.pk)
    # Lock the identity as well as the seat. Two different free seats of the
    # same product can otherwise be assigned concurrently to the same user.
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    if lic.status in {'blocked', 'payment_review', 'refunded'} or not has_current_term(lic, now):
        raise ValidationError('Lizenz ist nicht zuweisbar.')
    if not user.is_active:
        raise ValidationError('Benutzer ist deaktiviert.')
    if lic.company_id and not user.company_memberships.filter(company_id=lic.company_id, active=True).exists():
        raise ValidationError('Benutzer gehört nicht zum Unternehmen.')
    if lic.owner_user_id and lic.owner_user_id != user.id:
        raise ValidationError('Private Lizenz gehört einem anderen Benutzer.')

    duplicate = LicenseAssignment.objects.filter(
        user=user,
        ended_at__isnull=True,
        license__product=lic.product,
        license__terms__status='active',
        license__terms__valid_from__lte=now,
        license__terms__valid_until__gt=now,
    ).exclude(license=lic).distinct()
    if duplicate.exists():
        raise ValidationError('Dem Benutzer ist dieses Produkt bereits aktiv zugewiesen.')

    previous = list(
        LicenseAssignment.objects.select_for_update()
        .filter(license=lic, ended_at__isnull=True)
        .select_related('user')
    )
    for row in previous:
        row.ended_at = now
        row.save(update_fields=['ended_at'])
        # A device token is an authorization credential for the old assignment;
        # it must never survive a reassignment to a different user.
        DeviceRegistration.objects.filter(
            license=lic, user=row.user, revoked_at__isnull=True
        ).update(revoked_at=now)

    assignment = LicenseAssignment.objects.create(license=lic, user=user)
    lic.status = 'active'
    lic.save(update_fields=['status', 'updated_at'])
    audit(actor, 'license.assigned', lic, {'user': str(user.id)})
    return assignment


@transaction.atomic
def release_license(license, actor):
    from apps.devices.models import DeviceRegistration

    lic = License.objects.select_for_update().get(pk=license.pk)
    now = timezone.now()
    LicenseAssignment.objects.select_for_update().filter(
        license=lic, ended_at__isnull=True
    ).update(ended_at=now)
    DeviceRegistration.objects.filter(license=lic, revoked_at__isnull=True).update(revoked_at=now)
    if lic.status not in {'blocked', 'payment_review', 'refunded'}:
        lic.status = 'free' if has_current_term(lic, now) else 'expired'
    lic.save(update_fields=['status', 'updated_at'])
    audit(actor, 'license.released', lic, {})
    return lic


@transaction.atomic
def request_product_upgrade(*, user, company, product, note='', request=None):
    from .models import LicenseUpgradeRequest

    membership = user.company_memberships.select_for_update().filter(company=company, active=True).first()
    if not membership:
        raise ValidationError('Benutzer gehört nicht zum Unternehmen.')
    now = timezone.now()
    already_active = LicenseAssignment.objects.filter(
        user=user,
        ended_at__isnull=True,
        license__company=company,
        license__product=product,
        license__terms__status='active',
        license__terms__valid_from__lte=now,
        license__terms__valid_until__gt=now,
    ).exists()
    if already_active:
        raise ValidationError('Für dieses Produkt besteht bereits eine aktive Zuweisung.')
    upgrade, created = LicenseUpgradeRequest.objects.get_or_create(
        user=user,
        company=company,
        product=product,
        status='pending',
        defaults={'note': str(note or '')[:2000]},
    )
    if not created and note and upgrade.note != note:
        upgrade.note = str(note)[:2000]
        upgrade.save(update_fields=['note', 'updated_at'])
    if created:
        audit(user, 'license.upgrade_requested', upgrade, {'product': product.code}, request=request)
    return upgrade, created


@transaction.atomic
def resolve_product_upgrade(*, upgrade_request, actor, approve: bool, license_obj=None, request=None):
    from .models import LicenseUpgradeRequest

    row = (
        LicenseUpgradeRequest.objects.select_for_update()
        .select_related('company', 'product', 'user')
        .get(pk=upgrade_request.pk)
    )
    if row.status != 'pending':
        raise ValidationError('Diese Upgrade-Anfrage ist nicht mehr offen.')
    membership = actor.company_memberships.select_for_update().filter(
        company=row.company, active=True, role='admin'
    ).first()
    if not membership:
        raise ValidationError('Nur der aktive Firmenadministrator darf die Anfrage entscheiden.')

    if approve:
        if license_obj is None:
            candidates = License.objects.select_for_update().filter(
                company=row.company,
                product=row.product,
                status='free',
            ).order_by('valid_until', 'created_at')
            license_obj = next((lic for lic in candidates if has_current_term(lic)), None)
        if license_obj is None:
            raise ValidationError('Keine freie gültige Lizenz verfügbar. Bitte zuerst eine weitere Lizenz kaufen.')
        if license_obj.company_id != row.company_id or license_obj.product_id != row.product_id:
            raise ValidationError('Lizenz gehört nicht zu Unternehmen/Produkt der Anfrage.')
        assign_license(license_obj, row.user, actor)
        row.status = 'approved'
        row.assigned_license = license_obj
    else:
        row.status = 'rejected'
    row.resolved_by = actor
    row.resolved_at = timezone.now()
    row.save(update_fields=['status', 'assigned_license', 'resolved_by', 'resolved_at', 'updated_at'])
    audit(
        actor,
        'license.upgrade_resolved',
        row,
        {'status': row.status, 'license': str(row.assigned_license_id or '')},
        request=request,
    )
    return row


@transaction.atomic
def create_assignment_link(*, company, target_user, license_obj, actor, expires_hours=24, request=None):
    from apps.core.security import token_pair
    from .models import LicenseAssignmentLink

    membership = target_user.company_memberships.filter(company=company, active=True).first()
    if not membership:
        raise ValidationError('Zielbenutzer gehört nicht zum Unternehmen.')
    actor_membership = actor.company_memberships.filter(company=company, active=True, role='admin').first()
    if not actor_membership:
        raise ValidationError('Nur der Firmenadministrator darf Zuordnungslinks erzeugen.')
    lic = License.objects.select_for_update().get(pk=license_obj.pk)
    if lic.company_id != company.id or lic.status != 'free' or not has_current_term(lic):
        raise ValidationError('Lizenz ist nicht als freie gültige Unternehmenslizenz verfügbar.')
    LicenseAssignmentLink.objects.filter(
        license=lic,
        target_user=target_user,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    raw, hashed = token_pair(32)
    link = LicenseAssignmentLink.objects.create(
        company=company,
        license=lic,
        target_user=target_user,
        token_hash=hashed,
        expires_at=timezone.now() + timedelta(hours=max(1, min(int(expires_hours), 168))),
        created_by=actor,
    )
    audit(
        actor,
        'license.assignment_link_created',
        link,
        {'license': lic.license_number, 'target_user': str(target_user.id), 'expires_at': link.expires_at.isoformat()},
        request=request,
    )
    return link, raw


@transaction.atomic
def consume_assignment_link(*, raw_token, user, request=None):
    from apps.core.security import token_hash
    from .models import LicenseAssignmentLink

    link = (
        LicenseAssignmentLink.objects.select_for_update()
        .select_related('company', 'license', 'target_user', 'created_by')
        .filter(token_hash=token_hash(raw_token))
        .first()
    )
    if not link or not link.is_valid():
        raise ValidationError('Zuordnungslink ist ungültig oder abgelaufen.')
    if link.target_user_id != user.id:
        raise ValidationError('Dieser Zuordnungslink ist für einen anderen Benutzer bestimmt.')
    if not user.company_memberships.filter(company=link.company, active=True).exists():
        raise ValidationError('Benutzer gehört nicht mehr zum Unternehmen.')
    locked_license = License.objects.select_for_update().get(pk=link.license_id)
    if locked_license.status != 'free' or not has_current_term(locked_license):
        raise ValidationError('Die vorbereitete Lizenz ist nicht mehr frei/verfügbar. Bitte einen neuen Link anfordern.')
    if LicenseAssignment.objects.filter(license=locked_license, ended_at__isnull=True).exists():
        raise ValidationError('Die vorbereitete Lizenz wurde inzwischen anderweitig zugewiesen.')
    assignment = assign_license(locked_license, user, link.created_by)
    link.used_at = timezone.now()
    link.save(update_fields=['used_at', 'updated_at'])
    audit(
        user,
        'license.assignment_link_used',
        link,
        {'license': link.license.license_number, 'delegated_by': str(link.created_by_id)},
        request=request,
    )
    return assignment
