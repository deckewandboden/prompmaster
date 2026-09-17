from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.security import bump_security_version
from apps.audit.services import audit
from apps.core.datagrid import DataGrid
from apps.devices.models import DeviceRegistration
from apps.licenses.models import License, LicenseAssignment
from apps.licenses.services import release_license
from apps.notifications.services import queue_email
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.support.models import SupportRequest

from .forms import SupportForm
from .models import Membership


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


def _support_license(request, company, membership, license_id):
    if not license_id:
        return None
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
    return get_object_or_404(queryset.select_related('product'), pk=license_id)


@login_required
def member_delete(request, user_id):
    company, _membership = _admin(request)
    if request.method != 'POST':
        raise PermissionDenied
    member = get_object_or_404(
        Membership.objects.select_related('user'),
        company=company,
        user_id=user_id,
        active=True,
    )
    if member.role == 'admin':
        messages.error(request, 'Firmenadministrator muss vor dem Löschen übertragen werden.')
        return redirect('portal:team_member', user_id=user_id)

    with transaction.atomic():
        member = (
            Membership.objects.select_for_update()
            .select_related('user')
            .get(pk=member.pk)
        )
        user = User.objects.select_for_update().get(pk=member.user_id)
        assignments = list(
            LicenseAssignment.objects.select_for_update()
            .filter(
                user=user,
                license__company=company,
                ended_at__isnull=True,
            )
            .select_related('license')
        )
        for assignment in assignments:
            release_license(assignment.license, request.user)

        now = timezone.now()
        DeviceRegistration.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
        member.active = False
        member.save(update_fields=['active', 'updated_at'])

        original_user_id = str(user.id)
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
        audit(
            request.user,
            'company.member_deleted',
            member,
            {'user_id': original_user_id, 'mode': 'anonymized'},
            request=request,
        )

    messages.success(request, 'Benutzer gelöscht/anonymisiert; historische Geschäftsdaten bleiben erhalten.')
    return redirect('portal:team')


@login_required
def orders(request):
    company, membership = _ctx(request)
    if company and (not membership or membership.role != 'admin'):
        raise PermissionDenied
    queryset = Order.objects.filter(company=company) if company else Order.objects.filter(private_user=request.user)
    queryset = queryset.prefetch_related(
        Prefetch(
            'items',
            queryset=OrderItem.objects.select_related('product').prefetch_related('license_terms__license'),
            to_attr='portal_items',
        ),
        Prefetch(
            'payments',
            queryset=Payment.objects.order_by('-created_at'),
            to_attr='portal_payments',
        ),
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
def help_view(request):
    company, membership = _ctx(request)
    license_id = (request.POST.get('license') or request.GET.get('license') or '').strip()
    selected_license = _support_license(request, company, membership, license_id) if license_id else None
    form = SupportForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        now = timezone.now()
        support_context = {
            'user_id': str(request.user.id),
            'company_id': str(company.id) if company else None,
            'license_id': str(selected_license.id) if selected_license else None,
            'submitted_at': now.isoformat(),
        }
        support_request = SupportRequest.objects.create(
            user=request.user,
            company=company,
            context=support_context,
            **form.cleaned_data,
        )
        queue_email('support_confirmation', request.user.email, {'subject': form.cleaned_data['subject']})
        from apps.core.settings_store import get_setting
        support_email = get_setting('support_email', 'promptmaster@netstyle.de')
        queue_email(
            'support_notification',
            support_email,
            {
                'subject': form.cleaned_data['subject'],
                'category': support_request.get_category_display(),
                'customer': company.name if company else request.user.full_name,
                'email': request.user.email,
                'user_id': str(request.user.id),
                'license_id': support_context['license_id'] or '',
                'submitted_at': support_context['submitted_at'],
                'message': form.cleaned_data['message'],
            },
        )
        audit(
            request.user,
            'support.created',
            support_request,
            {'category': support_request.category, 'license_id': support_context['license_id']},
            request=request,
        )
        messages.success(request, 'Nachricht wurde übermittelt.')
        return redirect('portal:help')

    if company:
        history = (
            SupportRequest.objects.filter(company=company)
            if membership and membership.role == 'admin'
            else SupportRequest.objects.filter(user=request.user)
        )
    else:
        history = SupportRequest.objects.filter(user=request.user)
    return render(
        request,
        'portal/help.html',
        {
            'form': form,
            'selected_license': selected_license,
            'support_history': history.order_by('-created_at')[:100],
        },
    )
