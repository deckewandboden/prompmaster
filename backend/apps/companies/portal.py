import logging
import secrets
from datetime import timedelta
from apps.core.security import check_rate, client_ip

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
import json
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms import TransferAdminForm
from apps.accounts.models import User
from apps.accounts.security import bump_security_version
from apps.audit.services import audit
from apps.core.datagrid import DataGrid
from apps.devices.models import DeviceRegistration
from apps.devices.services import revoke_device
from apps.legal.models import DeletionRequest, LegalAcceptance, LegalDocument
from apps.legal.services import process_deletion_request
from apps.licenses.models import License, LicenseAssignment, LicenseReminder, LicenseUpgradeRequest
from apps.licenses.services import assign_license, release_license, request_product_upgrade, resolve_product_upgrade, create_assignment_link, consume_assignment_link
from apps.notifications.services import queue_email
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.proaccess.services import active_product_assignment, assignment_expiry_context
from apps.payments.mollie import MollieClient, MollieError
from apps.support.models import SupportRequest
from .forms import CompanyForm, InviteForm, PrivateCustomerForm, SupportForm, UserProfileForm
from .models import Invitation, Membership
from .services import create_invitation, transfer_admin

logger = logging.getLogger(__name__)


def _ctx(request):
    membership = (
        Membership.objects.filter(user=request.user, active=True)
        .select_related('company')
        .first()
    )
    if membership and membership.company.status != 'active':
        raise PermissionDenied('Das Unternehmen ist deaktiviert.')
    return (membership.company if membership else None, membership)


def _admin(request):
    company, membership = _ctx(request)
    if not company or not membership or membership.role != 'admin':
        raise PermissionDenied
    return company, membership


def _is_private_customer(user):
    return hasattr(user, 'private_customer') and not user.company_memberships.filter(active=True).exists()


def _active_legal_documents(private_customer=False):
    now = timezone.now()
    required = ['terms', 'privacy'] + (['withdrawal'] if private_customer else [])
    documents = {}
    for doc_type in required:
        document = (
            LegalDocument.objects.filter(doc_type=doc_type, active=True, valid_from__lte=now)
            .order_by('-valid_from')
            .first()
        )
        if not document:
            raise ValidationError(f'Aktives Rechtsdokument fehlt: {doc_type}.')
        documents[doc_type] = document
    return documents


def _record_legal_acceptances(request, order, documents):
    evidence = {
        'ip': client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
    }
    for document in documents.values():
        LegalAcceptance.objects.get_or_create(
            user=request.user,
            document=document,
            order=order,
            defaults={'evidence': evidence},
        )


def _checkout_key(request, scope):
    session_key = f'checkout_key:{scope}'
    value = request.session.get(session_key)
    if not value:
        value = secrets.token_urlsafe(24)
        request.session[session_key] = value
    return session_key, value


def _rotate_checkout_key(request, session_key):
    request.session[session_key] = secrets.token_urlsafe(24)


def _start_mollie_checkout(request, order, description, metadata):
    try:
        existing_payment = order.payments.order_by('-created_at').first()
        if existing_payment and existing_payment.status in {'created', 'open', 'pending'}:
            checkout_url = ((((existing_payment.last_provider_payload or {}).get('_links') or {}).get('checkout') or {}).get('href') or '').strip()
            if checkout_url.startswith('https://'):
                return redirect(checkout_url)
        payload = MollieClient().create_payment(
            amount=order.gross_total,
            currency=order.currency,
            description=description,
            redirect_url=request.build_absolute_uri(reverse('portal:orders')),
            webhook_url=request.build_absolute_uri(reverse('payments:mollie_webhook')),
            metadata=metadata,
            idempotency_key=order.idempotency_key,
        )
        payment_id = str(payload.get('id') or '')[:100]
        checkout_url = (((payload.get('_links') or {}).get('checkout') or {}).get('href') or '').strip()
        if not payment_id or not checkout_url.startswith('https://'):
            raise MollieError('Mollie response is missing payment ID or secure checkout URL')
        payment, created = Payment.objects.get_or_create(
            provider_payment_id=payment_id,
            defaults={
                'order': order,
                'status': str(payload.get('status') or 'open')[:40],
                'amount': order.gross_total,
                'currency': order.currency,
                'last_provider_payload': payload,
            },
        )
        if payment.order_id != order.id:
            raise MollieError('Mollie payment ID is already linked to another order')
        if not created:
            payment.last_provider_payload = payload
            payment.save(update_fields=['last_provider_payload', 'updated_at'])
        order.status = 'payment_open'
        order.save(update_fields=['status', 'updated_at'])
        return redirect(checkout_url)
    except Exception as exc:
        logger.exception('Could not create Mollie checkout for order %s', order.order_number)
        order.status = 'failed'
        order.save(update_fields=['status', 'updated_at'])
        messages.error(request, 'Die Zahlung konnte nicht gestartet werden. Es wurde nichts freigeschaltet.')
        return None


