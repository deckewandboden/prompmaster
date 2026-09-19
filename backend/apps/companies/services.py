from datetime import timedelta

INVITATION_TTL_HOURS = 24

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import audit
from apps.accounts.security import bump_security_version
from apps.core.security import token_pair
from .models import Invitation, Membership, PrivateCustomerProfile


@transaction.atomic
def create_invitation(*, company, actor, email, first_name='', last_name=''):
    normalized = email.strip().lower()
    existing_user = get_user_model().objects.filter(email__iexact=normalized).only(
        'id', 'is_staff'
    ).first()
    if existing_user and existing_user.is_staff:
        raise ValidationError(
            'Interne netstyle Benutzer können keinem Kundenunternehmen beitreten.'
        )
    if existing_user and not existing_user.is_active:
        if Membership.objects.filter(
            company=company,
            user=existing_user,
            active=False,
        ).exists():
            raise ValidationError(
                'Dieser Benutzer ist deaktiviert. Öffnen Sie ihn unter „Mein Team“ und reaktivieren Sie das Konto.'
            )
        raise ValidationError(
            'Zu dieser E-Mail-Adresse existiert ein deaktiviertes Konto. Bitte wenden Sie sich an den Support.'
        )
    if Membership.objects.filter(user__email__iexact=normalized, active=True).exists():
        raise ValidationError('Diese E-Mail-Adresse gehört bereits zu einem aktiven Unternehmenskonto.')
    if PrivateCustomerProfile.objects.filter(user__email__iexact=normalized).exists():
        raise ValidationError('Diese E-Mail-Adresse gehört bereits zu einem Privatkundenkonto. Eine Identität kann in V1 nicht gleichzeitig Privat- und Firmenkunde sein.')
    Invitation.objects.select_for_update().filter(
        company=company,
        email__iexact=normalized,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    raw, hashed = token_pair()
    invitation = Invitation.objects.create(
        company=company,
        email=normalized,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        token_hash=hashed,
        expires_at=timezone.now() + timedelta(hours=INVITATION_TTL_HOURS),
        invited_by=actor,
    )
    audit(actor, 'invitation.created', invitation, {'email': normalized})
    return invitation, raw


@transaction.atomic
def transfer_admin(company, old_admin, new_user, *, actor=None, request=None, audit_context=None):
    if old_admin.pk == new_user.pk:
        raise ValidationError('Der Benutzer ist bereits Firmenadministrator.')
    if new_user.is_staff:
        raise ValidationError(
            'Interne netstyle Benutzer dürfen keine Kunden-Firmenadministratoren werden.'
        )

    active_memberships = Membership.objects.select_for_update().filter(company=company, active=True)
    old_membership = active_memberships.filter(user=old_admin, role='admin').first()
    if not old_membership:
        raise ValidationError('Aktueller Firmenadministrator nicht gefunden.')

    new_membership = active_memberships.filter(user=new_user).first()
    if not new_membership:
        raise ValidationError('Der neue Administrator muss aktives Mitglied des Unternehmens sein.')

    # Demote first within the same transaction, then promote the target. The
    # conditional DB constraint still guarantees one active admin in V1.
    old_membership.role = 'member'
    old_membership.save(update_fields=['role', 'updated_at'])
    new_membership.role = 'admin'
    new_membership.save(update_fields=['role', 'updated_at'])

    if not new_user.two_factor_required:
        new_user.two_factor_required = True
        new_user.save(update_fields=['two_factor_required', 'updated_at'])

    # Both identities changed privilege. Invalidate all old sessions so the
    # newly promoted administrator must establish a fresh, 2FA-protected
    # session and the former administrator cannot retain stale privileges.
    bump_security_version(old_admin)
    bump_security_version(new_user)

    event_context = {
        'old_admin': str(old_admin.id),
        'new_admin': str(new_user.id),
    }
    if audit_context:
        event_context.update(audit_context)
    audit(
        actor or old_admin,
        'company.admin_transferred',
        company,
        event_context,
        request=request,
    )
    return new_membership


@transaction.atomic
def reactivate_company_member(*, company, member, actor, request=None):
    locked = (
        Membership.objects.select_for_update()
        .select_related('user')
        .get(pk=member.pk, company=company)
    )
    user = get_user_model().objects.select_for_update().get(pk=locked.user_id)
    if locked.active:
        return locked
    if user.is_staff:
        raise ValidationError(
            'Interne netstyle Benutzer dürfen nicht über ein Kundenunternehmen reaktiviert werden.'
        )
    if hasattr(user, 'private_customer'):
        raise ValidationError(
            'Ein Privatkundenkonto kann nicht als Firmenmitglied reaktiviert werden.'
        )
    if Membership.objects.filter(user=user, active=True).exclude(pk=locked.pk).exists():
        raise ValidationError('Der Benutzer gehört bereits zu einem anderen aktiven Unternehmen.')
    locked.active = True
    locked.role = 'member'
    locked.save(update_fields=['active', 'role', 'updated_at'])
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active', 'updated_at'])
    bump_security_version(user)
    audit(
        actor,
        'company.member_reactivated',
        locked,
        {'user': str(user.id), 'company': str(company.id)},
        request=request,
    )
    return locked


@transaction.atomic
def deactivate_company_member(*, company, member, actor, request=None):
    """Deactivate a non-admin company member and release tenant resources."""
    from apps.devices.models import DeviceRegistration
    from apps.licenses.models import LicenseAssignment
    from apps.licenses.services import release_license

    locked = (
        Membership.objects.select_for_update()
        .select_related('user')
        .get(pk=member.pk, company=company, active=True)
    )
    if locked.user.is_staff:
        raise ValidationError(
            'Interne netstyle Benutzer dürfen nicht über ein Kundenunternehmen verwaltet werden.'
        )
    if locked.role == 'admin':
        raise ValidationError('Firmenadministrator zuerst übertragen.')

    assignments = list(
        LicenseAssignment.objects.select_for_update()
        .filter(
            user=locked.user,
            license__company=company,
            ended_at__isnull=True,
        )
        .select_related('license')
    )
    for row in assignments:
        release_license(row.license, actor)

    DeviceRegistration.objects.filter(
        user=locked.user,
        license__company=company,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    locked.active = False
    locked.save(update_fields=['active', 'updated_at'])
    locked.user.is_active = False
    locked.user.save(update_fields=['is_active', 'updated_at'])
    bump_security_version(locked.user)
    audit(
        actor,
        'company.member_deactivated',
        locked,
        {'user': str(locked.user_id), 'company': str(company.id)},
        request=request,
    )
    return locked
