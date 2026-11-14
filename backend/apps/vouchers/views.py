"""Voucher screens: netstyle controls campaigns, customers redeem without mint rights."""
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.audit.services import audit
from apps.companies.models import Membership
from apps.core.permissions import has_perm
from apps.core.security import check_rate

from .forms import VoucherCreateForm, VoucherEditForm
from .models import Voucher, VoucherRedemption
from .services import issue_vouchers, redeem_trial


def staff_voucher_perm(permission):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.is_staff or not has_perm(request.user, permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


@staff_voucher_perm("licenses.read")
def staff_vouchers(request):
    vouchers = Voucher.objects.select_related(
        "product", "bound_company", "bound_user"
    ).order_by("-created_at")
    search = (request.GET.get("q") or "").strip()[:120]
    status = request.GET.get("state", "")
    kind = request.GET.get("kind", "")
    if search:
        vouchers = vouchers.filter(
            Q(title__icontains=search) | Q(note__icontains=search)
            | Q(code_suffix__icontains=search)
            | Q(bound_company__name__icontains=search)
            | Q(bound_user__email__icontains=search)
        )
    if status == "active":
        vouchers = vouchers.filter(active=True)
    elif status == "inactive":
        vouchers = vouchers.filter(active=False)
    if kind in {"trial", "percent", "fixed"}:
        vouchers = vouchers.filter(kind=kind)
    page = Paginator(vouchers, 40).get_page(request.GET.get("page"))
    return render(request, "ns_admin/vouchers.html", {
        "page": page, "q": search, "selected_state": status,
        "selected_kind": kind, "can_write": has_perm(request.user, "licenses.write"),
        "voucher_total": Voucher.objects.count(),
        "voucher_active": Voucher.objects.filter(active=True).count(),
        "voucher_redemptions": VoucherRedemption.objects.filter(status="redeemed").count(),
    })


@staff_voucher_perm("licenses.write")
def staff_voucher_create(request):
    form = VoucherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        count = data.pop("code_count")
        try:
            minted = issue_vouchers(
                actor=request.user, count=count,
                title=data["title"], note=data.get("note") or "",
                kind=data["kind"], product=data["product"],
                percent_off=data.get("percent_off") or 0,
                fixed_gross_off=data.get("fixed_gross_off") or 0,
                trial_days=data.get("trial_days") or 0,
                max_redemptions=data["max_redemptions"],
                starts_at=data["starts_at"], expires_at=data.get("expires_at"),
                bound_company=data.get("bound_company"),
                bound_user=data.get("bound_user"),
                allow_renewal=data.get("allow_renewal") or False,
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            response = render(request, "ns_admin/voucher_issued.html", {
                "minted": minted,
                "title": _("Neue Gutscheincodes"),
            })
            response["Cache-Control"] = "no-store"
            response["Pragma"] = "no-cache"
            return response
    return render(request, "ns_admin/voucher_form.html", {
        "title": _("Gutscheine erstellen"), "form": form,
    })


@staff_voucher_perm("licenses.read")
def staff_voucher_detail(request, pk):
    voucher = get_object_or_404(
        Voucher.objects.select_related("product", "bound_company", "bound_user"), pk=pk,
    )
    form = VoucherEditForm(voucher=voucher)
    history = voucher.redemptions.select_related(
        "company", "beneficiary", "redeemed_by", "license", "order"
    ).order_by("-created_at")[:100]
    return render(request, "ns_admin/voucher_detail.html", {
        "voucher": voucher, "form": form, "history": history,
        "can_write": has_perm(request.user, "licenses.write"),
    })


@staff_voucher_perm("licenses.write")
@require_POST
@transaction.atomic
def staff_voucher_edit(request, pk):
    voucher = get_object_or_404(Voucher.objects.select_for_update(), pk=pk)
    form = VoucherEditForm(request.POST, voucher=voucher)
    if form.is_valid():
        for field in ("title", "note", "max_redemptions", "expires_at"):
            setattr(voucher, field, form.cleaned_data[field])
        voucher.full_clean()
        voucher.save(update_fields=["title", "note", "max_redemptions", "expires_at", "updated_at"])
        audit(request.user, "voucher.metadata_updated", voucher, {
            "limit": voucher.max_redemptions, "expires_at": str(voucher.expires_at or ""),
        }, request=request)
        messages.success(request, _("Gutschein aktualisiert."))
        return redirect("ns_admin:voucher_detail", pk=voucher.pk)
    history = voucher.redemptions.select_related("company", "beneficiary", "redeemed_by").order_by("-created_at")[:100]
    return render(request, "ns_admin/voucher_detail.html", {
        "voucher": voucher, "form": form, "history": history, "can_write": True,
    }, status=400)


@staff_voucher_perm("licenses.write")
@require_POST
@transaction.atomic
def staff_voucher_toggle(request, pk):
    voucher = get_object_or_404(Voucher.objects.select_for_update(), pk=pk)
    voucher.active = not voucher.active
    voucher.save(update_fields=["active", "updated_at"])
    audit(request.user, "voucher.enabled" if voucher.active else "voucher.disabled",
          voucher, {"active": voucher.active}, request=request)
    messages.success(request, _("Gutscheinstatus geändert. Bestehende Nutzungsrechte bleiben unverändert."))
    return redirect("ns_admin:voucher_detail", pk=voucher.pk)


@login_required
def portal_vouchers(request):
    from apps.companies.portal import _ctx
    company, membership = _ctx(request)
    is_admin = bool(company and membership and membership.role == "admin")
    can_redeem = is_admin or not company
    if company and is_admin:
        records = VoucherRedemption.objects.filter(company=company)
        assigned = Voucher.objects.filter(bound_company=company)
        members = Membership.objects.filter(company=company, active=True, user__is_active=True).select_related("user").order_by("user__email")
    elif company:
        records = VoucherRedemption.objects.filter(company=company, beneficiary=request.user)
        assigned = Voucher.objects.filter(bound_user=request.user)
        members = Membership.objects.none()
    else:
        records = VoucherRedemption.objects.filter(
            Q(redeemed_by=request.user) | Q(beneficiary=request.user)
        ).distinct()
        assigned = Voucher.objects.filter(bound_user=request.user)
        members = Membership.objects.none()
    records = records.select_related("voucher", "license", "beneficiary", "redeemed_by").order_by("-created_at")[:100]
    assigned = assigned.select_related("product").order_by("-created_at")[:50]
    return render(request, "portal/vouchers.html", {
        "company": company, "membership": membership,
        "can_redeem": can_redeem, "is_company_admin": is_admin,
        "members": members, "assigned": assigned, "records": records,
    })


@login_required
@require_POST
def portal_voucher_redeem(request):
    from apps.companies.portal import _ctx
    company, membership = _ctx(request)
    if company and (not membership or membership.role != "admin"):
        raise PermissionDenied
    limited = check_rate(request, "voucher-redeem", 12, 3600)
    if limited:
        return limited
    raw_code = (request.POST.get("voucher_code") or "").strip()
    target_id = (request.POST.get("target_user") or "").strip()
    target = None
    if company and target_id:
        target = get_object_or_404(
            User, pk=target_id,
            company_memberships__company=company,
            company_memberships__active=True,
        )
    try:
        redemption = redeem_trial(
            code=raw_code, actor=request.user,
            company=company, beneficiary=target, request=request,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        label = redemption.license.license_number if redemption.license else _("Lizenz")
        messages.success(request, _("Gutschein eingelöst. Pro-Lizenz: %(license)s") % {"license": label})
    return redirect("portal:vouchers")


@require_POST
def public_voucher_quote(request):
    """Same-origin, CSRF-protected, GET-free price preview for new customers."""
    from decimal import Decimal
    from django.http import JsonResponse
    from apps.catalog.models import Product
    from apps.catalog.services import current_price
    from apps.orders.services import MAX_PURCHASE_QUANTITY
    from .services import discount_quote

    limited = check_rate(request, "public-voucher-quote", 20, 3600)
    if limited:
        return limited
    try:
        quantity = int(request.POST.get("quantity") or 1)
        if quantity < 1 or quantity > MAX_PURCHASE_QUANTITY:
            raise ValidationError(_("Ungültige Lizenzanzahl."))
        code = (request.POST.get("voucher_code") or "").strip()
        product = Product.objects.filter(code="PRO", active=True, purchasable=True).first()
        price = current_price(product, "new") if product else None
        if not code or price is None:
            raise ValidationError(_("Gutschein oder Preis nicht verfügbar."))
        voucher, new_unit, saving = discount_quote(
            code=code, user=None, company=None, product=product,
            unit_gross=price.gross_amount, quantity=quantity, renewal=False,
        )
        if voucher.kind == "fixed" and price.currency != "EUR":
            raise ValidationError(_("Festbetrag ist für diese Währung nicht zulässig."))
        # Public checkout can only quote unbound campaign codes. Company- or
        # person-scoped codes require logged-in, tenant-aware customer checkout.
        if voucher.bound_company_id or voucher.bound_user_id:
            raise ValidationError(_("Bitte den Gutschein im Kundenportal einlösen."))
        response = JsonResponse({
            "valid": True, "title": voucher.title, "currency": price.currency,
            "discountGrossCents": int(saving * 100),
            "totalGrossCents": int(new_unit * quantity * 100),
            "originalGrossCents": int(price.gross_amount * quantity * 100),
        })
    except (ValidationError, ValueError):
        response = JsonResponse({"valid": False, "error": _("Gutschein ungültig oder nicht verfügbar.")}, status=400)
    response["Cache-Control"] = "no-store"
    return response
