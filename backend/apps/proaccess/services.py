from django.utils import timezone

from apps.catalog.services import PRO_ACCESS_FEATURE
from apps.licenses.models import LicenseAssignment
from apps.licenses.services import has_current_term

DEVICE_COOKIE = 'pm_device_v2'
LEGACY_DEVICE_COOKIE = 'pm_device'


def active_product_assignment(user, product_code=None, required_feature=PRO_ACCESS_FEATURE):
    """Return a live assignment whose product grants the runtime entitlement.

    ``product_code`` remains accepted for backwards compatibility with older
    callers but deliberately does not participate in authorization. Access is
    controlled by the enabled product entitlement.
    """
    if not user.is_active or not user.email_verified_at:
        return None
    from apps.companies.models import Membership

    now = timezone.now()
    candidates = (
        LicenseAssignment.objects.select_related('license__product')
        .filter(
            user=user,
            ended_at__isnull=True,
            license__product__active=True,
            license__status='active',
            license__product__entitlements__feature__code=required_feature,
            license__product__entitlements__enabled=True,
        )
        .distinct()
        .order_by('-assigned_at')
    )
    for assignment in candidates:
        if assignment.license.company_id and not Membership.objects.filter(
            company_id=assignment.license.company_id, user=user, active=True,
            company__status='active',
        ).exists():
            continue
        if has_current_term(assignment.license, now):
            return assignment
    return None


def assignment_expiry_context(assignment, now=None):
    """Return authoritative remaining-term warning data for a live assignment."""
    import math
    from apps.licenses.models import LicenseTerm

    now = now or timezone.now()
    term = (
        LicenseTerm.objects.filter(
            license=assignment.license,
            status='active',
            valid_from__lte=now,
            valid_until__gt=now,
        )
        .order_by('-valid_until')
        .first()
    )
    if not term:
        return None
    seconds = max(0, (term.valid_until - now).total_seconds())
    days = int(math.ceil(seconds / 86400))
    product = assignment.license.product
    if days <= product.critical_warning_days:
        level = 'critical'
    elif days <= product.reminder_2_days:
        level = 'warning'
    elif days <= product.reminder_1_days:
        level = 'info'
    else:
        level = 'none'
    return {
        'term': term,
        'valid_until': term.valid_until,
        'days_remaining': days,
        'level': level,
        'critical_days': product.critical_warning_days,
        'reminder_2_days': product.reminder_2_days,
        'reminder_1_days': product.reminder_1_days,
    }