@login_required
def dashboard(request):
    company, membership = _ctx(request)
    is_company_admin = bool(company and membership and membership.role == 'admin')
    if is_company_admin:
        licenses = License.objects.filter(company=company)
        device_queryset = DeviceRegistration.objects.filter(
            user__company_memberships__company=company,
            user__company_memberships__active=True,
            revoked_at__isnull=True,
        ).distinct()
        team_shortlist = (
            Membership.objects.filter(company=company, active=True)
            .select_related('user')
            .order_by('user__last_name', 'user__first_name')[:5]
        )
        payment_issues = (
            Payment.objects.filter(order__company=company, status__in=['failed', 'chargeback'])
            .select_related('order')
            .order_by('-updated_at')[:5]
        )
        required_company_fields = {
            'name': 'Firmenname',
            'email': 'E-Mail',
            'street': 'Straße',
            'postal_code': 'PLZ',
            'city': 'Ort',
            'country': 'Land',
        }
        company_missing_fields = [
            label for field, label in required_company_fields.items()
            if not str(getattr(company, field, '') or '').strip()
        ]
    elif company:
        licenses = License.objects.filter(
            company=company,
            assignments__user=request.user,
            assignments__ended_at__isnull=True,
        ).distinct()
        device_queryset = DeviceRegistration.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
        )
        team_shortlist = []
        payment_issues = []
        company_missing_fields = []
    else:
        licenses = License.objects.filter(owner_user=request.user)
        device_queryset = DeviceRegistration.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
        )
        team_shortlist = []
        payment_issues = (
            Payment.objects.filter(
                order__private_user=request.user,
                status__in=['failed', 'chargeback'],
            )
            .select_related('order')
            .order_by('-updated_at')[:5]
        )
        company_missing_fields = []

    now = timezone.now()
    active_licenses = list(
        licenses.filter(status='active', valid_until__gt=now).select_related('product')
    )
    pro_assignment = active_product_assignment(request.user, 'PRO')
    pro_expiry = assignment_expiry_context(pro_assignment, now) if pro_assignment else None
    return render(
        request,
        'portal/dashboard.html',
        {
            'company': company,
            'membership': membership,
            'licenses': licenses.select_related('product'),
            'license_total': licenses.count(),
            'license_free': licenses.filter(status='free', valid_until__gt=now).count(),
            'license_active': len(active_licenses),
            'license_assigned': licenses.filter(
                assignments__ended_at__isnull=True,
            ).distinct().count(),
            'expiring_30': licenses.filter(
                valid_until__gt=now,
                valid_until__lte=now + timedelta(days=30),
            ).count(),
            'device_count': device_queryset.count(),
            'device_capacity': sum(
                license_obj.product.default_device_limit
                for license_obj in active_licenses
            ),
            'team_shortlist': team_shortlist,
            'payment_issues': payment_issues,
            'company_missing_fields': company_missing_fields,
            'can_start_pro': bool(pro_assignment),
            'pro_expiry': pro_expiry,
            'pending_upgrade': LicenseUpgradeRequest.objects.filter(
                user=request.user,
                status='pending',
                product__code='PRO',
            ).exists(),
            'now': now,
        },
    )


@login_required
def team(request):
    company, _ = _admin(request)
    grid = DataGrid(
        request,
        Membership.objects.filter(company=company).select_related('user'),
        search_fields=('user__email', 'user__first_name', 'user__last_name'),
        sort_fields={'name': 'user__last_name', 'email': 'user__email', 'created': 'created_at'},
        default_sort='user__last_name',
        filters={'role': 'role', 'active': 'active'},
    ).build()
    return render(
        request,
        'portal/team.html',
        {
            'company': company,
            'grid': grid,
            'upgrade_requests': LicenseUpgradeRequest.objects.filter(company=company, status='pending').select_related('user', 'product').order_by('created_at'),
            'filter_options': [
                ('role', 'Rolle', Membership.ROLE),
                ('active', 'Status', [('True', 'Aktiv'), ('False', 'Inaktiv')]),
            ],
        },
    )


