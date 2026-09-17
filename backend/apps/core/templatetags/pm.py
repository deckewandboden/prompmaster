from django import template

register = template.Library()


@register.filter
def attr(obj, name):
    """Resolve a safe dot-separated attribute path for DataGrid cells."""
    value = obj
    for part in str(name).split('.'):
        if value is None:
            return ''
        value = getattr(value, part, '')
        if callable(value):
            try:
                value = value()
            except TypeError:
                return value
    return value


@register.simple_tag
def url_replace(request, **kwargs):
    q = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == '':
            q.pop(key, None)
        else:
            q[key] = value
    return '?' + q.urlencode() if q else request.path


@register.simple_tag
def sort_url(request, key, current_sort, current_dir):
    q = request.GET.copy()
    q['sort'] = key
    q['dir'] = 'desc' if current_sort == key and current_dir == 'asc' else 'asc'
    q['page'] = '1'
    return '?' + q.urlencode()


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key, '')
    except Exception:
        return ''


@register.simple_tag
def col_visible(request, key):
    selected = request.GET.getlist('cols')
    return not selected or key in selected


@register.simple_tag
def filter_display(request, param, choices):
    current = request.GET.get(param, '')
    for value, label in choices:
        if str(value) == str(current):
            return str(label)
    return current


@register.simple_tag
def nav_class(request, names):
    current = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
    candidates = [item.strip() for item in names.split(',') if item.strip()]
    for candidate in candidates:
        if current == candidate or current.startswith(candidate + '_'):
            return 'active'
    return ''


@register.simple_tag
def clear_param_url(request, param):
    q = request.GET.copy()
    q.pop(param, None)
    q['page'] = '1'
    return '?' + q.urlencode() if q else request.path


@register.filter
def human_bytes(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'nicht verfügbar'
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    for unit in units:
        if abs(number) < 1024 or unit == units[-1]:
            return f'{number:.1f} {unit}' if unit != 'B' else f'{int(number)} B'
        number /= 1024
    return f'{number:.1f} PB'


@register.simple_tag
def portal_dashboard_extras(request, company=None, membership=None):
    """Return supplemental portal dashboard data without widening tenant scope."""
    from django.db.models import Sum
    from django.utils import timezone

    from apps.companies.models import Membership
    from apps.devices.models import DeviceRegistration
    from apps.licenses.models import License, LicenseAssignment
    from apps.payments.models import Payment

    now = timezone.now()
    result = {
        'active_devices': 0,
        'device_capacity': 0,
        'team_short': [],
        'payment_issue_count': 0,
        'company_data_incomplete': False,
    }

    problematic_payment_statuses = {
        'failed', 'canceled', 'expired', 'chargeback', 'charged_back', 'payment_review'
    }

    if company:
        if not membership or membership.role != 'admin':
            assignments = LicenseAssignment.objects.filter(
                user=request.user,
                ended_at__isnull=True,
                license__company=company,
                license__status='active',
                license__valid_until__gt=now,
            )
            result['active_devices'] = DeviceRegistration.objects.filter(
                user=request.user,
                revoked_at__isnull=True,
            ).count()
            result['device_capacity'] = assignments.aggregate(
                total=Sum('license__product__default_device_limit')
            )['total'] or 0
            return result

        assignments = LicenseAssignment.objects.filter(
            license__company=company,
            ended_at__isnull=True,
            license__status='active',
            license__valid_until__gt=now,
        )
        result['active_devices'] = DeviceRegistration.objects.filter(
            license__company=company,
            revoked_at__isnull=True,
        ).count()
        result['device_capacity'] = assignments.aggregate(
            total=Sum('license__product__default_device_limit')
        )['total'] or 0
        result['team_short'] = list(
            Membership.objects.filter(company=company, active=True)
            .select_related('user')
            .order_by('role', 'user__last_name', 'user__first_name')[:5]
        )
        payment_count = Payment.objects.filter(
            order__company=company,
            status__in=problematic_payment_statuses,
        ).count()
        review_count = License.objects.filter(company=company, status='payment_review').count()
        result['payment_issue_count'] = payment_count + review_count
        required = ('name', 'email', 'street', 'house_number', 'postal_code', 'city', 'country')
        result['company_data_incomplete'] = any(
            not str(getattr(company, field, '') or '').strip() for field in required
        )
        return result

    assignments = LicenseAssignment.objects.filter(
        user=request.user,
        ended_at__isnull=True,
        license__owner_user=request.user,
        license__status='active',
        license__valid_until__gt=now,
    )
    result['active_devices'] = DeviceRegistration.objects.filter(
        user=request.user,
        revoked_at__isnull=True,
    ).count()
    result['device_capacity'] = assignments.aggregate(
        total=Sum('license__product__default_device_limit')
    )['total'] or 0
    result['payment_issue_count'] = Payment.objects.filter(
        order__private_user=request.user,
        status__in=problematic_payment_statuses,
    ).count()
    return result
