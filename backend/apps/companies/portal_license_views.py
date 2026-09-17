from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.licenses.models import License, LicenseAssignment
from .models import Membership


def _license_scope(user):
    membership = (
        Membership.objects.filter(user=user, active=True)
        .select_related('company')
        .first()
    )
    if membership and membership.company.status != 'active':
        raise PermissionDenied('Das Unternehmen ist deaktiviert.')
    if membership and membership.role == 'admin':
        return License.objects.filter(company=membership.company), membership
    if membership:
        return (
            License.objects.filter(
                company=membership.company,
                assignments__user=user,
                assignments__ended_at__isnull=True,
            ).distinct(),
            membership,
        )
    return License.objects.filter(owner_user=user), None


@login_required
def license_detail(request, pk):
    queryset, membership = _license_scope(request.user)
    license_obj = get_object_or_404(queryset.select_related('product'), pk=pk)
    assignment = (
        LicenseAssignment.objects.filter(license=license_obj, ended_at__isnull=True)
        .select_related('user')
        .first()
    )
    latest_reminder = license_obj.reminders.order_by('-created_at').first()
    today = timezone.localdate()
    remaining_days = max(0, (timezone.localtime(license_obj.valid_until).date() - today).days) if license_obj.valid_until else 0
    can_manage = not membership or membership.role == 'admin'
    return render(
        request,
        'portal/license_detail.html',
        {
            'license': license_obj,
            'assignment': assignment,
            'latest_reminder': latest_reminder,
            'remaining_days': remaining_days,
            'can_manage': can_manage,
            'is_admin': bool(membership and membership.role == 'admin'),
        },
    )


@login_required
def renew_index(request):
    queryset, membership = _license_scope(request.user)
    licenses = (
        queryset.select_related('product')
        .exclude(status__in=['refunded', 'payment_review', 'blocked'])
        .order_by('valid_until', 'license_number')
    )
    return render(
        request,
        'portal/renew_index.html',
        {
            'licenses': licenses,
            'can_manage': not membership or membership.role == 'admin',
        },
    )
