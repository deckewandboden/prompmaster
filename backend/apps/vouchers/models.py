"""Audited, tenant-scoped PROMPTFINISHER discount and trial vouchers."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Voucher(TimeStampedModel):
    KIND = [
        ("percent", _("Prozentualer Rabatt")),
        ("fixed", _("Fester Rabatt je Lizenz")),
        ("trial", _("Kostenlose Pro-Laufzeit")),
    ]
    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    code_suffix = models.CharField(max_length=4, editable=False)
    title = models.CharField(max_length=140)
    note = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=KIND)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="vouchers")
    percent_off = models.PositiveSmallIntegerField(default=0)
    fixed_gross_off = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    trial_days = models.PositiveSmallIntegerField(default=0)
    max_redemptions = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    allow_renewal = models.BooleanField(default=False)
    bound_company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, null=True, blank=True,
        related_name="assigned_vouchers",
    )
    bound_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="assigned_vouchers",
    )
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_vouchers",
    )

    class Meta:
        indexes = [
            models.Index(fields=["active", "expires_at"], name="voucher_active_exp_idx"),
            models.Index(fields=["bound_company", "active"], name="voucher_company_act_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_redemptions__gte=1),
                name="voucher_max_uses_positive",
            ),
            models.CheckConstraint(
                condition=Q(used_count__lte=F("max_redemptions")),
                name="voucher_uses_not_over_limit",
            ),
            models.CheckConstraint(
                condition=Q(bound_company__isnull=True) | Q(bound_user__isnull=True),
                name="voucher_single_scope",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("starts_at")),
                name="voucher_valid_window",
            ),
        ]

    def clean(self):
        errors = {}
        if self.kind == "percent" and not (1 <= self.percent_off <= 99):
            errors["percent_off"] = _("Rabattprozente müssen zwischen 1 und 99 liegen.")
        if self.kind == "fixed" and not (self.fixed_gross_off > 0):
            errors["fixed_gross_off"] = _("Ein positiver Festbetrag ist erforderlich.")
        if self.kind == "trial" and not (1 <= self.trial_days <= 1095):
            errors["trial_days"] = _("Kostenlose Laufzeit muss 1 bis 1095 Tage betragen.")
        if self.kind != "trial" and self.trial_days:
            errors["trial_days"] = _("Rabattcodes dürfen keine freie Laufzeit haben.")
        if self.kind != "fixed" and self.fixed_gross_off:
            errors["fixed_gross_off"] = _("Nur Festbetragsrabatte dürfen einen Betrag haben.")
        if self.kind != "percent" and self.percent_off:
            errors["percent_off"] = _("Nur Prozentcodes dürfen Rabattprozente haben.")
        if self.kind == "trial" and self.allow_renewal:
            errors["allow_renewal"] = _("Probezeiträume sind keine Zahlungsrabatte.")
        if self.bound_company_id and self.bound_user_id:
            errors["bound_user"] = _("Ein Code kann nur auf Firma oder Benutzer begrenzt sein.")
        if self.expires_at and self.expires_at <= self.starts_at:
            errors["expires_at"] = _("Ende muss nach Beginn liegen.")
        if self.max_redemptions < 1:
            errors["max_redemptions"] = _("Mindestens eine Einlösung erforderlich.")
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.title} · ••••{self.code_suffix}"


class VoucherRedemption(TimeStampedModel):
    STATUS = [
        ("reserved", _("Für Bestellung reserviert")),
        ("redeemed", _("Eingelöst")),
        ("cancelled", _("Fehlgeschlagen / freigegeben")),
    ]
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT, related_name="redemptions")
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="voucher_redemptions_created",
    )
    beneficiary = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="received_voucher_redemptions",
    )
    company = models.ForeignKey(
        "companies.Company", null=True, blank=True, on_delete=models.PROTECT,
        related_name="voucher_redemptions",
    )
    order = models.OneToOneField(
        "orders.Order", null=True, blank=True, on_delete=models.PROTECT,
        related_name="voucher_redemption",
    )
    license = models.ForeignKey(
        "licenses.License", null=True, blank=True, on_delete=models.PROTECT,
        related_name="voucher_redemptions",
    )
    status = models.CharField(max_length=12, choices=STATUS, default="reserved")
    discount_gross = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    granted_days = models.PositiveSmallIntegerField(default=0)
    granted_from = models.DateTimeField(null=True, blank=True)
    granted_until = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"], name="voucher_red_company_idx"),
            models.Index(fields=["voucher", "status"], name="voucher_red_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_gross__gte=0),
                name="voucher_red_discount_nonneg",
            ),
        ]

    def __str__(self):
        return f"{self.voucher.title} · {self.get_status_display()}"
