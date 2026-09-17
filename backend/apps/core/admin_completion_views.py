from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Company, PrivateCustomerProfile
from apps.integrations.models import IntegrationSecret, ServiceAccount
from apps.legal.models import DeletionRequest, LegalAcceptance
from apps.licenses.models import License
from apps.notifications.models import EmailTemplate
from apps.ops.metrics import snapshot
from apps.ops.models import BackupRecord, SystemAlert
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.support.models import SupportRequest

from .admin_views import staff_perm
from .permissions import has_perm
from .settings_store import get_setting


@staff_perm()
def dashboard(request):
    now = timezone.now()
    rights = {
        name: has_perm(request.user, f'{name}.read')
        for name in ('customers', 'licenses', 'orders', 'payments', 'ops', 'support', 'api', 'settings')
    }
    integration_visible = rights['api'] or rights['settings']
    revenue_trend = []
    if rights['orders']:
        revenue_trend = list(
            Order.objects.filter(status='paid', created_at__gte=now - timedelta(days=180))
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(revenue=Sum('gross_total'), orders=Count('id'))
            .order_by('month')
        )
    product_mix = []
    if rights['licenses']:
        product_mix = list(
            License.objects.values('product__name')
            .annotate(count=Count('id'))
            .order_by('-count', 'product__name')[:8]
        )
    failed_payment_count = None
    chargeback_count = None
    if rights['payments']:
        failed_payment_count = Payment.objects.filter(status__in=['failed', 'canceled', 'expired']).count()
        chargeback_count = Payment.objects.filter(status__in=['charged_back', 'chargeback']).count()
        chargeback_count += License.objects.filter(status='payment_review').count()

    latest_backup = BackupRecord.objects.order_by('-finished_at', '-created_at').first() if rights['ops'] else None
    active_integrations = IntegrationSecret.objects.filter(active=True).count() if integration_visible else None
    active_service_accounts = ServiceAccount.objects.filter(active=True).count() if integration_visible else None
    mollie_configured = bool(get_setting('mollie_profile_id', '')) if integration_visible else None

    context = {
        'rights': rights,
        'integration_visible': integration_visible,
        'customers': Company.objects.count() + PrivateCustomerProfile.objects.count() if rights['customers'] else None,
        'licenses': License.objects.filter(valid_until__gt=now, status__in=['active', 'free']).count() if rights['licenses'] else None,
        'expiring30': License.objects.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=30)).count() if rights['licenses'] else None,
        'expiring60': License.objects.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=60)).count() if rights['licenses'] else None,
        'orders30': Order.objects.filter(created_at__gte=now - timedelta(days=30)).count() if rights['orders'] else None,
        'revenue30': (Order.objects.filter(status='paid', created_at__gte=now - timedelta(days=30)).aggregate(v=Sum('gross_total'))['v'] or 0) if rights['orders'] else None,
        'alerts': SystemAlert.objects.filter(active=True)[:8] if rights['ops'] else [],
        'open_support_count': SupportRequest.objects.exclude(status='closed').count() if rights['support'] else None,
        'ops': snapshot() if rights['ops'] else {},
        'recent_orders': Order.objects.select_related('company', 'private_user').order_by('-created_at')[:8] if rights['orders'] else [],
        'expiring': License.objects.select_related('company', 'owner_user', 'product').filter(valid_until__gt=now).order_by('valid_until')[:8] if rights['licenses'] else [],
        'product_mix': product_mix,
        'revenue_trend': revenue_trend,
        'failed_payment_count': failed_payment_count,
        'chargeback_count': chargeback_count,
        'latest_backup': latest_backup,
        'active_integrations': active_integrations,
        'active_service_accounts': active_service_accounts,
        'mollie_configured': mollie_configured,
    }
    return render(request, 'ns_admin/dashboard.html', context)


@staff_perm('customers.read')
def customer_company(request, pk):
    customer = get_object_or_404(Company, pk=pk)
    return render(request, 'ns_admin/customer_company.html', {'customer': customer})


@staff_perm('customers.read')
def customer_privacy(request, pk):
    customer = get_object_or_404(Company, pk=pk)
    user_ids = customer.memberships.values_list('user_id', flat=True)
    acceptances = (
        LegalAcceptance.objects.filter(user_id__in=user_ids)
        .select_related('user', 'document', 'order')
        .order_by('-accepted_at')[:100]
    )
    deletions = (
        DeletionRequest.objects.filter(user_id__in=user_ids)
        .select_related('user')
        .order_by('-requested_at')[:100]
    )
    return render(
        request,
        'ns_admin/customer_privacy.html',
        {
            'customer': customer,
            'acceptances': acceptances,
            'deletions': deletions,
        },
    )


@staff_perm('email.read')
def email_templates(request):
    return render(
        request,
        'ns_admin/email_templates.html',
        {
            'templates': EmailTemplate.objects.order_by('code'),
            'can_write': has_perm(request.user, 'email.write'),
        },
    )


@staff_perm('roles.read')
def users(request):
    staff_users = (
        User.objects.filter(is_staff=True)
        .prefetch_related('role_links__role')
        .order_by('email')
    )
    return render(
        request,
        'ns_admin/users.html',
        {
            'users': staff_users,
            'can_write': has_perm(request.user, 'roles.write'),
        },
    )
