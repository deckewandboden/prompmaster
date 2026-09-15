from datetime import timedelta

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
        expires_at=timezone.now() + timedelta(hours=24),
        invited_by=actor,
    )
    audit(actor, 'invitation.created', invitation, {'email': normalized})
    return invitation, raw


@transaction.atomic
def transfer_admin(company, old_admin, new_user, *, actor=None, request=None, audit_context=None):
    if old_admin.pk == new_user.pk:
        raise ValidationError('Der Benutzer ist bereits Firmenadministrator.')

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
