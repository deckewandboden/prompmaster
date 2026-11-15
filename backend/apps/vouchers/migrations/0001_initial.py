"""Voucher campaigns and audited redemptions; additive schema, no data changes."""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0002_rename_catalog_pp_stream_idx_catalog_pro_product_2e5f65_idx"),
        ("companies", "0004_invitation_role"),
        ("licenses", "0005_rename_licenses_l_status_idx_licenses_li_status_3263d5_idx_and_more"),
        ("orders", "0002_rename_orders_o_status_idx_orders_orde_status_25e057_idx"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Voucher",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code_hash", models.CharField(max_length=64, editable=False, unique=True)),
                ("code_suffix", models.CharField(max_length=4, editable=False)),
                ("title", models.CharField(max_length=140)),
                ("note", models.TextField(blank=True)),
                ("kind", models.CharField(max_length=12, choices=[
                    ("percent", "Prozentualer Rabatt"),
                    ("fixed", "Fester Rabatt je Lizenz"),
                    ("trial", "Kostenlose Pro-Laufzeit"),
                ])),
                ("percent_off", models.PositiveSmallIntegerField(default=0)),
                ("fixed_gross_off", models.DecimalField(max_digits=10, decimal_places=2, default=0)),
                ("trial_days", models.PositiveSmallIntegerField(default=0)),
                ("max_redemptions", models.PositiveIntegerField(default=1)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("allow_renewal", models.BooleanField(default=False)),
                ("starts_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(null=True, blank=True)),
                ("active", models.BooleanField(default=True)),
                ("bound_company", models.ForeignKey(
                    to="companies.company", null=True, blank=True,
                    related_name="assigned_vouchers", on_delete=django.db.models.deletion.PROTECT)),
                ("bound_user", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, null=True, blank=True,
                    related_name="assigned_vouchers", on_delete=django.db.models.deletion.PROTECT)),
                ("created_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, related_name="created_vouchers",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("product", models.ForeignKey(
                    to="catalog.product", related_name="vouchers",
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
            options={"indexes": [
                models.Index(fields=["active", "expires_at"], name="voucher_active_exp_idx"),
                models.Index(fields=["bound_company", "active"], name="voucher_company_act_idx"),
            ]},
        ),
        migrations.AddConstraint(
            model_name="voucher",
            constraint=models.CheckConstraint(condition=Q(max_redemptions__gte=1),
                                             name="voucher_max_uses_positive"),
        ),
        migrations.AddConstraint(
            model_name="voucher",
            constraint=models.CheckConstraint(condition=Q(used_count__lte=F("max_redemptions")),
                                             name="voucher_uses_not_over_limit"),
        ),
        migrations.AddConstraint(
            model_name="voucher",
            constraint=models.CheckConstraint(condition=Q(bound_company__isnull=True) | Q(bound_user__isnull=True),
                                             name="voucher_single_scope"),
        ),
        migrations.AddConstraint(
            model_name="voucher",
            constraint=models.CheckConstraint(condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("starts_at")),
                                             name="voucher_valid_window"),
        ),
        migrations.CreateModel(
            name="VoucherRedemption",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(max_length=12, default="reserved", choices=[
                    ("reserved", "Für Bestellung reserviert"),
                    ("redeemed", "Eingelöst"),
                    ("cancelled", "Fehlgeschlagen / freigegeben"),
                ])),
                ("discount_gross", models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ("granted_days", models.PositiveSmallIntegerField(default=0)),
                ("granted_from", models.DateTimeField(null=True, blank=True)),
                ("granted_until", models.DateTimeField(null=True, blank=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("voucher", models.ForeignKey(
                    to="vouchers.voucher", related_name="redemptions",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("redeemed_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, related_name="voucher_redemptions_created",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("beneficiary", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, null=True, blank=True,
                    related_name="received_voucher_redemptions",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("company", models.ForeignKey(
                    to="companies.company", null=True, blank=True,
                    related_name="voucher_redemptions",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("order", models.OneToOneField(
                    to="orders.order", null=True, blank=True,
                    related_name="voucher_redemption",
                    on_delete=django.db.models.deletion.PROTECT)),
                ("license", models.ForeignKey(
                    to="licenses.license", null=True, blank=True,
                    related_name="voucher_redemptions",
                    on_delete=django.db.models.deletion.PROTECT)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["company", "-created_at"], name="voucher_red_company_idx"),
                    models.Index(fields=["voucher", "status"], name="voucher_red_status_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="voucherredemption",
            constraint=models.CheckConstraint(
                condition=Q(discount_gross__gte=0),
                name="voucher_red_discount_nonneg",
            ),
        ),
    ]
