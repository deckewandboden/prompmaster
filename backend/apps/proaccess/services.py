from django.utils import timezone

from apps.licenses.models import LicenseAssignment
from apps.licenses.services import has_current_term


def active_product_assignment(user, product_code='PRO'):
    """Return the one assignment that currently grants product access."""
    now = timezone.now()
    candidates = (
        LicenseAssignment.objects.select_related('license__product')
        .filter(
            user=user,
            ended_at__isnull=True,
            license__product__code=product_code,
            license__product__active=True,
            license__status='active',
        )
        .order_by('-assigned_at')
    )
    for assignment in candidates:
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