@login_required
def invitations(request):
    company, _ = _admin(request)
    grid = DataGrid(
        request,
        Invitation.objects.filter(company=company),
        search_fields=('email', 'first_name', 'last_name'),
        sort_fields={'email': 'email', 'expires': 'expires_at', 'created': 'created_at'},
        default_sort='-created_at',
    ).build()
    return render(request, 'portal/invitations.html', {'grid': grid, 'filter_options': []})


@login_required
def invite(request):
    company, _ = _admin(request)
    if request.method == 'POST':
        limited = check_rate(request, f'invite-send:{company.pk}:{request.user.pk}', 30, 3600)
        if limited:
            return limited
    form = InviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            invitation, raw = create_invitation(company=company, actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error('email', exc.messages[0])
        else:
            url = request.build_absolute_uri(reverse('accounts:accept_invitation', args=[raw]))
            queue_email('invite', invitation.email, {'url': url})
            messages.success(request, 'Einladung wurde versendet.')
            return redirect('portal:invitations')
    return render(request, 'portal/form.html', {'title': 'Benutzer einladen', 'form': form})


@login_required
def request_pro_upgrade(request):
    if request.method != 'POST':
        raise PermissionDenied
    company_obj, membership = _ctx(request)
    if not company_obj or not membership or membership.role != 'member':
        raise PermissionDenied
    from apps.catalog.models import Product
    product = get_object_or_404(Product, code='PRO', active=True)
    try:
        upgrade, created = request_product_upgrade(
            user=request.user,
            company=company_obj,
            product=product,
            note=(request.POST.get('note') or '').strip(),
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        if created:
            admin = company_obj.memberships.filter(active=True, role='admin').select_related('user').first()
            if admin:
                queue_email(
                    'upgrade_request',
                    admin.user.email,
                    {'user': request.user.full_name, 'email': request.user.email, 'product': product.name},
                )
            messages.success(request, 'Ihre Pro-Anfrage wurde an den Firmenadministrator gesendet.')
        else:
            messages.info(request, 'Für PromptMaster Pro besteht bereits eine offene Anfrage.')
    return redirect('portal:dashboard')


@login_required
def resolve_upgrade(request, pk, decision):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    if decision not in {'approve', 'reject'}:
        raise PermissionDenied
    upgrade = get_object_or_404(LicenseUpgradeRequest, pk=pk, company=company_obj, status='pending')
    try:
        row = resolve_product_upgrade(
            upgrade_request=upgrade,
            actor=request.user,
            approve=(decision == 'approve'),
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        queue_email(
            'upgrade_request_resolved',
            row.user.email,
            {'product': row.product.name, 'status': row.get_status_display()},
        )
        messages.success(request, f'Pro-Anfrage: {row.get_status_display()}.')
    return redirect('portal:team')


@login_required
def licenses(request):
    company, membership = _ctx(request)
    if company and membership and membership.role == 'admin':
        queryset = License.objects.filter(company=company)
    elif company:
        queryset = License.objects.filter(
            company=company,
            assignments__user=request.user,
            assignments__ended_at__isnull=True,
        ).distinct()
    else:
        queryset = License.objects.filter(owner_user=request.user)
    grid = DataGrid(
        request,
        queryset.select_related('product'),
        search_fields=('license_number', 'product__name'),
        sort_fields={'id': 'license_number', 'expiry': 'valid_until', 'status': 'status', 'product': 'product__name'},
        default_sort='valid_until',
        filters={'status': 'status', 'product': 'product__code'},
    ).build()
    products = sorted({(row.product.code, row.product.name) for row in queryset.select_related('product')})
    return render(
        request,
        'portal/licenses.html',
        {
            'grid': grid,
            'is_admin': bool(membership and membership.role == 'admin'),
            'can_manage': bool(not company or (membership and membership.role == 'admin')),
            'filter_options': [('status', 'Status', License.STATUS), ('product', 'Produkt', products)],
        },
    )


@login_required
def license_detail(request, pk):
    company_obj, membership = _ctx(request)
    if company_obj and membership and membership.role == 'admin':
        queryset = License.objects.filter(company=company_obj)
    elif company_obj:
        queryset = License.objects.filter(
            company=company_obj,
            assignments__user=request.user,
            assignments__ended_at__isnull=True,
        ).distinct()
    else:
        queryset = License.objects.filter(owner_user=request.user)

    license_obj = get_object_or_404(
        queryset.select_related('product'),
        pk=pk,
    )
    assignment = (
        LicenseAssignment.objects.filter(
            license=license_obj,
            ended_at__isnull=True,
        )
        .select_related('user')
        .first()
    )
    reminders = LicenseReminder.objects.filter(
        license=license_obj,
        target_valid_until=license_obj.valid_until,
    ).order_by('kind')
    now = timezone.now()
    remaining_days = max(
        (timezone.localtime(license_obj.valid_until).date() - timezone.localdate(now)).days,
        0,
    ) if license_obj.valid_until else 0
    can_manage = bool(
        license_obj.owner_user_id == request.user.id
        or (company_obj and membership and membership.role == 'admin')
    )
    return render(
        request,
        'portal/license_detail.html',
        {
            'license': license_obj,
            'assignment': assignment,
            'reminders': reminders,
            'devices': DeviceRegistration.objects.filter(
                license=license_obj,
                revoked_at__isnull=True,
            ).select_related('user').order_by('-last_seen_at'),
            'remaining_days': remaining_days,
            'can_manage': can_manage,
        },
    )


@login_required
def devices(request):
    company, membership = _ctx(request)
    if company and membership and membership.role == 'admin':
        queryset = DeviceRegistration.objects.filter(
            user__company_memberships__company=company,
            user__company_memberships__active=True,
        )
    else:
        queryset = DeviceRegistration.objects.filter(user=request.user)
    grid = DataGrid(
        request,
        queryset.select_related('user', 'license'),
        search_fields=('display_name', 'user__email'),
        sort_fields={'device': 'display_name', 'last': 'last_seen_at', 'user': 'user__email'},
        default_sort='-last_seen_at',
    ).build()
    return render(
        request,
        'portal/devices.html',
        {'grid': grid, 'is_admin': bool(membership and membership.role == 'admin'), 'filter_options': []},
    )


@login_required
def revoke_device_view(request, pk):
    company, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    device = get_object_or_404(
        DeviceRegistration,
        pk=pk,
        user__company_memberships__company=company,
        user__company_memberships__active=True,
    )
    revoke_device(device, request.user, request=request)
    messages.success(request, 'Gerät entfernt.')
    return redirect('portal:devices')


@login_required
def orders(request):
    company, membership = _ctx(request)
    if company and (not membership or membership.role != 'admin'):
        raise PermissionDenied
    queryset = (
        Order.objects.filter(company=company)
        if company
        else Order.objects.filter(private_user=request.user)
    )
    queryset = queryset.prefetch_related(
        'items__license_terms__license',
        'payments',
    )
    grid = DataGrid(
        request,
        queryset,
        search_fields=('order_number', 'payments__provider_payment_id'),
        sort_fields={'number': 'order_number', 'date': 'created_at', 'amount': 'gross_total', 'status': 'status'},
        default_sort='-created_at',
        filters={'status': 'status'},
    ).build()
    return render(
        request,
        'portal/orders.html',
        {'grid': grid, 'filter_options': [('status', 'Status', Order.STATUS)]},
    )


@login_required
def company(request):
    company_obj, _ = _admin(request)
    form = CompanyForm(request.POST or None, instance=company_obj)
    if request.method == 'POST' and form.is_valid():
        before = {field: getattr(company_obj, field) for field in form.fields}
        saved = form.save()
        audit(request.user, 'company.updated', saved, {'before': before}, request=request)
        messages.success(request, 'Unternehmensdaten gespeichert.')
        return redirect('portal:company')
    return render(request, 'portal/company.html', {'form': form, 'company': company_obj})


@login_required
def profile(request):
    form = UserProfileForm(
        request.POST or None,
        initial={'first_name': request.user.first_name, 'last_name': request.user.last_name},
    )
    private_form = None
    if _is_private_customer(request.user):
        private_form = PrivateCustomerForm(request.POST or None, instance=request.user.private_customer, prefix='address')
    if request.method == 'POST' and form.is_valid() and (private_form is None or private_form.is_valid()):
        request.user.first_name = form.cleaned_data['first_name'].strip()
        request.user.last_name = form.cleaned_data['last_name'].strip()
        request.user.save(update_fields=['first_name', 'last_name', 'updated_at'])
        if private_form:
            private_form.save()
        messages.success(request, 'Profil gespeichert.')
        return redirect('portal:profile')
    pending_deletion = (
        DeletionRequest.objects.filter(
            user=request.user,
            status__in=['open', 'processing'],
        )
        .order_by('-created_at')
        .first()
    )
    return render(
        request,
        'portal/profile.html',
        {
            'form': form,
            'private_form': private_form,
            'pending_deletion': pending_deletion,
        },
    )


@login_required
def security(request):
    return render(request, 'portal/security.html')


@login_required
def help_view(request):
    company_obj, membership = _ctx(request)
    if company_obj and membership and membership.role == 'admin':
        visible_licenses = License.objects.filter(company=company_obj).select_related('product')
    elif company_obj:
        visible_licenses = License.objects.filter(
            company=company_obj,
            assignments__user=request.user,
            assignments__ended_at__isnull=True,
        ).select_related('product').distinct()
    else:
        visible_licenses = License.objects.filter(owner_user=request.user).select_related('product')

    form = SupportForm(
        request.POST or None,
        license_queryset=visible_licenses.order_by('license_number'),
    )
    if request.method == 'POST' and form.is_valid():
        support_request = SupportRequest.objects.create(
            user=request.user,
            company=company_obj,
            **form.cleaned_data,
        )
        queue_email(
            'support_confirmation',
            request.user.email,
            {'subject': form.cleaned_data['subject']},
        )
        from apps.core.settings_store import get_setting
        support_email = get_setting('support_email', 'promptmaster@netstyle.de')
        queue_email('support_notification', support_email, {
            'subject': form.cleaned_data['subject'],
            'category': support_request.get_category_display(),
            'customer': company_obj.name if company_obj else request.user.full_name,
            'email': request.user.email,
            'message': form.cleaned_data['message'],
            'license': support_request.license.license_number if support_request.license else '–',
        })
        audit(
            request.user,
            'support.created',
            support_request,
            {
                'category': support_request.category,
                'license': str(support_request.license_id or ''),
            },
            request=request,
        )
        messages.success(request, 'Nachricht wurde übermittelt.')
        return redirect('portal:help')

    if company_obj and membership and membership.role == 'admin':
        history = SupportRequest.objects.filter(company=company_obj)
    else:
        history = SupportRequest.objects.filter(user=request.user)
    history = history.select_related('license', 'license__product')
    return render(
        request,
        'portal/help.html',
        {
            'form': form,
            'support_history': history.order_by('-created_at')[:100],
        },
    )


@login_required
@transaction.atomic
def privacy_delete_request(request):
    if request.method != 'POST':
        raise PermissionDenied
    if request.POST.get('confirm') != '1':
        messages.error(request, 'Bitte bestätigen Sie die Löschanfrage ausdrücklich.')
        return redirect('portal:profile')

    # Serialize requests per identity so double-clicks/concurrent POSTs cannot
    # create duplicate open deletion workflows.
    User.objects.select_for_update().get(pk=request.user.pk)
    pending = (
        DeletionRequest.objects.select_for_update()
        .filter(user=request.user, status__in=['open', 'processing'])
        .order_by('-created_at')
        .first()
    )
    if pending:
        messages.info(request, 'Für Ihr Konto besteht bereits eine offene Löschanfrage.')
        return redirect('portal:profile')

    deletion = DeletionRequest.objects.create(user=request.user, status='open')
    audit(request.user, 'privacy.deletion_requested', deletion, {}, request=request)
    if request.user.company_memberships.filter(active=True, role='admin').exists():
        messages.warning(
            request,
            'Löschanfrage erfasst. Vor der Verarbeitung muss die Firmenadministration '
            'an ein anderes aktives Mitglied übertragen werden.',
        )
    else:
        messages.success(request, 'Löschanfrage wurde erfasst und wird geprüft.')
    return redirect('portal:profile')


@login_required
def privacy_export(request):
    """Export the authenticated user's PromptMaster personal data as JSON.

    The export deliberately excludes secrets, device tokens, provider payloads
    and unrelated tenant/member data. Company metadata is included only as the
    context of the user's own membership.
    """
    user = request.user
    memberships = list(
        Membership.objects.filter(user=user)
        .select_related('company')
        .values(
            'id', 'role', 'active', 'created_at', 'updated_at',
            'company_id', 'company__customer_number', 'company__name',
        )
    )
    assigned_licenses = list(
        LicenseAssignment.objects.filter(user=user)
        .select_related('license__product')
        .values(
            'id', 'license_id', 'license__license_number', 'license__product__code',
            'license__status', 'license__valid_from', 'license__valid_until',
            'assigned_at', 'ended_at',
        )
    )
    owned_licenses = list(
        License.objects.filter(owner_user=user)
        .select_related('product')
        .values('id', 'license_number', 'product__code', 'status', 'valid_from', 'valid_until')
    )
    devices = list(
        DeviceRegistration.objects.filter(user=user).values(
            'id', 'license_id', 'display_name', 'os_family', 'browser_family',
            'created_at', 'last_seen_at', 'revoked_at',
        )
    )
    support = list(
        SupportRequest.objects.filter(user=user).values(
            'id', 'category', 'subject', 'message', 'status', 'created_at', 'updated_at'
        )
    )
    legal = list(
        LegalAcceptance.objects.filter(user=user)
        .select_related('document')
        .values(
            'id', 'document__doc_type', 'document__version', 'accepted_at',
            'order_id', 'evidence',
        )
    )
    from apps.audit.models import AuditEvent
    from apps.prompts.models import PromptRating
    ratings = list(
        PromptRating.objects.filter(user=user)
        .select_related('definition', 'version')
        .values(
            'id', 'definition__task_id', 'version__version', 'stars', 'feedback',
            'created_at', 'updated_at',
        )
    )
    events = list(
        AuditEvent.objects.filter(actor=user).values(
            'id', 'created_at', 'action', 'object_type', 'object_id',
            'ip', 'user_agent', 'correlation_id',
        )[:5000]
    )
    private = None
    if hasattr(user, 'private_customer'):
        pc = user.private_customer
        private = {
            'customer_number': pc.customer_number,
            'street': pc.street,
            'house_number': pc.house_number,
            'postal_code': pc.postal_code,
            'city': pc.city,
            'country': pc.country,
        }
    payload = {
        'schema_version': 1,
        'exported_at': timezone.now(),
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'email_verified_at': user.email_verified_at,
            'last_login': user.last_login,
            'created_at': user.created_at,
            'updated_at': user.updated_at,
        },
        'private_customer': private,
        'memberships': memberships,
        'license_assignments': assigned_licenses,
        'owned_licenses': owned_licenses,
        'devices': devices,
        'support_requests': support,
        'legal_acceptances': legal,
        'prompt_ratings': ratings,
        'audit_events_as_actor': events,
        'excluded_by_design': [
            'password hashes', 'TOTP secrets', 'recovery-code hashes', 'device token hashes',
            'service-account tokens', 'integration secrets', 'provider raw payment payloads',
            'other users personal data',
        ],
    }
    audit(user, 'privacy.export', user, {'sections': sorted(payload.keys())}, request=request)
    body = json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="promptmaster-datenauskunft.json"'
    response['Cache-Control'] = 'no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
def buy(request):
    if not request.user.email_verified_at:
        messages.error(request, 'Bitte zuerst Ihre E-Mail-Adresse bestätigen.')
        return redirect('portal:dashboard')

    from apps.catalog.models import Product
    from apps.orders.forms import PurchaseForm
    from apps.orders.services import create_order

    company_obj, membership = _ctx(request)
    if company_obj and (not membership or membership.role != 'admin'):
        raise PermissionDenied
    private_customer = not company_obj
    product = get_object_or_404(Product, code='PRO', active=True, purchasable=True)
    checkout_session_key, checkout_key = _checkout_key(request, 'buy:PRO')
    form = PurchaseForm(request.POST or None, require_withdrawal=private_customer)

    if request.method == 'POST' and form.is_valid():
        try:
            documents = _active_legal_documents(private_customer=private_customer)
            order = create_order(user=request.user, product=product, quantity=form.cleaned_data['quantity'], idempotency_key=checkout_key)
            _record_legal_acceptances(request, order, documents)
            response = _start_mollie_checkout(
                request,
                order,
                f'PromptMaster {order.order_number}',
                {'order_id': str(order.id)},
            )
            if response:
                _rotate_checkout_key(request, checkout_session_key)
                return response
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        except Exception:
            logger.exception('Checkout failed before provider redirect')
            form.add_error(None, 'Checkout konnte nicht vorbereitet werden.')
    return render(request, 'portal/buy.html', {'form': form, 'product': product})


@login_required
def renew(request, pk):
    from apps.orders.forms import RenewalForm
    from apps.orders.services import create_order

    license_obj = get_object_or_404(License.objects.select_related('product'), pk=pk)
    company_obj, membership = _ctx(request)
    allowed = license_obj.owner_user_id == request.user.id or (
        company_obj
        and membership
        and membership.role == 'admin'
        and license_obj.company_id == company_obj.id
    )
    if not allowed:
        raise PermissionDenied
    if license_obj.status in {'refunded', 'payment_review', 'blocked'}:
        raise PermissionDenied

    private_customer = license_obj.owner_user_id == request.user.id
    checkout_session_key, checkout_key = _checkout_key(request, f'renew:{license_obj.id}')
    form = RenewalForm(request.POST or None, require_withdrawal=private_customer)
    if request.method == 'POST' and form.is_valid():
        try:
            documents = _active_legal_documents(private_customer=private_customer)
            order = create_order(user=request.user, product=license_obj.product, quantity=1, target_license=license_obj, idempotency_key=checkout_key)
            _record_legal_acceptances(request, order, documents)
            response = _start_mollie_checkout(
                request,
                order,
                f'Verlängerung {license_obj.license_number}',
                {'order_id': str(order.id), 'license_id': str(license_obj.id)},
            )
            if response:
                _rotate_checkout_key(request, checkout_session_key)
                return response
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        except Exception:
            logger.exception('Renewal checkout failed')
            form.add_error(None, 'Verlängerung konnte nicht vorbereitet werden.')
    return render(request, 'portal/renew.html', {'form': form, 'license': license_obj})


@login_required
def renew_index(request):
    company_obj, membership = _ctx(request)
    queryset = License.objects.select_related('product')
    if company_obj and membership and membership.role == 'admin':
        queryset = queryset.filter(company=company_obj)
    elif company_obj:
        queryset = queryset.filter(
            company=company_obj,
            assignments__user=request.user,
            assignments__ended_at__isnull=True,
        ).distinct()
    else:
        queryset = queryset.filter(owner_user=request.user)
    queryset = queryset.exclude(
        status__in=['refunded', 'payment_review', 'blocked']
    ).order_by('valid_until', 'license_number')
    return render(
        request,
        'portal/renew_index.html',
        {'licenses': queryset},
    )


@login_required
def invitation_revoke(request, pk):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    invitation = get_object_or_404(Invitation, pk=pk, company=company_obj, accepted_at__isnull=True)
    if not invitation.revoked_at:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=['revoked_at', 'updated_at'])
        audit(request.user, 'invitation.revoked', invitation, {}, request=request)
    messages.success(request, 'Einladung widerrufen.')
    return redirect('portal:invitations')


@login_required
def invitation_resend(request, pk):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    limited = check_rate(request, f'invite-send:{company_obj.pk}:{request.user.pk}', 30, 3600)
    if limited:
        return limited
    old = get_object_or_404(Invitation, pk=pk, company=company_obj, accepted_at__isnull=True)
    try:
        invitation, raw = create_invitation(
            company=company_obj,
            actor=request.user,
            email=old.email,
            first_name=old.first_name,
            last_name=old.last_name,
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        url = request.build_absolute_uri(reverse('accounts:accept_invitation', args=[raw]))
        queue_email('invite', invitation.email, {'url': url})
        messages.success(request, 'Neue Einladung versendet.')
    return redirect('portal:invitations')


@login_required
def team_member(request, user_id):
    company_obj, _ = _admin(request)
    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=company_obj,
        user_id=user_id,
        active=True,
    )
    free = License.objects.filter(
        company=company_obj,
        status='free',
        valid_until__gt=timezone.now(),
    ).select_related('product')
    assignments = LicenseAssignment.objects.filter(
        user=member.user,
        license__company=company_obj,
        ended_at__isnull=True,
    ).select_related('license__product')
    return render(
        request,
        'portal/team_member.html',
        {
            'member': member,
            'free_licenses': free,
            'assignments': assignments,
            'devices': member.user.devices.filter(revoked_at__isnull=True).select_related('license'),
        },
    )


@login_required
def member_assign(request, user_id):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    member = get_object_or_404(Membership, company=company_obj, user_id=user_id, active=True)
    license_obj = get_object_or_404(License, pk=request.POST.get('license_id'), company=company_obj)
    try:
        assign_license(license_obj, member.user, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, 'Lizenz zugewiesen.')
    return redirect('portal:team_member', user_id=user_id)


@login_required
def member_assignment_link(request, user_id):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    member = get_object_or_404(Membership.objects.select_related('user'), company=company_obj, user_id=user_id, active=True)
    license_obj = get_object_or_404(License, pk=request.POST.get('license_id'), company=company_obj)
    try:
        link, raw = create_assignment_link(
            company=company_obj,
            target_user=member.user,
            license_obj=license_obj,
            actor=request.user,
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('portal:team_member', user_id=user_id)
    claim_url = request.build_absolute_uri(reverse('portal:claim_assignment_link', args=[raw]))
    queue_email(
        'assignment_link',
        member.user.email,
        {'url': claim_url, 'license': license_obj.license_number, 'expiry': link.expires_at},
    )
    messages.success(request, 'Sicherer Zuordnungslink wurde erzeugt und an den Benutzer versendet.')
    return render(
        request,
        'portal/assignment_link_created.html',
        {'member': member, 'license': license_obj, 'claim_url': claim_url, 'expires_at': link.expires_at},
    )


@login_required
def claim_assignment_link(request, token):
    if request.method == 'POST':
        try:
            consume_assignment_link(raw_token=token, user=request.user, request=request)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(request, 'Lizenz wurde Ihrem Benutzerkonto zugewiesen.')
            return redirect('portal:licenses')
    return render(request, 'portal/assignment_link_claim.html', {'token': token})


@login_required
def member_release(request, user_id, license_id):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    license_obj = get_object_or_404(
        License,
        pk=license_id,
        company=company_obj,
        assignments__user_id=user_id,
        assignments__ended_at__isnull=True,
    )
    release_license(license_obj, request.user)
    messages.success(request, 'Lizenz freigegeben.')
    return redirect('portal:team_member', user_id=user_id)


@login_required
def member_deactivate(request, user_id):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=company_obj,
        user_id=user_id,
        active=True,
    )
    if member.role == 'admin':
        messages.error(request, 'Firmenadministrator zuerst übertragen.')
        return redirect('portal:team_member', user_id=user_id)

    with transaction.atomic():
        member = Membership.objects.select_for_update().select_related('user').get(pk=member.pk)
        assignment_rows = list(
            LicenseAssignment.objects.select_for_update()
            .filter(
                user=member.user,
                license__company=company_obj,
                ended_at__isnull=True,
            )
            .select_related('license')
        )
        for row in assignment_rows:
            release_license(row.license, request.user)
        DeviceRegistration.objects.filter(user=member.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        member.active = False
        member.save(update_fields=['active', 'updated_at'])
        member.user.is_active = False
        member.user.save(update_fields=['is_active', 'updated_at'])
        bump_security_version(member.user)
        audit(request.user, 'company.member_deactivated', member, {'user': str(member.user_id)}, request=request)

    messages.success(request, 'Benutzer deaktiviert; Lizenz und Geräteslots freigegeben.')
    return redirect('portal:team')


@login_required
def member_delete(request, user_id):
    company_obj, _ = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    if request.POST.get('confirm') != '1':
        messages.error(request, 'Benutzerlöschung muss ausdrücklich bestätigt werden.')
        return redirect('portal:team_member', user_id=user_id)

    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=company_obj,
        user_id=user_id,
        active=True,
    )
    if member.role == 'admin':
        messages.error(request, 'Firmenadministrator zuerst übertragen.')
        return redirect('portal:team_member', user_id=user_id)

    with transaction.atomic():
        member = (
            Membership.objects.select_for_update()
            .select_related('user')
            .get(pk=member.pk)
        )
        deletion = DeletionRequest.objects.create(
            user=member.user,
            status='processing',
            notes=f'Durch Firmenadministrator {request.user.id} ausgelöst.',
        )
        process_deletion_request(
            deletion,
            actor=request.user,
            request=request,
        )

    messages.success(
        request,
        'Benutzer gelöscht/anonymisiert; Lizenzen und Gerätezugänge wurden beendet.',
    )
    return redirect('portal:team')


@login_required
def transfer_admin_view(request, user_id):
    company_obj, _ = _admin(request)
    new_member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=company_obj,
        user_id=user_id,
        active=True,
    )
    form = TransferAdminForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if not request.user.check_password(form.cleaned_data['password']):
            form.add_error('password', 'Passwort falsch.')
        elif not request.session.get('two_factor_ok'):
            raise PermissionDenied
        else:
            try:
                transfer_admin(company_obj, request.user, new_member.user, actor=request.user, request=request)
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                messages.success(request, 'Firmenadministrator übertragen. Bitte melden Sie sich aufgrund der Rechteänderung erneut an.')
                return redirect('accounts:login')
    return render(
        request,
        'portal/form.html',
        {'title': f'Administrator an {new_member.user.full_name} übertragen', 'form': form},
    )
