from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.security import bump_security_version
from apps.audit.services import audit
from apps.companies.models import Membership
from apps.devices.models import DeviceRegistration
from apps.licenses.models import LicenseAssignment
from apps.licenses.services import release_license

from .models import DeletionRequest


@transaction.atomic
def process_deletion_request(deletion, *, actor, request=None):
    """Deactivate and anonymize an approved account deletion request.

    Financial/order, legal acceptance and append-only audit records are retained
    by reference to the anonymized user. No legally relevant business record is
    silently deleted here. Company administrators must transfer their role first.
    """
    deletion = (
        DeletionRequest.objects.select_for_update()
        .select_related('user')
        .get(pk=deletion.pk)
    )
    if deletion.status == 'completed':
        return deletion
    if deletion.status not in {'open', 'processing'}:
        raise ValidationError('Diese Löschanfrage kann nicht verarbeitet werden.')

    user = deletion.user
    active_memberships = list(
        Membership.objects.select_for_update()
        .filter(user=user, active=True)
        .select_related('company')
    )
    if any(link.role == 'admin' for link in active_memberships):
        raise ValidationError('Firmenadministrator muss vor der Löschung übertragen werden.')

    # End active assignments via the canonical service so license state and
    # device revocation stay consistent and audited in one place.
    active_assignments = list(
        LicenseAssignment.objects.select_for_update()
        .filter(user=user, ended_at__isnull=True)
        .select_related('license')
    )
    for assignment in active_assignments:
        release_license(assignment.license, actor)

    now = timezone.now()
    DeviceRegistration.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    Membership.objects.filter(user=user, active=True).update(active=False, updated_at=now)

    if hasattr(user, 'private_customer'):
        profile = user.private_customer
        profile.street = ''
        profile.house_number = ''
        profile.postal_code = ''
        profile.city = ''
        profile.save(update_fields=['street', 'house_number', 'postal_code', 'city', 'updated_at'])

    # Keep the immutable UUID so historical foreign keys remain valid, while
    # removing account PII and login ability.
    user.first_name = ''
    user.last_name = ''
    user.email = f'deleted+{user.id.hex}@invalid.local'
    user.email_verified_at = None
    user.is_active = False
    user.is_staff = False
    user.two_factor_required = False
    user.totp_secret_enc = ''
    user.set_unusable_password()
    user.save(
        update_fields=[
            'first_name', 'last_name', 'email', 'email_verified_at', 'is_active',
            'is_staff', 'two_factor_required', 'totp_secret_enc', 'password', 'updated_at',
        ]
    )
    bump_security_version(user)
    user.recovery_codes.all().delete()

    deletion.status = 'completed'
    deletion.completed_at = now
    deletion.save(update_fields=['status', 'completed_at', 'updated_at'])
    audit(actor, 'privacy.deletion_completed', deletion, {'user_id': str(user.id)}, request=request)
    return deletion


@transaction.atomic
def reject_deletion_request(deletion, *, actor, notes='', request=None):
    deletion = DeletionRequest.objects.select_for_update().get(pk=deletion.pk)
    if deletion.status == 'completed':
        raise ValidationError('Abgeschlossene Löschanfragen können nicht abgelehnt werden.')
    deletion.status = 'rejected'
    deletion.notes = notes.strip()[:5000]
    deletion.completed_at = timezone.now()
    deletion.save(update_fields=['status', 'notes', 'completed_at', 'updated_at'])
    audit(actor, 'privacy.deletion_rejected', deletion, {'notes': deletion.notes}, request=request)
    return deletion
