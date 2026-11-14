"""Voucher issuance / admin forms, with immutable economic terms after issue."""
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company


class VoucherCreateForm(forms.Form):
    title = forms.CharField(max_length=140, label=_("Kampagnenbezeichnung"))
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label=_("Interner Hinweis"))
    kind = forms.ChoiceField(choices=(
        ("percent", _("Rabatt in Prozent")),
        ("fixed", _("Festbetrag je Lizenz")),
        ("trial", _("Kostenlose Pro-Nutzung")),
    ), label=_("Gutscheinart"))
    product = forms.ModelChoiceField(queryset=Product.objects.none(), label=_("Produkt"))
    percent_off = forms.IntegerField(min_value=0, max_value=99, initial=0, required=False, label=_("Rabatt in Prozent"))
    fixed_gross_off = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, initial=0,
        required=False, label=_("Rabatt je Lizenz in EUR brutto"),
    )
    trial_days = forms.IntegerField(min_value=0, max_value=1095, initial=0, required=False, label=_("Kostenlose Tage"))
    max_redemptions = forms.IntegerField(min_value=1, max_value=100000, initial=1, label=_("Maximale Einlösungen je Code"))
    code_count = forms.IntegerField(min_value=1, max_value=100, initial=1, label=_("Anzahl verschiedener Codes"))
    starts_at = forms.SplitDateTimeField(required=False, label=_("Gültig ab"))
    expires_at = forms.SplitDateTimeField(required=False, label=_("Gültig bis"))
    allow_renewal = forms.BooleanField(required=False, label=_("Rabatt auch für Verlängerungen"))
    bound_company = forms.ModelChoiceField(queryset=Company.objects.none(), required=False, label=_("Nur für Unternehmen (optional)"))
    bound_user = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label=_("Nur für Benutzer (optional)"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(code="PRO", active=True)
        self.fields["bound_company"].queryset = Company.objects.filter(status="active").order_by("name")
        self.fields["bound_user"].queryset = User.objects.filter(is_active=True, is_staff=False).order_by("email")
        self.fields["starts_at"].initial = timezone.now

    def clean(self):
        values = super().clean()
        kind = values.get("kind")
        percent = values.get("percent_off") or 0
        fixed = values.get("fixed_gross_off") or 0
        days = values.get("trial_days") or 0
        if kind == "percent" and not (1 <= percent <= 99):
            self.add_error("percent_off", _("Prozentgutscheine benötigen 1–99 Prozent."))
        if kind == "fixed" and fixed <= 0:
            self.add_error("fixed_gross_off", _("Festbetrag muss größer null sein."))
        if kind == "trial" and not (1 <= days <= 1095):
            self.add_error("trial_days", _("Kostenlose Laufzeit muss 1–1095 Tage betragen."))
        if kind != "percent" and percent:
            self.add_error("percent_off", _("Nur für Prozentgutscheine zulässig."))
        if kind != "fixed" and fixed:
            self.add_error("fixed_gross_off", _("Nur für Festbetragsgutscheine zulässig."))
        if kind != "trial" and days:
            self.add_error("trial_days", _("Nur für Zeitgutscheine zulässig."))
        if kind == "trial" and values.get("allow_renewal"):
            self.add_error("allow_renewal", _("Bei Zeitgutscheinen nicht anwendbar."))
        if values.get("bound_company") and values.get("bound_user"):
            self.add_error("bound_user", _("Entweder Unternehmen oder Benutzer binden."))
        start = values.get("starts_at") or timezone.now()
        end = values.get("expires_at")
        if end and end <= start:
            self.add_error("expires_at", _("Das Ende muss nach dem Beginn liegen."))
        values["starts_at"] = start
        return values


class VoucherEditForm(forms.Form):
    title = forms.CharField(max_length=140, label=_("Kampagne"))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label=_("Interner Hinweis"))
    max_redemptions = forms.IntegerField(min_value=1, max_value=100000, label=_("Maximale Einlösungen"))
    expires_at = forms.SplitDateTimeField(required=False, label=_("Gültig bis"))

    def __init__(self, *args, voucher, **kwargs):
        self.voucher = voucher
        initial = {
            "title": voucher.title,
            "note": voucher.note,
            "max_redemptions": voucher.max_redemptions,
            "expires_at": voucher.expires_at,
        }
        kwargs.setdefault("initial", initial)
        super().__init__(*args, **kwargs)

    def clean(self):
        values = super().clean()
        limit = values.get("max_redemptions")
        if limit is not None and limit < self.voucher.used_count:
            self.add_error("max_redemptions", _("Bereits reservierte Einlösungen dürfen nicht abgeschnitten werden."))
        end = values.get("expires_at")
        if end and end <= self.voucher.starts_at:
            self.add_error("expires_at", _("Das Ende muss nach Beginn liegen."))
        return values
