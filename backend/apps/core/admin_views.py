from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole
from apps.accounts.security import bump_security_version
from apps.audit.models import AuditEvent
from apps.audit.services import audit as write_audit
from apps.catalog.models import Feature, Product
from apps.catalog.services import create_price_version, current_price
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.companies.services import INVITATION_TTL_HOURS, deactivate_company_member, transfer_admin
from apps.devices.models import DeviceRegistration
from apps.devices.services import revoke_device
from apps.integrations.models import ServiceAccount
from apps.legal.models import DeletionRequest, LegalAcceptance, LegalDocument, RetentionPolicy
from apps.licenses.models import License, LicenseTerm
from apps.licenses.services import assign_license, block_license, release_license, unblock_license
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.ops.metrics import caddy_health, certificate_status, snapshot
from apps.ops.models import BackupRecord, RestoreTest, SystemAlert
from apps.orders.models import Order
from apps.payments.models import MollieEvent, Payment
from apps.payments.services import calculate_refund, create_refund_request, submit_refund
from apps.support.models import SupportRequest
from .admin_forms import (
    AdminCompanyForm,
    EmailTemplateForm,
    FeatureForm,
    GeneralSettingsForm,
    DeletionRejectForm,
    LegalDocumentForm,
    RetentionPolicyForm,
    MollieConfigForm,
    PriceVersionForm,
    ProductForm,
    RefundForm,
    RoleForm,
    ServiceAccountForm,
    StaffUserCreateForm,
    StaffUserRoleForm,
    SupportAdminTransferForm,
)
from .datagrid import DataGrid, csv_response
from .permissions import has_perm
from .security import token_pair
from .settings_store import get_setting, set_setting


def staff_perm(code=None):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.is_staff:
                raise PermissionDenied
            if code and not has_perm(request.user, code):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


PASSWORD_RESET_SALT = 'pm-password-reset'
PAYMENT_STATUS_CHOICES = [
    ('created', 'Erstellt'), ('open', 'Offen'), ('pending', 'Ausstehend'),
    ('authorized', 'Autorisiert'), ('paid', 'Bezahlt'), ('failed', 'Fehlgeschlagen'),
    ('canceled', 'Storniert'), ('expired', 'Abgelaufen'),
    ('refunded_partial', 'Teilweise erstattet'), ('refunded_full', 'Vollständig erstattet'),
    ('chargeback', 'Chargeback'), ('chargeback_reversed', 'Chargeback zurückgenommen'), ('unknown', 'Unbekannt'),
]
EMAIL_STATUS_CHOICES = [
    ('queued', 'Warteschlange'), ('sending', 'Wird gesendet'),
    ('sent', 'Gesendet'), ('failed', 'Fehlgeschlagen'),
]
MOLLIE_STATUS_CHOICES = PAYMENT_STATUS_CHOICES + [('error', 'Verarbeitungsfehler'), ('recovered', 'Fehler behoben')]


def _active_superadmin_count():
    built_in = User.objects.filter(is_staff=True, is_active=True, is_superuser=True).count()
    role_users = User.objects.filter(
        is_staff=True,
        is_active=True,
        is_superuser=False,
        role_links__role__code='superadmin',
        role_links__role__active=True,
    ).distinct().count()
    return built_in + role_users


def _send_staff_setup_email(request, user):
    from apps.notifications.services import queue_email
    token = signing.dumps(
        {'uid': str(user.id), 'email': user.email, 'sv': int(user.security_version)},
        salt=PASSWORD_RESET_SALT,
    )
    url = request.build_absolute_uri(reverse('accounts:password_reset_confirm', args=[token]))
    queue_email('staff_invite', user.email, {'url': url})



def _grid_export(request, grid, columns, filename):
    if request.GET.get('export') == 'csv':
        # Export actions can contain customer, license, payment or audit data.
        # Record the operation without persisting the user's raw search text.
        write_audit(
            request.user,
            'datagrid.exported',
            request.user,
            {
                'filename': filename,
                'rows': grid.page.paginator.count,
                'filtered': bool(grid.query or grid.filters),
            },
            request=request,
        )
        return csv_response(grid.queryset, columns, filename)
    return None


@staff_perm()
def dashboard(request):
    now = timezone.now()
    rights = {
        name: has_perm(request.user, f'{name}.read')
        for name in ('customers', 'licenses', 'orders', 'ops', 'support')
    }
    paid_orders = Order.objects.filter(status='paid')
    revenue_since = now - timedelta(days=185)

    product_mix = (
        list(
            License.objects.values('product__name')
            .annotate(total=Count('id'))
            .order_by('-total', 'product__name')[:8]
        )
        if rights['licenses'] else []
    )
    product_total = sum(row['total'] for row in product_mix)
    for row in product_mix:
        row['percent'] = round((row['total'] / product_total) * 100, 1) if product_total else 0

    revenue_months = (
        list(
            paid_orders.filter(created_at__gte=revenue_since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('gross_total'), orders=Count('id'))
            .order_by('month')
        )
        if rights['orders'] else []
    )
    revenue_peak = max((float(row['total'] or 0) for row in revenue_months), default=0)
    for row in revenue_months:
        row['percent'] = round((float(row['total'] or 0) / revenue_peak) * 100, 1) if revenue_peak else 0

    failed_payment_count = Payment.objects.filter(status='failed').count() if rights['orders'] else None
    chargeback_count = Payment.objects.filter(status='chargeback').count() if rights['orders'] else None
    active_alerts = list(SystemAlert.objects.filter(active=True)[:8]) if rights['ops'] else []
    open_support_count = SupportRequest.objects.exclude(status='closed').count() if rights['support'] else None

    context = {
        'rights': rights,
        'customers': Company.objects.count() + PrivateCustomerProfile.objects.count() if rights['customers'] else None,
        'licenses': License.objects.filter(valid_until__gt=now, status__in=['active', 'free']).count() if rights['licenses'] else None,
        'expiring30': License.objects.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=30)).count() if rights['licenses'] else None,
        'expiring60': License.objects.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=60)).count() if rights['licenses'] else None,
        'orders30': Order.objects.filter(created_at__gte=now - timedelta(days=30)).count() if rights['orders'] else None,
        'revenue30': (
            paid_orders.filter(created_at__gte=now - timedelta(days=30))
            .aggregate(v=Sum('gross_total'))['v'] or 0
        ) if rights['orders'] else None,
        'product_mix': product_mix,
        'product_total': product_total,
        'revenue_months': revenue_months,
        'failed_payment_count': failed_payment_count,
        'chargeback_count': chargeback_count,
        'alerts': active_alerts,
        'open_support_count': open_support_count,
        'system_healthy': bool(
            rights['ops']
            and not active_alerts
            and not (failed_payment_count or 0)
            and not (chargeback_count or 0)
        ),
        'ops': snapshot() if rights['ops'] else {},
        'backup': BackupRecord.objects.order_by('-finished_at', '-created_at').first() if rights['ops'] else None,
        'restore': RestoreTest.objects.order_by('-started_at').first() if rights['ops'] else None,
        'integration_status': {
            'mollie': bool(get_setting('mollie_profile_id', '') or settings.MOLLIE_PROFILE_ID),
            'mail_provider': settings.EMAIL_PROVIDER,
            'graph_configured': bool(
                settings.GRAPH_TENANT_ID
                and settings.GRAPH_CLIENT_ID
                and settings.GRAPH_CLIENT_SECRET
                and settings.GRAPH_SENDER
            ),
        } if rights['ops'] else {},
        'recent_orders': Order.objects.select_related('company', 'private_user').order_by('-created_at')[:8] if rights['orders'] else [],
        'expiring': License.objects.select_related('company', 'owner_user', 'product').filter(valid_until__gt=now).order_by('valid_until')[:8] if rights['licenses'] else [],
    }
    return render(request, 'ns_admin/dashboard.html', context)


