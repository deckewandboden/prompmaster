"""Secure voucher issuance, discount reservations and zero-price trial entitlements.

All state transitions are transactional. Voucher codes are never stored in
plaintext, emailed implicitly or placed in query strings.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.audit.services import audit
from apps.catalog.services import current_price
from apps.companies.models import Membership
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.licenses.services import assign_license, has_current_term
from apps.orders.models import Order, OrderItem

from .models import Voucher, VoucherRedemption


CENT = Decimal("0.01")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 20


def normalize_code(raw: str) -> str:
    raw = str(raw or "").strip().upper()
    compact = "".join(letter for letter in raw if letter not in "- \t\r\n")
    if not compact.startswith("PF") or len(compact) != CODE_LENGTH + 2:
        raise ValidationError("Gutscheincode ungültig oder nicht verfügbar.")
    if any(letter not in ALPHABET for letter in compact[2:]):
        raise ValidationError("Gutscheincode ungültig oder nicht verfügbar.")
    return compact


def code_digest(raw: str) -> str:
    return hashlib.sha256(normalize_code(raw).encode("ascii")).hexdigest()


def new_code() -> str:
    token = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return "PF-" + "-".join(token[index:index + 4] for index in range(0, CODE_LENGTH, 4))


@transaction.atomic
def issue_vouchers(*, actor, count=1, **values):
    if not actor.is_active or not actor.is_staff:
        raise ValidationError("Nur netstyle kann Gutscheine erstellen.")
    if not (1 <= int(count) <= 100):
        raise ValidationError("Pro Aktion sind 1 bis 100 Gutscheine zulässig.")
    results = []
    for _ in range(int(count)):
        raw = new_code()
        voucher = Voucher(
            created_by=actor, code_hash=code_digest(raw),
            code_suffix=normalize_code(raw)[-4:], **values,
        )
        voucher.full_clean()
        voucher.save()
        audit(actor, "voucher.created", voucher, {
            "kind": voucher.kind,
            "title": voucher.title,
            "limit": voucher.max_redemptions,
            "scope_company": str(voucher.bound_company_id or ""),
            "scope_user": str(voucher.bound_user_id or ""),
        })
        results.append((voucher, raw))
    return results


def _validate(voucher, *, user, company, product, renewal=False, beneficiary=None):
    now = timezone.now()
    if not voucher.active or voucher.starts_at > now or (
        voucher.expires_at and voucher.expires_at <= now
    ):
        raise ValidationError("Gutschein nicht verfügbar oder abgelaufen.")
    if voucher.used_count >= voucher.max_redemptions:
        raise ValidationError("Dieser Gutschein ist bereits vollständig eingelöst.")
    if voucher.product_id != product.pk or product.code != "PRO" or not product.active:
        raise ValidationError("Dieser Gutschein gilt nicht für das gewählte Produkt.")
    if company and company.status != "active":
        raise ValidationError("Deaktivierte Unternehmen können keine Gutscheine einlösen.")
    if voucher.bound_company_id and voucher.bound_company_id != getattr(company, "pk", None):
        raise ValidationError("Gutschein ist für einen anderen Kunden ausgestellt.")
    target_user = beneficiary or user
    if voucher.bound_user_id and (target_user is None or voucher.bound_user_id != target_user.pk):
        raise ValidationError("Gutschein ist für einen anderen Benutzer ausgestellt.")
    if renewal and not voucher.allow_renewal:
        raise ValidationError("Gutschein gilt nur für neue Pro-Lizenzen.")


def _check_single_use(voucher, *, user, kind, beneficiary=None):
    # Customers can purchase many seats in one discounted order, but must
    # not repeatedly re-use the same code on different orders. Trial grants
    # are single-use per named beneficiary; unassigned seats can be multiple.
    rows = VoucherRedemption.objects.filter(voucher=voucher).exclude(status="cancelled")
    if kind == "trial":
        if beneficiary and rows.filter(beneficiary=beneficiary).exists():
            raise ValidationError("Dieser Benutzer hat den Gutschein bereits eingelöst.")
    elif (
        user is not None
        and not voucher.bound_company_id
        and not voucher.bound_user_id
        and rows.filter(redeemed_by=user).exists()
    ):
        # Public promotions are limited to one order per buyer. Explicitly
        # customer-bound campaigns can be used repeatedly up to their
        # deliberately configured campaign quota.
        raise ValidationError("Dieser Gutschein wurde von diesem Konto bereits genutzt.")


def _fetch(raw, *, lock=False):
    try:
        digest = code_digest(raw)
    except ValidationError:
        raise
    queryset = Voucher.objects
    if lock:
        queryset = queryset.select_for_update()
    voucher = queryset.filter(code_hash=digest).first()
    if voucher is None:
        raise ValidationError("Gutscheincode ungültig oder nicht verfügbar.")
    return voucher


def discount_quote(*, code, user, company, product, unit_gross, quantity, renewal=False, lock=False):
    """Check a discount and calculate a safe per-seat gross amount.

    No writes. The caller of lock=True must already be in an atomic transaction
    and immediately reserve the returned voucher before releasing its row lock.
    """
    voucher = _fetch(code, lock=lock)
    if voucher.kind not in {"percent", "fixed"}:
        raise ValidationError("Kostenlose Zeitgutscheine bitte im Gutscheinbereich einlösen.")
    _validate(voucher, user=user, company=company, product=product, renewal=renewal)
    _check_single_use(voucher, user=user, kind="discount")

    original = Decimal(unit_gross).quantize(CENT)
    if voucher.kind == "percent":
        saving = (original * Decimal(voucher.percent_off) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        saving = Decimal(voucher.fixed_gross_off).quantize(CENT)
    after = original - saving
    if saving <= 0 or after < CENT:
        raise ValidationError("Gutscheinbetrag ist für diesen Lizenzpreis nicht zulässig.")
    if int(quantity) < 1:
        raise ValidationError("Ungültige Lizenzanzahl.")
    return voucher, after, (saving * int(quantity)).quantize(CENT)


def reserve_discount(*, voucher, order, actor, company, saving):
    """Must run under the locked Voucher row inside create_order transaction."""
    if order.status != "draft" or order.gross_total <= 0:
        raise ValidationError("Gutschein darf nur für eine zahlungspflichtige Bestellung verwendet werden.")
    voucher.used_count = F("used_count") + 1
    voucher.save(update_fields=["used_count", "updated_at"])
    redemption = VoucherRedemption.objects.create(
        voucher=voucher, redeemed_by=actor, beneficiary=actor,
        company=company, order=order, status="reserved", discount_gross=saving,
    )
    audit(actor, "voucher.discount_reserved", redemption, {
        "voucher_id": str(voucher.pk), "order": str(order.pk),
        "discount_gross": str(saving),
    })
    return redemption


def complete_discount_order(order):
    """Idempotent. Invoked only after verified provider-paid activation."""
    redemption = (
        VoucherRedemption.objects.select_for_update()
        .filter(order=order, status="reserved")
        .first()
    )
    if redemption is not None:
        redemption.status = "redeemed"
        redemption.completed_at = timezone.now()
        redemption.save(update_fields=["status", "completed_at", "updated_at"])
        audit(None, "voucher.discount_paid", redemption, {"order": str(order.pk)})


@transaction.atomic
def release_terminal_discount_reservation(order):
    """Release voucher quota only for provider-confirmed terminal non-payments.

    Provider uncertainty is deliberately NOT treated as a terminal failure:
    no payment, open/unknown/pending payment and ambiguous create attempts
    must retain their reservation for reconciliation. Repeated calls are safe.
    """
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status not in {"failed", "canceled"}:
        return False
    redemption = (
        VoucherRedemption.objects.select_for_update()
        .filter(order=locked, status="reserved")
        .first()
    )
    if redemption is None:
        return False
    # Never infer terminal provider status from an application-side exception.
    payments = locked.payments.all()
    if not payments.exists():
        return False
    if payments.filter(processed_paid=True).exists():
        return False
    if payments.exclude(status__in={"failed", "canceled", "expired"}).exists():
        return False

    voucher = Voucher.objects.select_for_update().get(pk=redemption.voucher_id)
    changed = Voucher.objects.filter(
        pk=voucher.pk, used_count__gt=0
    ).update(used_count=F("used_count") - 1, updated_at=timezone.now())
    if changed != 1:
        raise ValidationError(
            "Gutscheinreservierung kann wegen inkonsistentem Kontingent nicht freigegeben werden."
        )
    redemption.status = "cancelled"
    redemption.completed_at = timezone.now()
    redemption.save(update_fields=["status", "completed_at", "updated_at"])
    audit(None, "voucher.discount_terminal_released", redemption, {
        "order": str(locked.pk), "voucher": str(voucher.pk),
        "reason": "provider_confirmed_nonpayment",
    })
    return True


@transaction.atomic
def redeem_trial(*, code, actor, company, beneficiary=None, request=None):
    """Create/extend a real Pro license with a free, auditable zero-value term.

    Company administrator may create an unassigned company seat (beneficiary
    None) or target an active member. Private customers target themselves.
    It never creates provider payments or converts a draft paid order to paid.
    """
    if not actor.is_active or not actor.email_verified_at or actor.is_staff:
        raise ValidationError("Bitte ein aktives, bestätigtes Kundenkonto verwenden.")
    from apps.catalog.models import Product

    product = Product.objects.filter(code="PRO", active=True).first()
    if product is None:
        raise ValidationError("Pro ist derzeit nicht verfügbar.")

    if company is not None:
        membership = Membership.objects.select_for_update().filter(
            company=company, user=actor, active=True, role="admin",
        ).first()
        if membership is None:
            raise ValidationError("Nur der Firmenadministrator kann Zeitgutscheine einlösen.")
        if beneficiary is not None:
            target_membership = Membership.objects.filter(
                company=company, user=beneficiary, active=True,
            ).first()
            if not target_membership or not beneficiary.is_active or not beneficiary.email_verified_at:
                raise ValidationError("Empfänger muss aktives, bestätigtes Firmenmitglied sein.")
    else:
        if beneficiary is not None and beneficiary.pk != actor.pk:
            raise ValidationError("Privatcodes sind ausschließlich für das eigene Konto.")
        if not hasattr(actor, "private_customer"):
            raise ValidationError("Ein Privatkundenkonto ist erforderlich.")
        beneficiary = actor

    voucher = _fetch(code, lock=True)
    if voucher.bound_user_id and beneficiary is None:
        raise ValidationError("Persönliche Zeitgutscheine müssen direkt dem vorgesehenen Benutzer zugewiesen werden.")
    if voucher.kind != "trial":
        raise ValidationError("Rabattgutscheine bitte beim Pro-Kauf verwenden.")
    _validate(voucher, user=actor, company=company, product=product, beneficiary=beneficiary)
    _check_single_use(voucher, user=actor, kind="trial", beneficiary=beneficiary)

    price = current_price(product, "new")
    if price is None:
        raise ValidationError("Für Pro fehlt die Preisversion; Gutschein kann nicht gebucht werden.")

    now = timezone.now()
    # A trial must never defeat an existing administrator/payment block.
    # Check the intended recipient rather than only the actor.
    if beneficiary:
        barred = {"blocked", "payment_review", "refunded"}
        if company:
            blocked_seats = License.objects.filter(
                company=company, product=product,
                status__in=barred,
                assignments__user=beneficiary,
                assignments__ended_at__isnull=True,
            )
        else:
            blocked_seats = License.objects.filter(
                owner_user=beneficiary, product=product,
                status__in=barred,
            )
        if blocked_seats.exists():
            raise ValidationError(
                "Für diesen Benutzer besteht eine gesperrte oder zu prüfende Pro-Lizenz."
            )

    active_license = None
    if beneficiary:
        if company:
            assigned_ids = LicenseAssignment.objects.filter(
                user=beneficiary, ended_at__isnull=True,
                license__company=company, license__product=product,
            ).values_list("license_id", flat=True)
            active_license = (
                License.objects.select_for_update()
                .filter(pk__in=assigned_ids, status="active", valid_until__gt=now)
                .order_by("-valid_until").first()
            )
        else:
            active_license = (
                License.objects.select_for_update()
                .filter(owner_user=actor, product=product, status="active", valid_until__gt=now)
                .order_by("-valid_until").first()
            )
        if active_license and not has_current_term(active_license, now):
            active_license = None

    start = max(now, active_license.valid_until) if active_license else now
    end = start + timedelta(days=voucher.trial_days)
    order = Order.objects.create(
        order_number=f"PM-V-{uuid.uuid4().hex.upper()}",
        company=company,
        private_user=actor if company is None else None,
        status="paid", currency=price.currency, gross_total=Decimal("0.00"),
        tax_total=Decimal("0.00"),
        billing_snapshot={
            "source": "voucher_trial", "voucher_id": str(voucher.pk),
            "trial_days": voucher.trial_days, "no_provider_payment": True,
        },
        idempotency_key=secrets.token_urlsafe(24),
    )
    item = OrderItem.objects.create(
        order=order, product=product, price_version=price, quantity=1,
        unit_gross=Decimal("0.00"), unit_net=Decimal("0.00"),
        tax_rate=Decimal("0.00"),
        product_name_snapshot=f"{product.name} · Gutschein",
        target_license=active_license,
    )
    if active_license:
        license_obj = active_license
        license_obj.valid_until = end
        license_obj.save(update_fields=["valid_until", "updated_at"])
    else:
        license_obj = License.objects.create(
            company=company, owner_user=None if company else actor,
            product=product,
            status="free" if company else "active",
            valid_from=start, valid_until=end,
        )
    LicenseTerm.objects.create(
        license=license_obj, order_item=item, valid_from=start,
        valid_until=end, paid_gross_amount=Decimal("0.00"),
    )
    if not active_license:
        if company and beneficiary:
            assign_license(license_obj, beneficiary, actor)
            # assign_license updates a separately locked ORM instance.
            # Reload so returned redemption and same-request UI reflect ACTIVE.
            license_obj.refresh_from_db(fields=["status"])
        elif company is None:
            LicenseAssignment.objects.create(license=license_obj, user=actor)

    redemption = VoucherRedemption.objects.create(
        voucher=voucher, redeemed_by=actor, beneficiary=beneficiary,
        company=company, order=order, license=license_obj, status="redeemed",
        granted_days=voucher.trial_days, granted_from=start,
        granted_until=end, completed_at=now,
    )
    voucher.used_count = F("used_count") + 1
    voucher.save(update_fields=["used_count", "updated_at"])
    audit(actor, "voucher.trial_redeemed", redemption, {
        "license": str(license_obj.pk), "days": voucher.trial_days,
        "beneficiary": str(beneficiary.pk) if beneficiary else "unassigned",
    }, request=request)
    return redemption