@staff_perm('customers.read')
def customers(request):
    grid = DataGrid(
        request,
        Company.objects.all(),
        search_fields=('customer_number', 'name', 'email'),
        sort_fields={'number': 'customer_number', 'name': 'name', 'created': 'created_at', 'status': 'status'},
        default_sort='name',
        filters={'status': 'status', 'country': 'country'},
    ).build()
    export = _grid_export(
        request,
        grid,
        [('customer_number', 'Kundennummer'), ('name', 'Kunde'), ('email', 'E-Mail'), ('status', 'Status')],
        'promptmaster-kunden.csv',
    )
    if export:
        return export
    return render(
        request,
        'ns_admin/grid.html',
        {
            'title': 'Kunden',
            'grid': grid,
            'columns': [
                ('customer_number', 'Kundennummer', 'number'),
                ('name', 'Kunde', 'name'),
                ('email', 'E-Mail', None),
                ('status', 'Status', 'status'),
            ],
            'detail_route': 'ns_admin:customer_detail',
            'filter_options': [('status', 'Status', Company.STATUS), ('country', 'Land', [('DE', 'Deutschland')])],
            'export_enabled': True,
            'customer_tabs': True,
            'customer_type': 'company',
        },
    )


@staff_perm('customers.read')
def private_customers(request):
    grid = DataGrid(
        request,
        PrivateCustomerProfile.objects.select_related('user'),
        search_fields=('customer_number', 'user__email', 'user__first_name', 'user__last_name', 'city'),
        sort_fields={'number': 'customer_number', 'name': 'user__last_name', 'email': 'user__email', 'created': 'created_at'},
        default_sort='user__last_name',
        filters={'country': 'country'},
    ).build()
    export = _grid_export(
        request,
        grid,
        [('customer_number', 'Kundennummer'), ('user.full_name', 'Name'), ('user.email', 'E-Mail'), ('country', 'Land')],
        'promptmaster-privatkunden.csv',
    )
    if export:
        return export
    return render(
        request,
        'ns_admin/grid.html',
        {
            'title': 'Privatkunden',
            'grid': grid,
            'columns': [
                ('customer_number', 'Kundennummer', 'number'),
                ('user', 'Kunde', 'name'),
                ('user.email', 'E-Mail', 'email'),
                ('country', 'Land', None),
            ],
            'detail_route': 'ns_admin:private_customer_detail',
            'filter_options': [('country', 'Land', [('DE', 'Deutschland')])],
            'export_enabled': True,
            'customer_tabs': True,
            'customer_type': 'private',
        },
    )


def _private_customer(request, pk):
    return get_object_or_404(PrivateCustomerProfile.objects.select_related('user'), pk=pk)


@staff_perm('customers.read')
def private_customer_detail(request, pk):
    profile = _private_customer(request, pk)
    user = profile.user
    return render(request, 'ns_admin/private_customer_detail.html', {
        'profile': profile,
        'customer_user': user,
        'license_count': user.owned_licenses.count(),
        'order_count': user.private_orders.count(),
        'device_count': user.devices.filter(revoked_at__isnull=True).count(),
    })


@staff_perm('customers.read')
def private_customer_portal_preview(request, pk):
    profile = _private_customer(request, pk)
    user = profile.user
    licenses = user.owned_licenses.select_related('product')
    now = timezone.now()
    return render(request, 'ns_admin/customer_portal_preview.html', {
        'preview_kind': 'private', 'preview_title': user.full_name or user.email,
        'preview_subtitle': f'{profile.customer_number} · Privatkonto', 'preview_user': user,
        'preview_company': None, 'license_total': licenses.count(),
        'license_free': licenses.filter(status='free', valid_until__gt=now).count(),
        'license_active': licenses.filter(status='active', valid_until__gt=now).count(),
        'expiring_30': licenses.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=30)).count(),
        'device_count': user.devices.filter(revoked_at__isnull=True).count(), 'order_count': user.private_orders.count(),
        'member_count': 1, 'back_route': 'ns_admin:private_customer_detail', 'back_pk': profile.pk,
    })


@staff_perm('licenses.read')
def private_customer_licenses(request, pk):
    profile = _private_customer(request, pk)
    grid = DataGrid(request, profile.user.owned_licenses.select_related('product'), search_fields=('license_number', 'product__name'), sort_fields={'number':'license_number','expiry':'valid_until','status':'status'}, default_sort='valid_until', filters={'status':'status'}).build()
    return render(request, 'ns_admin/private_customer_grid.html', {'profile': profile, 'title':'Lizenzen', 'kind':'licenses', 'grid':grid, 'filter_options':[('status','Status',License.STATUS)]})


@staff_perm('customers.read')
def private_customer_devices(request, pk):
    profile = _private_customer(request, pk)
    grid = DataGrid(
        request,
        profile.user.devices.select_related('license'),
        search_fields=('display_name', 'os_family', 'browser_family'),
        sort_fields={'device': 'display_name', 'last': 'last_seen_at'},
        default_sort='-last_seen_at',
    ).build()
    return render(
        request,
        'ns_admin/private_customer_grid.html',
        {
            'profile': profile,
            'title': 'Geräte',
            'kind': 'devices',
            'grid': grid,
            'filter_options': [],
            'can_revoke_devices': has_perm(request.user, 'devices.write'),
        },
    )


@staff_perm('devices.write')
def private_customer_device_revoke(request, pk, device_id):
    if request.method != 'POST' or not has_perm(request.user, 'customers.read'):
        raise PermissionDenied
    profile = _private_customer(request, pk)
    device = get_object_or_404(
        DeviceRegistration.objects.select_related('user', 'license'),
        pk=device_id,
        user=profile.user,
    )
    revoke_device(device, request.user, request=request)
    messages.success(request, 'Gerät wurde widerrufen.')
    return redirect('ns_admin:private_customer_devices', pk=profile.pk)


@staff_perm('orders.read')
def private_customer_orders(request, pk):
    profile = _private_customer(request, pk)
    grid = DataGrid(request, profile.user.private_orders.all(), search_fields=('order_number',), sort_fields={'number':'order_number','date':'created_at','amount':'gross_total','status':'status'}, default_sort='-created_at', filters={'status':'status'}).build()
    return render(request, 'ns_admin/private_customer_grid.html', {'profile': profile, 'title':'Bestellungen', 'kind':'orders', 'grid':grid, 'filter_options':[('status','Status',Order.STATUS)]})


@staff_perm('payments.read')
def private_customer_payments(request, pk):
    profile = _private_customer(request, pk)
    grid = DataGrid(request, Payment.objects.filter(order__private_user=profile.user).select_related('order'), search_fields=('provider_payment_id','order__order_number'), sort_fields={'date':'created_at','amount':'amount','status':'status'}, default_sort='-created_at', filters={'status':'status'}).build()
    return render(request, 'ns_admin/private_customer_grid.html', {'profile': profile, 'title':'Zahlungen', 'kind':'payments', 'grid':grid, 'filter_options':[('status','Status',PAYMENT_STATUS_CHOICES)]})


@staff_perm('email.read')
def private_customer_emails(request, pk):
    profile = _private_customer(request, pk)
    grid = DataGrid(request, EmailMessage.objects.filter(recipient=profile.user.email).select_related('template'), search_fields=('recipient','subject'), sort_fields={'date':'created_at','status':'status'}, default_sort='-created_at', filters={'status':'status'}).build()
    return render(request, 'ns_admin/private_customer_grid.html', {'profile': profile, 'title':'E-Mail-Historie', 'kind':'emails', 'grid':grid, 'filter_options':[('status','Status',EMAIL_STATUS_CHOICES)]})


@staff_perm('audit.read')
def private_customer_audit(request, pk):
    profile = _private_customer(request, pk)
    object_ids = {str(profile.id), str(profile.user_id)}
    object_ids.update(str(v) for v in profile.user.owned_licenses.values_list('id', flat=True))
    grid = DataGrid(request, AuditEvent.objects.filter(object_id__in=object_ids).select_related('actor'), search_fields=('action','object_type','object_id','actor__email'), sort_fields={'time':'created_at','action':'action'}, default_sort='-created_at').build()
    return render(request, 'ns_admin/private_customer_grid.html', {'profile': profile, 'title':'Audit', 'kind':'audit', 'grid':grid, 'filter_options':[]})


def _customer(request, pk):
    return get_object_or_404(Company, pk=pk)


@staff_perm('customers.read')
def customer_detail(request, pk):
    customer = _customer(request, pk)
    return render(
        request,
        'ns_admin/customer_detail.html',
        {
            'customer': customer,
            'member_count': customer.memberships.filter(active=True).count(),
            'license_count': customer.licenses.count(),
            'order_count': customer.orders.count(),
        },
    )


@staff_perm('customers.read')
def customer_company(request, pk):
    customer = _customer(request, pk)
    can_write = has_perm(request.user, 'customers.write')
    if request.method == 'POST' and not can_write:
        raise PermissionDenied

    before = {
        field: getattr(customer, field)
        for field in AdminCompanyForm.Meta.fields
    }
    form = AdminCompanyForm(request.POST or None, instance=customer)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        after = {
            field: getattr(saved, field)
            for field in AdminCompanyForm.Meta.fields
        }
        changes = {
            field: {'before': str(before[field]), 'after': str(after[field])}
            for field in after
            if before[field] != after[field]
        }
        if changes:
            write_audit(
                request.user,
                'company.updated',
                saved,
                {'changes': changes},
                request=request,
            )
        messages.success(request, 'Unternehmensdaten gespeichert.')
        return redirect('ns_admin:customer_company', pk=saved.pk)

    return render(
        request,
        'ns_admin/customer_company.html',
        {'customer': customer, 'form': form, 'can_write': can_write},
    )


@staff_perm('customers.read')
def customer_portal_preview(request, pk):
    customer = _customer(request, pk)
    licenses = customer.licenses.select_related('product')
    now = timezone.now()
    admin_membership = customer.memberships.filter(active=True, role='admin').select_related('user').first()
    return render(request, 'ns_admin/customer_portal_preview.html', {
        'preview_kind': 'company', 'preview_title': customer.name,
        'preview_subtitle': f'{customer.customer_number} · Firmenkonto',
        'preview_user': admin_membership.user if admin_membership else None, 'preview_company': customer,
        'license_total': licenses.count(), 'license_free': licenses.filter(status='free', valid_until__gt=now).count(),
        'license_active': licenses.filter(status='active', valid_until__gt=now).count(),
        'expiring_30': licenses.filter(valid_until__gt=now, valid_until__lte=now + timedelta(days=30)).count(),
        'device_count': DeviceRegistration.objects.filter(user__company_memberships__company=customer, user__company_memberships__active=True, revoked_at__isnull=True).distinct().count(),
        'order_count': customer.orders.count(), 'member_count': customer.memberships.filter(active=True).count(),
        'back_route': 'ns_admin:customer_detail', 'back_pk': customer.pk,
    })


@staff_perm('customers.read')
def customer_users(request, pk):
    customer = _customer(request, pk)
    grid = DataGrid(
        request,
        customer.memberships.select_related('user'),
        search_fields=('user__email', 'user__first_name', 'user__last_name'),
        sort_fields={'name': 'user__last_name', 'email': 'user__email', 'role': 'role', 'created': 'created_at'},
        default_sort='user__last_name',
        filters={'role': 'role', 'active': 'active'},
    ).build()
    return render(
        request,
        'ns_admin/customer_grid.html',
        {
            'customer': customer,
            'title': 'Benutzer',
            'grid': grid,
            'kind': 'users',
            'filter_options': [
                ('role', 'Rolle', Membership.ROLE),
                ('active', 'Status', [('True', 'Aktiv'), ('False', 'Inaktiv')]),
            ],
            'can_manage_users': has_perm(request.user, 'customers.write'),
        },
    )


@staff_perm('customers.write')
def customer_admin_transfer(request, pk, user_id):
    customer = _customer(request, pk)
    target = get_object_or_404(
        Membership.objects.select_related('user'),
        company=customer,
        user_id=user_id,
        active=True,
    )
    current_admin = get_object_or_404(
        Membership.objects.select_related('user'),
        company=customer,
        role='admin',
        active=True,
    )
    if target.pk == current_admin.pk:
        messages.info(request, 'Dieser Benutzer ist bereits Firmenadministrator.')
        return redirect('ns_admin:customer_users', pk=customer.pk)

    form = SupportAdminTransferForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            transfer_admin(
                customer,
                current_admin.user,
                target.user,
                actor=request.user,
                request=request,
                audit_context={
                    'identity_verified': True,
                    'verification_note_present': bool(form.cleaned_data.get('note')),
                },
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(
                request,
                f'Firmenadministrator wurde auf {target.user.email} übertragen.',
            )
            return redirect('ns_admin:customer_users', pk=customer.pk)

    return render(
        request,
        'ns_admin/form.html',
        {
            'title': f'Firmenadministrator übertragen · {target.user.email}',
            'form': form,
            'cancel_url': reverse('ns_admin:customer_users', args=[customer.pk]),
        },
    )


@staff_perm('customers.write')
def customer_user_deactivate(request, pk, user_id):
    if request.method != 'POST':
        raise PermissionDenied
    customer = _customer(request, pk)
    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=customer,
        user_id=user_id,
        active=True,
    )
    try:
        deactivate_company_member(
            company=customer,
            member=member,
            actor=request.user,
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(
            request,
            'Benutzer deaktiviert; Lizenz- und Gerätezugänge wurden freigegeben.',
        )
    return redirect('ns_admin:customer_users', pk=customer.pk)


@staff_perm('customers.read')
def customer_licenses(request, pk):
    customer = _customer(request, pk)
    grid = DataGrid(
        request,
        customer.licenses.select_related('product'),
        search_fields=('license_number', 'product__name'),
        sort_fields={'number': 'license_number', 'expiry': 'valid_until', 'status': 'status'},
        default_sort='valid_until',
        filters={'status': 'status'},
    ).build()
    return render(request, 'ns_admin/customer_grid.html', {'customer': customer, 'title': 'Lizenzen', 'grid': grid, 'kind': 'licenses', 'filter_options': [('status', 'Status', License.STATUS)]})


@staff_perm('customers.read')
def customer_devices(request, pk):
    customer = _customer(request, pk)
    grid = DataGrid(
        request,
        DeviceRegistration.objects.filter(user__company_memberships__company=customer).select_related('user', 'license'),
        search_fields=('display_name', 'user__email'),
        sort_fields={'device': 'display_name', 'last': 'last_seen_at', 'user': 'user__email'},
        default_sort='-last_seen_at',
    ).build()
    return render(
        request,
        'ns_admin/customer_grid.html',
        {
            'customer': customer,
            'title': 'Geräte',
            'grid': grid,
            'kind': 'devices',
            'filter_options': [],
            'can_revoke_devices': has_perm(request.user, 'devices.write'),
        },
    )


@staff_perm('devices.write')
def customer_device_revoke(request, pk, device_id):
    if request.method != 'POST' or not has_perm(request.user, 'customers.read'):
        raise PermissionDenied
    customer = _customer(request, pk)
    device = get_object_or_404(
        DeviceRegistration.objects.select_related('user', 'license'),
        pk=device_id,
        user__company_memberships__company=customer,
        user__company_memberships__active=True,
    )
    revoke_device(device, request.user, request=request)
    messages.success(request, 'Gerät wurde widerrufen.')
    return redirect('ns_admin:customer_devices', pk=customer.pk)


@staff_perm('orders.read')
def customer_orders(request, pk):
    customer = _customer(request, pk)
    grid = DataGrid(
        request,
        customer.orders.all(),
        search_fields=('order_number',),
        sort_fields={'number': 'order_number', 'date': 'created_at', 'amount': 'gross_total', 'status': 'status'},
        default_sort='-created_at',
        filters={'status': 'status'},
    ).build()
    return render(request, 'ns_admin/customer_grid.html', {'customer': customer, 'title': 'Bestellungen', 'grid': grid, 'kind': 'orders', 'filter_options': [('status', 'Status', Order.STATUS)]})


@staff_perm('payments.read')
def customer_payments(request, pk):
    customer = _customer(request, pk)
    grid = DataGrid(
        request,
        Payment.objects.filter(order__company=customer).select_related('order'),
        search_fields=('provider_payment_id', 'order__order_number'),
        sort_fields={'date': 'created_at', 'amount': 'amount', 'status': 'status'},
        default_sort='-created_at',
        filters={'status': 'status'},
    ).build()
    return render(request, 'ns_admin/customer_grid.html', {'customer': customer, 'title': 'Zahlungen', 'grid': grid, 'kind': 'payments', 'filter_options': [('status','Status',PAYMENT_STATUS_CHOICES)]})


@staff_perm('email.read')
def customer_emails(request, pk):
    customer = _customer(request, pk)
    recipients = list(customer.memberships.values_list('user__email', flat=True))
    recipients.append(customer.email)
    grid = DataGrid(
        request,
        EmailMessage.objects.filter(recipient__in=set(recipients)).select_related('template'),
        search_fields=('recipient', 'subject'),
        sort_fields={'date': 'created_at', 'status': 'status', 'recipient': 'recipient'},
        default_sort='-created_at',
        filters={'status': 'status'},
    ).build()
    return render(request, 'ns_admin/customer_grid.html', {'customer': customer, 'title': 'E-Mail-Historie', 'grid': grid, 'kind': 'emails', 'filter_options': [('status','Status',EMAIL_STATUS_CHOICES)]})


@staff_perm('legal.read')
def customer_privacy(request, pk):
    customer = _customer(request, pk)
    user_ids = list(
        customer.memberships.values_list('user_id', flat=True)
    )
    acceptances = (
        LegalAcceptance.objects.filter(user_id__in=user_ids)
        .select_related('user', 'document', 'order')
        .order_by('-accepted_at')[:30]
    )
    deletions = (
        DeletionRequest.objects.filter(user_id__in=user_ids)
        .select_related('user')
        .order_by('-requested_at')[:30]
    )
    return render(
        request,
        'ns_admin/customer_privacy.html',
        {
            'customer': customer,
            'acceptances': acceptances,
            'deletions': deletions,
            'acceptance_count': LegalAcceptance.objects.filter(user_id__in=user_ids).count(),
            'deletion_count': DeletionRequest.objects.filter(user_id__in=user_ids).count(),
        },
    )


@staff_perm('audit.read')
def customer_audit(request, pk):
    customer = _customer(request, pk)
    object_ids = {str(customer.id)}
    object_ids.update(str(value) for value in customer.memberships.values_list('user_id', flat=True))
    object_ids.update(str(value) for value in customer.licenses.values_list('id', flat=True))
    grid = DataGrid(
        request,
        AuditEvent.objects.filter(object_id__in=object_ids).select_related('actor'),
        search_fields=('action', 'object_type', 'object_id', 'actor__email'),
        sort_fields={'time': 'created_at', 'action': 'action'},
        default_sort='-created_at',
    ).build()
    return render(request, 'ns_admin/customer_grid.html', {'customer': customer, 'title': 'Audit', 'grid': grid, 'kind': 'audit', 'filter_options': []})


@staff_perm('licenses.read')
def licenses(request):
    grid = DataGrid(
        request,
        License.objects.select_related('company', 'owner_user', 'product'),
        search_fields=('license_number', 'company__name', 'owner_user__email', 'product__name'),
        sort_fields={'number': 'license_number', 'expiry': 'valid_until', 'status': 'status', 'company': 'company__name'},
        default_sort='valid_until',
        filters={'status': 'status', 'product': 'product__code'},
    ).build()
    products = [(p.code, p.name) for p in Product.objects.filter(active=True).order_by('name')]
    export = _grid_export(request, grid, [('license_number', 'Lizenz-ID'), ('company.name', 'Unternehmen'), ('owner_user.email', 'Privatkunde'), ('product.name', 'Produkt'), ('valid_until', 'Ablauf'), ('status', 'Status')], 'promptmaster-lizenzen.csv')
    if export:
        return export
    return render(request, 'ns_admin/grid.html', {'title': 'Lizenzen', 'grid': grid, 'columns': [('license_number', 'Lizenz-ID', 'number'), ('company', 'Kunde', 'company'), ('product', 'Produkt', None), ('valid_until', 'Ablauf', 'expiry'), ('status', 'Status', 'status')], 'detail_route': 'ns_admin:license_detail', 'filter_options': [('status', 'Status', License.STATUS), ('product', 'Produkt', products)], 'export_enabled': True})


@staff_perm('licenses.read')
def license_detail(request, pk):
    license_obj = get_object_or_404(
        License.objects.select_related('company', 'owner_user', 'product'),
        pk=pk,
    )
    terms = list(
        license_obj.terms.select_related('order_item__order').order_by('-valid_until')
    )
    active_assignment = (
        license_obj.assignments.filter(ended_at__isnull=True)
        .select_related('user')
        .first()
    )
    eligible_members = []
    if license_obj.company_id:
        eligible_members = list(
            Membership.objects.filter(
                company=license_obj.company,
                active=True,
                user__is_active=True,
            )
            .select_related('user')
            .order_by('user__last_name', 'user__first_name', 'user__email')
        )
    refund_preview = {}
    for term in terms:
        if term.status == 'active':
            refund_preview[str(term.id)] = calculate_refund(term)
    return render(
        request,
        'ns_admin/license_detail.html',
        {
            'license': license_obj,
            'terms': terms,
            'active_assignment': active_assignment,
            'eligible_members': eligible_members,
            'refund_preview': refund_preview,
            'can_write': has_perm(request.user, 'licenses.write'),
            'can_refund': has_perm(request.user, 'payments.refund'),
        },
    )


@staff_perm('licenses.write')
def license_assign(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    license_obj = get_object_or_404(
        License.objects.select_related('company', 'product'),
        pk=pk,
    )
    if not license_obj.company_id:
        raise PermissionDenied
    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=license_obj.company,
        user_id=request.POST.get('user_id'),
        active=True,
        user__is_active=True,
    )
    try:
        assign_license(license_obj, member.user, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, f'Lizenz wurde {member.user.email} zugewiesen.')
    return redirect('ns_admin:license_detail', pk=license_obj.pk)


@staff_perm('licenses.write')
def license_release(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    license_obj = get_object_or_404(License, pk=pk)
    if not license_obj.assignments.filter(ended_at__isnull=True).exists():
        messages.info(request, 'Die Lizenz ist bereits frei.')
        return redirect('ns_admin:license_detail', pk=license_obj.pk)
    release_license(license_obj, request.user)
    messages.success(request, 'Lizenzzuweisung wurde freigegeben.')
    return redirect('ns_admin:license_detail', pk=license_obj.pk)


@staff_perm('licenses.write')
def license_block_toggle(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    license_obj = get_object_or_404(License, pk=pk)
    try:
        if license_obj.status == 'blocked':
            unblock_license(license_obj, request.user, request=request)
            messages.success(request, 'Lizenz wurde entsperrt.')
        else:
            block_license(license_obj, request.user, request=request)
            messages.success(request, 'Lizenz wurde gesperrt; vorhandene Gerätezugänge wurden widerrufen.')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect('ns_admin:license_detail', pk=pk)


@staff_perm('payments.refund')
def license_refund(request, pk, term_id):
    if request.method != 'POST':
        raise PermissionDenied
    license_obj = get_object_or_404(License, pk=pk)
    term = get_object_or_404(LicenseTerm, pk=term_id, license=license_obj)
    form = RefundForm(request.POST)
    if form.is_valid():
        try:
            refund = create_refund_request(term=term, actor=request.user, reason=form.cleaned_data['reason'])
            submit_refund(refund)
        except (ValidationError, Exception) as exc:
            # Provider errors are intentionally surfaced as a safe generic UI
            # message while detailed stack traces remain in server logs.
            messages.error(request, str(exc) if isinstance(exc, ValidationError) else 'Erstattung konnte nicht an Mollie übermittelt werden.')
        else:
            messages.success(request, 'Erstattung wurde an Mollie übermittelt.')
    else:
        messages.error(request, 'Bestätigung für die Erstattung fehlt.')
    return redirect('ns_admin:license_detail', pk=pk)


@staff_perm('orders.read')
def orders(request):
    grid = DataGrid(request, Order.objects.select_related('company', 'private_user'), search_fields=('order_number', 'company__name', 'private_user__email'), sort_fields={'number': 'order_number', 'date': 'created_at', 'amount': 'gross_total', 'status': 'status'}, default_sort='-created_at', filters={'status': 'status'}).build()
    export = _grid_export(request, grid, [('order_number', 'Bestellung'), ('company.name', 'Unternehmen'), ('private_user.email', 'Privatkunde'), ('gross_total', 'Betrag'), ('status', 'Status'), ('created_at', 'Datum')], 'promptmaster-bestellungen.csv')
    if export:
        return export
    return render(request, 'ns_admin/grid.html', {'title': 'Bestellungen', 'grid': grid, 'columns': [('order_number', 'Bestellung', 'number'), ('company', 'Kunde', None), ('gross_total', 'Betrag', 'amount'), ('status', 'Status', 'status'), ('created_at', 'Datum', 'date')], 'detail_route': 'ns_admin:order_detail', 'filter_options': [('status', 'Status', Order.STATUS)], 'export_enabled': True})


@staff_perm('orders.read')
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('company', 'private_user').prefetch_related('items__product', 'payments'), pk=pk)
    return render(request, 'ns_admin/order_detail.html', {'order': order})


@staff_perm('payments.read')
def payments(request):
    queryset = Payment.objects.select_related('order', 'order__company', 'order__private_user')
    grid = DataGrid(request, queryset, search_fields=('provider_payment_id', 'order__order_number', 'order__company__name', 'order__private_user__email'), sort_fields={'date': 'created_at', 'amount': 'amount', 'status': 'status'}, default_sort='-created_at', filters={'status': 'status'}).build()
    return render(
        request,
        'ns_admin/payments.html',
        {
            'grid': grid,
            'filter_options': [('status','Status',PAYMENT_STATUS_CHOICES)],
            'payment_counts': {
                'paid': Payment.objects.filter(status='paid').count(),
                'open': Payment.objects.filter(status__in=['created', 'open', 'pending', 'authorized']).count(),
                'failed': Payment.objects.filter(status='failed').count(),
                'chargeback': Payment.objects.filter(status='chargeback').count(),
            },
        },
    )


@staff_perm('products.read')
def products(request):
    product_rows = list(
        Product.objects.prefetch_related('prices', 'entitlements__feature').order_by('name')
    )
    for product in product_rows:
        product.current_new_price = current_price(product, 'new')
        product.current_renewal_price = current_price(product, 'renewal')
    return render(request, 'ns_admin/products.html', {'products': product_rows})


@staff_perm('products.write')
def product_new(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        write_audit(request.user, 'product.created', saved, {'code': saved.code}, request=request)
        messages.success(request, 'Produkt angelegt. Legen Sie anschließend Preisversionen an.')
        return redirect('ns_admin:product_edit', pk=saved.pk)
    return render(request, 'ns_admin/form.html', {'title': 'Produkt anlegen', 'form': form, 'cancel_url': reverse('ns_admin:products')})


@staff_perm('products.read')
def features(request):
    grid = DataGrid(request, Feature.objects.all(), search_fields=('code','name'), sort_fields={'code':'code','name':'name'}, default_sort='name').build()
    return render(request, 'ns_admin/features.html', {'grid':grid, 'filter_options':[]})


@staff_perm('products.write')
def feature_edit(request, pk=None):
    feature = get_object_or_404(Feature, pk=pk) if pk else None
    form = FeatureForm(request.POST or None, instance=feature)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        write_audit(request.user, 'feature.saved', saved, {'code': saved.code}, request=request)
        messages.success(request, 'Feature gespeichert.')
        return redirect('ns_admin:features')
    return render(request, 'ns_admin/form.html', {'title':'Feature bearbeiten' if feature else 'Feature anlegen', 'form':form, 'cancel_url': reverse('ns_admin:features')})


@staff_perm('products.write')
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        write_audit(request.user, 'product.updated', saved, {'fields': list(form.changed_data)}, request=request)
        messages.success(request, 'Produkt gespeichert.')
        return redirect('ns_admin:product_edit', pk=pk)
    return render(request, 'ns_admin/product_edit.html', {'product': product, 'form': form, 'prices': product.prices.order_by('-valid_from')})


@staff_perm('products.write')
def product_price_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = PriceVersionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            price = create_price_version(product=product, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            write_audit(request.user, 'product.price_created', price, {'gross_amount': str(price.gross_amount), 'type': price.price_type}, request=request)
            messages.success(request, 'Neue Preisversion angelegt.')
            return redirect('ns_admin:product_edit', pk=pk)
    return render(request, 'ns_admin/form.html', {'title': f'Preisversion · {product.name}', 'form': form, 'cancel_url': reverse('ns_admin:product_edit', args=[product.pk])})


@staff_perm('email.read')
def email(request):
    provider = settings.EMAIL_PROVIDER.lower().strip()
    graph_configured = all(
        [
            settings.GRAPH_TENANT_ID,
            settings.GRAPH_CLIENT_ID,
            settings.GRAPH_CLIENT_SECRET,
            settings.GRAPH_SENDER,
        ]
    )
    provider_configured = (
        bool(settings.EMAIL_HOST)
        if provider in {'smtp', 'mailpit'}
        else graph_configured
        if provider in {'graph', 'microsoft_graph'}
        else False
    )
    return render(
        request,
        'ns_admin/email.html',
        {
            'templates': EmailTemplate.objects.order_by('code'),
            'recent': EmailMessage.objects.select_related('template').order_by('-created_at')[:20],
            'provider': provider,
            'provider_configured': provider_configured,
            'graph_sender': settings.GRAPH_SENDER,
        },
    )


@staff_perm('email.write')
def email_template_edit(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    form = EmailTemplateForm(request.POST or None, instance=template)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        write_audit(request.user, 'email_template.updated', saved, {'fields': list(form.changed_data)}, request=request)
        messages.success(request, 'E-Mail-Vorlage gespeichert.')
        return redirect('ns_admin:email')
    return render(request, 'ns_admin/form.html', {'title': f'E-Mail-Vorlage · {template.code}', 'form': form, 'cancel_url': reverse('ns_admin:email')})


@staff_perm('email.read')
def email_log(request):
    grid = DataGrid(request, EmailMessage.objects.select_related('template'), search_fields=('recipient', 'subject', 'template__code'), sort_fields={'date': 'created_at', 'recipient': 'recipient', 'status': 'status'}, default_sort='-created_at', filters={'status': 'status'}).build()
    return render(request, 'ns_admin/email_log.html', {'grid': grid, 'filter_options': [('status','Status',EMAIL_STATUS_CHOICES)]})


@staff_perm('payments.read')
def mollie(request):
    from apps.integrations.services import get_secret

    profile = get_setting('mollie_profile_id', settings.MOLLIE_PROFILE_ID)
    api_key = get_secret('mollie_api_key', settings.MOLLIE_API_KEY)
    if api_key.startswith('live_'):
        mode = 'LIVE'
    elif api_key:
        mode = 'TEST'
    else:
        mode = 'NICHT KONFIGURIERT'
    events = MollieEvent.objects.order_by('-created_at')[:20]
    return render(
        request,
        'ns_admin/mollie.html',
        {
            'profile_id': profile,
            'configured': bool(api_key and profile),
            'mode': mode,
            'webhook_base': settings.MOLLIE_WEBHOOK_BASE,
            'payments': Payment.objects.order_by('-created_at')[:20],
            'events': events,
            'last_event': events[0] if events else None,
            'can_configure': has_perm(request.user, 'settings.write'),
        },
    )


@staff_perm('settings.write')
def mollie_config(request):
    from apps.integrations.services import set_secret

    form = MollieConfigForm(request.POST or None, initial={'profile_id': get_setting('mollie_profile_id', '')})
    if request.method == 'POST' and form.is_valid():
        set_setting('mollie_profile_id', form.cleaned_data['profile_id'])
        if form.cleaned_data['api_key']:
            set_secret('mollie_api_key', form.cleaned_data['api_key'])
        write_audit(request.user, 'mollie.configuration_updated', request.user, {'profile_id': form.cleaned_data['profile_id'], 'api_key': '[REDACTED]' if form.cleaned_data['api_key'] else 'unchanged'}, request=request)
        messages.success(request, 'Mollie-Konfiguration gespeichert.')
        return redirect('ns_admin:mollie')
    return render(request, 'ns_admin/form.html', {'title': 'Mollie konfigurieren', 'form': form, 'cancel_url': reverse('ns_admin:mollie')})


@staff_perm('payments.read')
def mollie_events(request):
    grid = DataGrid(request, MollieEvent.objects.select_related('payment'), search_fields=('event_key', 'payment__provider_payment_id', 'provider_status'), sort_fields={'date': 'created_at', 'status': 'provider_status'}, default_sort='-created_at', filters={'provider_status': 'provider_status'}).build()
    return render(request, 'ns_admin/mollie_events.html', {'grid': grid, 'filter_options': [('provider_status','Status',MOLLIE_STATUS_CHOICES)]})


@staff_perm()
def stats(request):
    now = timezone.now()
    rights = {
        'customers': has_perm(request.user, 'customers.read'),
        'licenses': has_perm(request.user, 'licenses.read'),
        'orders': has_perm(request.user, 'orders.read'),
    }
    if not any(rights.values()):
        raise PermissionDenied

    customer_total = (
        Company.objects.count() + PrivateCustomerProfile.objects.count()
        if rights['customers'] else None
    )
    new_customers_30 = (
        Company.objects.filter(created_at__gte=now - timedelta(days=30)).count()
        + PrivateCustomerProfile.objects.filter(created_at__gte=now - timedelta(days=30)).count()
        if rights['customers'] else None
    )
    term_total = LicenseTerm.objects.count() if rights['licenses'] else 0
    renewal_terms = (
        LicenseTerm.objects.filter(order_item__target_license__isnull=False).count()
        if rights['licenses'] else 0
    )
    refunded_terms = (
        LicenseTerm.objects.filter(status='refunded').count()
        if rights['licenses'] else 0
    )
    company_count = Company.objects.count() if rights['customers'] and rights['licenses'] else 0
    company_license_count = License.objects.filter(company__isnull=False).count() if company_count else 0

    return render(
        request,
        'ns_admin/stats.html',
        {
            'rights': rights,
            'customers': customer_total,
            'new_customers_30': new_customers_30,
            'licenses': License.objects.count() if rights['licenses'] else None,
            'orders': Order.objects.count() if rights['orders'] else None,
            'renewals': renewal_terms if rights['licenses'] else None,
            'renewal_share': round((renewal_terms / term_total) * 100, 1) if term_total else None,
            'refund_rate': round((refunded_terms / term_total) * 100, 1) if term_total else None,
            'avg_licenses_company': round(company_license_count / company_count, 1) if company_count else None,
            'revenue30': (
                Order.objects.filter(
                    status='paid',
                    created_at__gte=now - timedelta(days=30),
                ).aggregate(v=Sum('gross_total'))['v'] or 0
            ) if rights['orders'] else None,
        },
    )


@staff_perm('ops.read')
def ops(request):
    from apps.ops.api import _database_payload, _integration_payload, _service_payload

    domain = settings.CADDY_DOMAIN
    metrics = snapshot()
    backups = BackupRecord.objects.order_by('-finished_at', '-created_at')[:10]
    restores = RestoreTest.objects.order_by('-started_at')[:10]
    return render(
        request,
        'ns_admin/ops.html',
        {
            'ops': metrics,
            'alerts': SystemAlert.objects.filter(active=True).order_by('severity', '-created_at')[:20],
            'backups': backups,
            'restores': restores,
            'latest_backup': backups[0] if backups else None,
            'latest_restore': restores[0] if restores else None,
            'caddy_ok': caddy_health(),
            'certificate': certificate_status(domain.split(':', 1)[0] if domain else ''),
            'database': _database_payload(safe=True),
            'services': _service_payload(),
            'integrations': _integration_payload(),
            'app_version': settings.APP_VERSION,
            'git_sha': settings.GIT_SHA,
            'deployed_at': getattr(settings, 'DEPLOYED_AT', ''),
            'environment': settings.ENVIRONMENT,
        },
    )


@staff_perm('ops.read')
def ops_services(request):
    from apps.ops.api import _database_payload, _service_payload
    return render(request, 'ns_admin/ops_services.html', {'ops': snapshot(), 'database': _database_payload(), 'caddy_ok': caddy_health(), 'services': _service_payload()})


@staff_perm('ops.read')
def ops_database(request):
    from apps.ops.api import _database_payload
    return render(request, 'ns_admin/ops_database.html', {'database': _database_payload()})


@staff_perm('ops.read')
def ops_backups(request):
    grid = DataGrid(request, BackupRecord.objects.all(), search_fields=('status', 'provider_ref'), sort_fields={'date': 'finished_at', 'status': 'status', 'size': 'size_bytes'}, default_sort='-finished_at', filters={'status': 'status'}).build()
    return render(request, 'ns_admin/ops_grid.html', {'title': 'Backups', 'grid': grid, 'kind': 'backups', 'filter_options': []})


@staff_perm('ops.read')
def ops_restore_tests(request):
    grid = DataGrid(request, RestoreTest.objects.all(), search_fields=('status', 'backup_ref'), sort_fields={'date': 'started_at', 'status': 'status'}, default_sort='-started_at', filters={'status': 'status'}).build()
    return render(request, 'ns_admin/ops_grid.html', {'title': 'Restore-Tests', 'grid': grid, 'kind': 'restores', 'filter_options': []})


@staff_perm('ops.read')
def ops_alerts(request):
    grid = DataGrid(request, SystemAlert.objects.all(), search_fields=('code', 'message'), sort_fields={'date': 'created_at', 'severity': 'severity', 'active': 'active'}, default_sort='-created_at', filters={'severity': 'severity', 'active': 'active'}).build()
    return render(request, 'ns_admin/ops_grid.html', {'title': 'Systemwarnungen', 'grid': grid, 'kind': 'alerts', 'filter_options': [('severity', 'Schweregrad', SystemAlert.SEVERITY), ('active', 'Status', [('True', 'Aktiv'), ('False', 'Erledigt')])]})


@staff_perm('api.read')
def api(request):
    return render(
        request,
        'ns_admin/api.html',
        {
            'accounts': ServiceAccount.objects.order_by('name'),
            'can_write': has_perm(request.user, 'api.write'),
        },
    )


@staff_perm('api.write')
def service_account_create(request):
    form = ServiceAccountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        raw, hashed = token_pair()
        account = ServiceAccount.objects.create(
            name=form.cleaned_data['name'],
            token_hash=hashed,
            scopes=form.cleaned_data['scopes'],
            expires_at=form.cleaned_data['expires_at'],
        )
        write_audit(request.user, 'service_account.created', account, {'scopes': account.scopes}, request=request)
        return render(
            request,
            'ns_admin/service_account_token.html',
            {'account': account, 'token': raw, 'token_action': 'erstellt'},
        )
    return render(request, 'ns_admin/form.html', {'title': 'Service Account anlegen', 'form': form, 'cancel_url': reverse('ns_admin:api')})


@staff_perm('api.write')
@transaction.atomic
def service_account_rotate(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    account = get_object_or_404(ServiceAccount.objects.select_for_update(), pk=pk)
    if not account.active:
        messages.error(request, 'Ein gesperrter Service Account kann nicht rotiert werden.')
        return redirect('ns_admin:api')
    raw, hashed = token_pair()
    account.token_hash = hashed
    account.last_used_at = None
    account.save(update_fields=['token_hash', 'last_used_at', 'updated_at'])
    write_audit(request.user, 'service_account.rotated', account, {'scopes': account.scopes}, request=request)
    return render(
        request,
        'ns_admin/service_account_token.html',
        {'account': account, 'token': raw, 'token_action': 'rotiert'},
    )


@staff_perm('api.write')
def service_account_revoke(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    account = get_object_or_404(ServiceAccount, pk=pk)
    account.active = False
    account.save(update_fields=['active', 'updated_at'])
    write_audit(request.user, 'service_account.revoked', account, {}, request=request)
    messages.success(request, 'Service Account gesperrt.')
    return redirect('ns_admin:api')


@staff_perm('legal.read')
def legal(request):
    return render(
        request,
        'ns_admin/legal.html',
        {
            'documents': LegalDocument.objects.order_by('doc_type', '-valid_from')[:20],
            'retention_count': RetentionPolicy.objects.filter(active=True).count(),
            'open_deletion_count': DeletionRequest.objects.filter(status__in=['open', 'processing']).count(),
        },
    )


@staff_perm('legal.read')
def legal_documents(request):
    grid = DataGrid(
        request,
        LegalDocument.objects.all(),
        search_fields=('doc_type', 'version'),
        sort_fields={'type': 'doc_type', 'version': 'version', 'valid_from': 'valid_from', 'active': 'active'},
        default_sort='doc_type',
        filters={'doc_type': 'doc_type', 'active': 'active'},
    ).build()
    return render(request, 'ns_admin/legal_documents.html', {'grid': grid, 'filter_options': [('doc_type', 'Typ', LegalDocument.DOC_TYPES), ('active', 'Status', [('True', 'Aktiv'), ('False', 'Inaktiv')])]})


@staff_perm('legal.write')
def legal_document_edit(request, pk=None):
    document = get_object_or_404(LegalDocument, pk=pk) if pk else None
    form = LegalDocumentForm(request.POST or None, instance=document)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if form.cleaned_data['active']:
                LegalDocument.objects.select_for_update().filter(doc_type=form.cleaned_data['doc_type'], active=True).exclude(pk=document.pk if document else None).update(active=False)
            saved = form.save()
        write_audit(request.user, 'legal_document.saved', saved, {'version': saved.version, 'active': saved.active}, request=request)
        messages.success(request, 'Rechtsdokument gespeichert.')
        return redirect('ns_admin:legal_documents')
    return render(request, 'ns_admin/form.html', {'title': 'Rechtsdokument bearbeiten' if document else 'Rechtsdokument anlegen', 'form': form, 'cancel_url': reverse('ns_admin:legal_documents')})


@staff_perm('legal.read')
def retention_policies(request):
    grid = DataGrid(
        request,
        RetentionPolicy.objects.all(),
        search_fields=('data_class',),
        sort_fields={'data_class': 'data_class', 'days': 'retain_days', 'active': 'active'},
        default_sort='data_class',
        filters={'active': 'active'},
    ).build()
    return render(request, 'ns_admin/legal_retention.html', {'grid': grid, 'filter_options': [('active', 'Status', [('True', 'Aktiv'), ('False', 'Inaktiv')])]})


@staff_perm('legal.write')
def retention_policy_edit(request, pk=None):
    policy = get_object_or_404(RetentionPolicy, pk=pk) if pk else None
    form = RetentionPolicyForm(request.POST or None, instance=policy)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        write_audit(request.user, 'retention_policy.saved', saved, {'data_class': saved.data_class, 'retain_days': saved.retain_days, 'active': saved.active}, request=request)
        messages.success(request, 'Retention-Policy gespeichert.')
        return redirect('ns_admin:retention_policies')
    return render(request, 'ns_admin/form.html', {'title': 'Retention-Policy bearbeiten' if policy else 'Retention-Policy anlegen', 'form': form, 'cancel_url': reverse('ns_admin:retention_policies')})


@staff_perm('legal.read')
def deletion_requests(request):
    grid = DataGrid(
        request,
        DeletionRequest.objects.select_related('user'),
        search_fields=('user__email', 'user__first_name', 'user__last_name', 'notes'),
        sort_fields={'date': 'requested_at', 'status': 'status', 'email': 'user__email'},
        default_sort='-requested_at',
        filters={'status': 'status'},
    ).build()
    return render(request, 'ns_admin/legal_deletions.html', {'grid': grid, 'filter_options': [('status', 'Status', DeletionRequest.STATUS)]})


@staff_perm('legal.write')
def deletion_request_process(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    deletion = get_object_or_404(DeletionRequest, pk=pk)
    from apps.legal.services import process_deletion_request
    try:
        process_deletion_request(deletion, actor=request.user, request=request)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, 'Löschanfrage verarbeitet und Konto anonymisiert.')
    return redirect('ns_admin:deletion_requests')


@staff_perm('legal.write')
def deletion_request_reject(request, pk):
    deletion = get_object_or_404(DeletionRequest, pk=pk)
    form = DeletionRejectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        from apps.legal.services import reject_deletion_request
        try:
            reject_deletion_request(deletion, actor=request.user, notes=form.cleaned_data['notes'], request=request)
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            messages.success(request, 'Löschanfrage abgelehnt.')
            return redirect('ns_admin:deletion_requests')
    return render(request, 'ns_admin/form.html', {'title': 'Löschanfrage ablehnen', 'form': form, 'cancel_url': reverse('ns_admin:deletion_requests')})


@staff_perm('support.read')
def support_requests(request):
    grid = DataGrid(
        request,
        SupportRequest.objects.select_related('user', 'company', 'license', 'license__product'),
        search_fields=('subject', 'message', 'user__email', 'company__name'),
        sort_fields={'date':'created_at','status':'status','category':'category','subject':'subject'},
        default_sort='-created_at',
        filters={'status':'status','category':'category'},
    ).build()
    return render(request, 'ns_admin/support.html', {
        'grid': grid,
        'filter_options': [('status','Status',SupportRequest.STATUS),('category','Kategorie',SupportRequest.CATEGORY)],
    })


@staff_perm('support.read')
def support_request_detail(request, pk):
    support_request = get_object_or_404(SupportRequest.objects.select_related('user','company','license','license__product'), pk=pk)
    return render(request, 'ns_admin/support_detail.html', {'support_request': support_request, 'can_write': has_perm(request.user, 'support.write')})


@staff_perm('support.write')
def support_request_status(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    support_request = get_object_or_404(SupportRequest, pk=pk)
    status = (request.POST.get('status') or '').strip()
    allowed = {value for value, _label in SupportRequest.STATUS}
    if status not in allowed:
        messages.error(request, 'Ungültiger Supportstatus.')
        return redirect('ns_admin:support_request_detail', pk=pk)
    previous = support_request.status
    support_request.status = status
    support_request.save(update_fields=['status','updated_at'])
    write_audit(request.user, 'support.status_changed', support_request, {'before':previous,'after':status}, request=request)
    messages.success(request, 'Status aktualisiert.')
    return redirect('ns_admin:support_request_detail', pk=pk)


@staff_perm('audit.read')
def audit(request):
    grid = DataGrid(request, AuditEvent.objects.select_related('actor'), search_fields=('action', 'object_type', 'object_id', 'actor__email'), sort_fields={'time': 'created_at', 'action': 'action'}, default_sort='-created_at', filters={'action': 'action'}).build()
    export = _grid_export(request, grid, [('created_at', 'Zeit'), ('actor.email', 'Benutzer'), ('actor_role', 'Rolle'), ('action', 'Aktion'), ('object_type', 'Objekttyp'), ('object_id', 'Objekt-ID')], 'promptmaster-audit.csv')
    if export:
        return export
    return render(request, 'ns_admin/audit.html', {'grid': grid, 'filter_options': [], 'export_enabled': True})


@staff_perm('roles.read')
def roles(request):
    descriptions = {
        'superadmin': 'Uneingeschränkte Rechte auf alle PromptMaster-Verwaltungsbereiche.',
        'support': 'Kunden, Lizenzen, Geräte, Bestellungen, Zahlungen, E-Mail und Support.',
        'ops': 'Monitoring, Backups, Operations API, Logs und Systemstatus.',
        'prompt_manager': 'Prompt Studio, Prompt-Lifecycle, Qualität und zentrale Inhalte.',
    }
    role_rows = list(Role.objects.prefetch_related('permissions').order_by('name'))
    for role in role_rows:
        role.display_description = descriptions.get(
            role.code,
            'Berechtigungen werden über die zugewiesenen Capabilities gesteuert.',
        )
    return render(request, 'ns_admin/roles.html', {
        'roles': role_rows,
        'users': User.objects.filter(is_staff=True).prefetch_related('role_links__role').order_by('email'),
    })


@staff_perm('roles.write')
def staff_user_create(request):
    form = StaffUserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                email=form.cleaned_data['email'],
                password=None,
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                is_staff=True,
                is_active=True,
                two_factor_required=True,
            )
            link = UserRole.objects.create(user=user, role=form.cleaned_data['role'])
            write_audit(request.user, 'staff_user.created', user, {'role': link.role.code}, request=request)
            transaction.on_commit(lambda: _send_staff_setup_email(request, user), robust=True)
        messages.success(request, 'netstyle Benutzer angelegt; Einrichtungslink wurde per E-Mail versendet.')
        return redirect('ns_admin:roles')
    return render(request, 'ns_admin/form.html', {'title': 'netstyle Benutzer anlegen', 'form': form, 'cancel_url': reverse('ns_admin:roles')})


@staff_perm('roles.write')
def staff_user_toggle(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    target = get_object_or_404(User, pk=pk, is_staff=True)
    if target.pk == request.user.pk:
        messages.error(request, 'Das eigene netstyle Konto kann hier nicht deaktiviert werden.')
        return redirect('ns_admin:roles')
    if target.is_active and (target.is_superuser or target.role_links.filter(role__code='superadmin', role__active=True).exists()) and _active_superadmin_count() <= 1:
        messages.error(request, 'Der letzte aktive Superadmin kann nicht deaktiviert werden.')
        return redirect('ns_admin:roles')
    target.is_active = not target.is_active
    if target.is_active:
        target.two_factor_required = True
    target.save(update_fields=['is_active', 'two_factor_required', 'updated_at'])
    bump_security_version(target)
    write_audit(request.user, 'staff_user.activated' if target.is_active else 'staff_user.deactivated', target, {}, request=request)
    messages.success(request, 'Benutzerstatus aktualisiert.')
    return redirect('ns_admin:roles')


@staff_perm('roles.write')
def staff_user_reset_2fa(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    target = get_object_or_404(User, pk=pk, is_staff=True)
    if target.pk == request.user.pk:
        messages.error(request, 'Die eigene 2FA wird nicht über die Admin-Fremdverwaltung zurückgesetzt.')
        return redirect('ns_admin:roles')
    target.totp_secret_enc = ''
    target.two_factor_required = True
    target.save(update_fields=['totp_secret_enc', 'two_factor_required', 'updated_at'])
    target.recovery_codes.all().delete()
    bump_security_version(target)
    write_audit(request.user, 'staff_user.2fa_reset', target, {}, request=request)
    messages.success(request, '2FA zurückgesetzt. Der Benutzer muss sie beim nächsten Login neu einrichten.')
    return redirect('ns_admin:roles')


@staff_perm('roles.write')
def role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == 'POST' and form.is_valid():
        if role.code == 'superadmin' and not form.cleaned_data.get('active') and _active_superadmin_count() <= 1:
            form.add_error('active', 'Der letzte aktive Superadmin darf nicht deaktiviert werden.')
            return render(request, 'ns_admin/form.html', {'title': f'Rolle · {role.name}', 'form': form, 'cancel_url': reverse('ns_admin:roles')})
        saved = form.save()
        write_audit(request.user, 'role.updated', saved, {'fields': list(form.changed_data)}, request=request)
        messages.success(request, 'Rolle gespeichert.')
        return redirect('ns_admin:roles')
    return render(request, 'ns_admin/form.html', {'title': f'Rolle · {role.name}', 'form': form, 'cancel_url': reverse('ns_admin:roles')})


@staff_perm('roles.write')
def user_role_assign(request):
    form = StaffUserRoleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        target_user = form.cleaned_data['user']
        link, created = UserRole.objects.get_or_create(user=target_user, role=form.cleaned_data['role'])
        if created:
            if not target_user.two_factor_required:
                target_user.two_factor_required = True
                target_user.save(update_fields=['two_factor_required', 'updated_at'])
            bump_security_version(target_user)
        write_audit(request.user, 'user_role.assigned', link, {'user': str(link.user_id), 'role': link.role.code}, request=request)
        messages.success(request, 'Rolle zugewiesen.')
        return redirect('ns_admin:roles')
    return render(request, 'ns_admin/form.html', {'title': 'netstyle Rolle zuweisen', 'form': form, 'cancel_url': reverse('ns_admin:roles')})


@staff_perm('roles.write')
def user_role_remove(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    link = get_object_or_404(UserRole.objects.select_related('user', 'role'), pk=pk)
    if link.user_id == request.user.id and link.role.code == 'superadmin':
        messages.error(request, 'Die eigene Superadmin-Rolle kann nicht hier entfernt werden.')
        return redirect('ns_admin:roles')
    if link.role.code == 'superadmin' and link.user.is_active and _active_superadmin_count() <= 1:
        messages.error(request, 'Die letzte aktive Superadmin-Berechtigung kann nicht entfernt werden.')
        return redirect('ns_admin:roles')
    target_user = link.user
    write_audit(request.user, 'user_role.removed', link, {'user': str(link.user_id), 'role': link.role.code}, request=request)
    link.delete()
    bump_security_version(target_user)
    messages.success(request, 'Rolle entfernt.')
    return redirect('ns_admin:roles')


@staff_perm('settings.read')
def settings_view(request):
    values = get_setting('ops_thresholds', {}) or {}
    initial = {
        'support_email': get_setting('support_email', 'promptmaster@netstyle.de'),
        'disk_warning': values.get('disk_warning', 80),
        'disk_critical': values.get('disk_critical', 90),
        'ram_warning': values.get('ram_warning', 80),
        'ram_critical': values.get('ram_critical', 90),
        'cpu_warning': values.get('cpu_warning', 80),
        'backup_warning_hours': values.get('backup_warning_hours', 8),
        'backup_critical_hours': values.get('backup_critical_hours', 24),
        'restore_warning_days': values.get('restore_warning_days', 35),
    }
    form = GeneralSettingsForm(request.POST or None, initial=initial)
    if request.method == 'POST':
        if not has_perm(request.user, 'settings.write'):
            raise PermissionDenied
        if form.is_valid():
            data = form.cleaned_data.copy()
            support_email = data.pop('support_email')
            set_setting('support_email', support_email, 'Empfänger des PromptMaster-Kontaktformulars')
            set_setting('ops_thresholds', data, 'Warnschwellen für System & Betrieb')
            write_audit(request.user, 'settings.updated', request.user, {'support_email': support_email, 'ops_thresholds': data}, request=request)
            messages.success(request, 'Einstellungen gespeichert.')
            return redirect('ns_admin:settings')
    return render(
        request,
        'ns_admin/settings.html',
        {
            'form': form,
            'can_write': has_perm(request.user, 'settings.write'),
            'pro_product': Product.objects.filter(code='PRO').first(),
            'invitation_ttl_hours': INVITATION_TTL_HOURS,
        },
    )


@staff_perm()
def global_search(request):
    query = request.GET.get('q', '').strip()[:200]
    results = {'customers': [], 'private_customers': [], 'users': [], 'licenses': [], 'orders': [], 'payments': []}
    if len(query) >= 2:
        if has_perm(request.user, 'customers.read'):
            results['customers'] = Company.objects.filter(Q(name__icontains=query) | Q(customer_number__icontains=query) | Q(email__icontains=query))[:10]
            results['private_customers'] = PrivateCustomerProfile.objects.filter(Q(customer_number__icontains=query) | Q(user__email__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)).select_related('user')[:10]
            results['users'] = User.objects.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))[:10]
        if has_perm(request.user, 'licenses.read'):
            results['licenses'] = License.objects.filter(license_number__icontains=query).select_related('company', 'owner_user')[:10]
        if has_perm(request.user, 'orders.read'):
            results['orders'] = Order.objects.filter(order_number__icontains=query)[:10]
        if has_perm(request.user, 'payments.read'):
            results['payments'] = Payment.objects.filter(provider_payment_id__icontains=query)[:10]
    return render(request, 'ns_admin/search.html', {'q': query, 'results': results})
