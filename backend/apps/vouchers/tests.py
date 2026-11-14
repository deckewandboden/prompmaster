"""End-to-end voucher billing, tenant security, license grants and UI regression."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductPrice, TaxRule
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.orders.models import Order
from apps.orders.services import create_order
from apps.payments.models import Payment
from apps.payments.services import _activate_order

from .models import Voucher, VoucherRedemption
from .services import code_digest, discount_quote, issue_vouchers, redeem_trial


class VoucherContractsTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.now = now
        self.staff = User.objects.create_user(
            "voucher-staff@example.test", "Secure-2026!", is_staff=True,
            is_superuser=True, email_verified_at=now,
        )
        self.admin = User.objects.create_user(
            "voucher-admin@example.test", "Secure-2026!", email_verified_at=now,
        )
        self.member = User.objects.create_user(
            "voucher-member@example.test", "Secure-2026!", email_verified_at=now,
        )
        self.other = User.objects.create_user(
            "voucher-other@example.test", "Secure-2026!", email_verified_at=now,
        )
        self.private = User.objects.create_user(
            "voucher-private@example.test", "Secure-2026!", email_verified_at=now,
        )
        PrivateCustomerProfile.objects.create(
            user=self.private, customer_number="PV-TRIAL-1", street="Testweg",
            postal_code="57072", city="Siegen", country="DE",
        )
        self.company = Company.objects.create(
            name="Voucher Alpha GmbH", customer_number="V-ALPHA", email=self.admin.email,
            street="Testweg", postal_code="57072", city="Siegen", country="DE",
        )
        self.company2 = Company.objects.create(
            name="Voucher Beta GmbH", customer_number="V-BETA", email=self.other.email,
            street="Testweg", postal_code="57072", city="Siegen", country="DE",
        )
        Membership.objects.create(company=self.company, user=self.admin, role="admin")
        Membership.objects.create(company=self.company, user=self.member, role="member")
        Membership.objects.create(company=self.company2, user=self.other, role="admin")
        self.product = Product.objects.create(
            code="PRO", name="PROMPTFINISHER Pro",
            default_license_days=365, default_device_limit=2,
            reminder_1_days=60, reminder_2_days=30, critical_warning_days=7,
        )
        for type_ in ("new", "renewal"):
            ProductPrice.objects.create(
                product=self.product, price_type=type_, valid_from=now,
                gross_amount=Decimal("35.88"), currency="EUR",
            )
        for customer_type in ("company", "private"):
            TaxRule.objects.create(
                country="DE", customer_type=customer_type,
                tax_rate=Decimal("19.00"), active=True,
            )

    def make(self, *, kind="trial", bound_company=None, bound_user=None,
             count=1, max_redemptions=1, **values):
        options = {
            "title": "Voucher QA",
            "note": "synthetische Testaktion",
            "kind": kind,
            "product": self.product,
            "trial_days": 30 if kind == "trial" else 0,
            "percent_off": 25 if kind == "percent" else 0,
            "fixed_gross_off": Decimal("5.00") if kind == "fixed" else Decimal("0.00"),
            "max_redemptions": max_redemptions,
            "bound_company": bound_company,
            "bound_user": bound_user,
            "starts_at": self.now - timedelta(minutes=1),
            "expires_at": self.now + timedelta(days=10),
        }
        options.update(values)
        issued = issue_vouchers(actor=self.staff, count=count, **options)
        return issued[0] if count == 1 else issued

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["security_version"] = user.security_version
        session["authenticated_at"] = self.now.timestamp()
        session["last_activity_at"] = self.now.timestamp()
        session["two_factor_ok"] = True
        session.save()

    def test_code_entropy_and_no_plaintext_persistence(self):
        minted = self.make(count=5)
        codes = [code for _, code in minted]
        self.assertEqual(len(set(codes)), 5)
        for voucher, raw in minted:
            self.assertTrue(raw.startswith("PF-"))
            self.assertNotEqual(voucher.code_hash, raw)
            self.assertEqual(code_digest(raw), voucher.code_hash)
            self.assertNotIn(raw, str(voucher))
            self.assertNotIn(raw, voucher.note)

    def test_discount_price_and_tax_come_from_server_under_one_usage(self):
        voucher, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, quantity=2, voucher_code=raw)
        item = order.items.get()
        self.assertEqual(item.unit_gross, Decimal("26.91"))
        self.assertEqual(order.gross_total, Decimal("53.82"))
        self.assertEqual(item.unit_net * 2 + order.tax_total, order.gross_total)
        self.assertEqual(order.voucher_redemption.status, "reserved")
        self.assertEqual(order.voucher_redemption.discount_gross, Decimal("17.94"))
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)
        with self.assertRaises(ValidationError):
            create_order(user=self.admin, product=self.product, voucher_code=raw)
        with transaction.atomic():
            _activate_order(order, timezone.now())
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(License.objects.filter(company=self.company).count(), 2)
        redemption = VoucherRedemption.objects.get(order=order)
        self.assertEqual(redemption.status, "redeemed")
        with transaction.atomic():
            _activate_order(order, timezone.now())
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)

    def test_customer_bound_multiuse_campaign_respects_global_quota(self):
        voucher, raw = self.make(
            kind="percent", bound_company=self.company, max_redemptions=2
        )
        first = create_order(user=self.admin, product=self.product, voucher_code=raw)
        second = create_order(user=self.admin, product=self.product, voucher_code=raw)
        self.assertNotEqual(first.id, second.id)
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 2)
        with self.assertRaises(ValidationError):
            create_order(user=self.admin, product=self.product, voucher_code=raw)
        self.assertEqual(VoucherRedemption.objects.filter(voucher=voucher).count(), 2)

    def test_public_discount_code_allows_one_purchase_per_account(self):
        voucher, raw = self.make(kind="percent", max_redemptions=10)
        create_order(user=self.admin, product=self.product, voucher_code=raw)
        with self.assertRaisesMessage(ValidationError, "bereits genutzt"):
            create_order(user=self.admin, product=self.product, voucher_code=raw)
        self.assertEqual(voucher.redemptions.count(), 1)

    def test_fixed_gross_discount_per_seat_and_nonzero_floor(self):
        voucher, raw = self.make(kind="fixed", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, quantity=3, voucher_code=raw)
        self.assertEqual(order.gross_total, Decimal("92.64"))
        self.assertEqual(order.voucher_redemption.discount_gross, Decimal("15.00"))
        large, raw2 = self.make(kind="fixed", fixed_gross_off=Decimal("35.88"))
        with self.assertRaises(ValidationError):
            create_order(user=self.other, product=self.product, voucher_code=raw2)
        large.refresh_from_db()
        self.assertEqual(large.used_count, 0)

    def test_credits_can_never_cross_company_or_user_scope(self):
        voucher, code = self.make(kind="percent", bound_company=self.company)
        with self.assertRaises(ValidationError):
            create_order(user=self.other, product=self.product, voucher_code=code)
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 0)
        _, personal = self.make(kind="percent", bound_user=self.admin)
        with self.assertRaises(ValidationError):
            create_order(user=self.other, product=self.product, voucher_code=personal)

    def test_expired_and_disabled_codes_fail_without_consuming(self):
        disabled, code = self.make(kind="percent", active=False)
        with self.assertRaises(ValidationError):
            create_order(user=self.admin, product=self.product, voucher_code=code)
        expired, code2 = self.make(
            kind="percent", starts_at=self.now - timedelta(days=4),
            expires_at=self.now - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            create_order(user=self.admin, product=self.product, voucher_code=code2)
        disabled.refresh_from_db()
        expired.refresh_from_db()
        self.assertEqual(disabled.used_count, 0)
        self.assertEqual(expired.used_count, 0)

    def test_trial_private_grants_and_extension_without_mollie(self):
        _, code = self.make(bound_user=self.private)
        first = redeem_trial(code=code, actor=self.private, company=None)
        lic = first.license
        self.assertEqual(first.granted_days, 30)
        self.assertEqual(lic.status, "active")
        self.assertEqual(lic.owner_user, self.private)
        self.assertEqual(LicenseAssignment.objects.filter(license=lic, ended_at__isnull=True).count(), 1)
        self.assertEqual(first.order.gross_total, Decimal("0.00"))
        self.assertEqual(first.order.status, "paid")
        self.assertEqual(Payment.objects.count(), 0)
        with self.assertRaises(ValidationError):
            redeem_trial(code=code, actor=self.private, company=None)
        _, code2 = self.make(bound_user=self.private)
        next_one = redeem_trial(code=code2, actor=self.private, company=None)
        self.assertEqual(next_one.license_id, lic.pk)
        self.assertEqual(LicenseTerm.objects.filter(license=lic).count(), 2)
        lic.refresh_from_db()
        self.assertGreater(lic.valid_until, first.granted_until)

    def test_corporate_admin_controls_unassigned_and_targeted_seats(self):
        _, code = self.make(bound_company=self.company, max_redemptions=2)
        free_seat = redeem_trial(code=code, actor=self.admin, company=self.company)
        self.assertEqual(free_seat.license.status, "free")
        self.assertIsNone(free_seat.beneficiary)
        self.assertEqual(LicenseAssignment.objects.filter(license=free_seat.license).count(), 0)
        targeted = redeem_trial(code=code, actor=self.admin, company=self.company, beneficiary=self.member)
        self.assertEqual(targeted.license.status, "active")
        self.assertEqual(targeted.beneficiary, self.member)
        self.assertEqual(targeted.license.assignments.get(ended_at__isnull=True).user, self.member)
        with self.assertRaises(ValidationError):
            redeem_trial(code=code, actor=self.admin, company=self.company, beneficiary=self.member)
        with self.assertRaises(ValidationError):
            redeem_trial(code=code, actor=self.admin, company=self.company, beneficiary=self.other)

    def test_voucher_permissions_are_separate_from_license_permissions(self):
        from apps.accounts.models import Permission, Role, UserRole

        operator = User.objects.create_user(
            "voucher-licensing@example.test", "Secure-Test-2026!",
            is_staff=True, email_verified_at=self.now,
        )
        role = Role.objects.create(code="voucher-licensing", name="Licensing only")
        UserRole.objects.create(user=operator, role=role)
        perm, _ = Permission.objects.get_or_create(
            code="licenses.write", defaults={"name": "licenses.write"},
        )
        role.permissions.add(perm)
        self._login(operator)
        self.assertEqual(self.client.get("/ns-admin/vouchers/").status_code, 403)
        self.assertEqual(self.client.get("/ns-admin/vouchers/create/").status_code, 403)
        self.assertNotContains(
            self.client.get("/ns-admin/"), 'href="/ns-admin/vouchers/"'
        )
        read, _ = Permission.objects.get_or_create(
            code="vouchers.read", defaults={"name": "vouchers.read"},
        )
        role.permissions.add(read)
        self.assertEqual(self.client.get("/ns-admin/vouchers/").status_code, 200)
        self.assertEqual(self.client.get(
            f"/ns-admin/customers/{self.company.pk}/vouchers/"
        ).status_code, 403)
        self.assertEqual(self.client.get("/ns-admin/vouchers/create/").status_code, 403)
        write, _ = Permission.objects.get_or_create(
            code="vouchers.write", defaults={"name": "vouchers.write"},
        )
        role.permissions.add(write)
        self.assertEqual(self.client.get("/ns-admin/vouchers/create/").status_code, 200)

    def test_customer_voucher_tab_has_no_cross_company_leak(self):
        self.make(kind="trial", bound_company=self.company)
        self.make(kind="trial", bound_company=self.company2, title="SECRET OTHER COMPANY")
        self._login(self.staff)
        first = self.client.get(f"/ns-admin/customers/{self.company.pk}/vouchers/")
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, "Voucher QA")
        self.assertNotContains(first, "SECRET OTHER COMPANY")
        second = self.client.get(f"/ns-admin/customers/{self.company2.pk}/vouchers/")
        self.assertContains(second, "SECRET OTHER COMPANY")
        self.assertNotContains(second, "Voucher QA")

    def test_staff_and_portal_permissions_and_visibility(self):
        _, raw = self.make(kind="trial", bound_company=self.company)
        self._login(self.member)
        page = self.client.get("/portal/vouchers/")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, raw)
        self.assertEqual(self.client.post("/portal/vouchers/redeem/", {"voucher_code": raw}).status_code, 403)
        self._login(self.other)
        page2 = self.client.get("/portal/vouchers/")
        self.assertEqual(page2.status_code, 200)
        self.assertNotContains(page2, "Voucher QA")
        self._login(self.admin)
        self.assertEqual(self.client.get("/ns-admin/vouchers/").status_code, 403)
        self._login(self.staff)
        self.assertEqual(self.client.get("/ns-admin/vouchers/").status_code, 200)
        self.assertEqual(self.client.get("/portal/vouchers/").status_code, 403)

    def test_redemption_endpoint_is_csrf_scoped_and_post_only(self):
        _, raw = self.make(kind="trial", bound_company=self.company)
        self._login(self.admin)
        self.assertEqual(self.client.get("/portal/vouchers/redeem/").status_code, 405)
        response = self.client.post("/portal/vouchers/redeem/", {
            "voucher_code": raw, "target_user": str(self.member.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(VoucherRedemption.objects.filter(beneficiary=self.member, status="redeemed").count(), 1)

    def test_public_quote_is_read_only_and_rejects_scoped_codes(self):
        _, raw = self.make(kind="percent")
        self.client.logout()
        response = self.client.post("/api/v1/vouchers/quote/", {"voucher_code": raw, "quantity": 2})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["totalGrossCents"], 5382)
        self.assertEqual(data["discountGrossCents"], 1794)
        self.assertEqual(VoucherRedemption.objects.count(), 0)
        self.assertEqual(self.client.get("/api/v1/vouchers/quote/").status_code, 405)
        _, private_code = self.make(kind="percent", bound_company=self.company)
        self.assertEqual(self.client.post("/api/v1/vouchers/quote/", {
            "voucher_code": private_code, "quantity": 1,
        }).status_code, 400)

    def test_checkout_idempotency_rejects_changed_voucher_without_repricing(self):
        _, code_one = self.make(kind="percent", bound_company=self.company, max_redemptions=2)
        _, code_two = self.make(kind="percent", bound_company=self.company)
        token = "QA-VOUCHER-IDEMPOTENCY-20261114"
        first = create_order(
            user=self.admin, product=self.product, quantity=2,
            voucher_code=code_one, idempotency_key=token,
        )
        retried = create_order(
            user=self.admin, product=self.product, quantity=2,
            voucher_code=code_one, idempotency_key=token,
        )
        self.assertEqual(first.pk, retried.pk)
        self.assertEqual(first.gross_total, Decimal("53.82"))
        for changed_code in ("", code_two):
            with self.subTest(changed_code=bool(changed_code)):
                with self.assertRaises(ValidationError):
                    create_order(
                        user=self.admin, product=self.product, quantity=2,
                        voucher_code=changed_code, idempotency_key=token,
                    )
        first.refresh_from_db()
        self.assertEqual(first.gross_total, Decimal("53.82"))
        self.assertEqual(VoucherRedemption.objects.filter(order=first).count(), 1)

    def test_pending_renewal_cannot_reuse_another_voucher_price(self):
        license_obj = License.objects.create(
            company=self.company, product=self.product,
            status="free", valid_from=self.now - timedelta(days=1),
            valid_until=self.now + timedelta(days=40),
        )
        _, first_code = self.make(
            kind="percent", bound_company=self.company,
            allow_renewal=True,
        )
        _, second_code = self.make(
            kind="percent", bound_company=self.company,
            allow_renewal=True, percent_off=40,
        )
        first = create_order(
            user=self.admin, product=self.product, target_license=license_obj,
            voucher_code=first_code,
        )
        self.assertEqual(first.gross_total, Decimal("26.91"))
        with self.assertRaises(ValidationError):
            create_order(
                user=self.admin, product=self.product,
                target_license=license_obj, voucher_code=second_code,
            )
        with self.assertRaises(ValidationError):
            create_order(
                user=self.admin, product=self.product,
                target_license=license_obj, voucher_code="",
            )
        self.assertEqual(first.voucher_redemption.status, "reserved")
        self.assertEqual(VoucherRedemption.objects.filter(order=first).count(), 1)

    def test_voucher_reconciler_requires_provider_terminal_confirmation(self):
        from .tasks import reconcile_reserved_voucher_payments

        _, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, voucher_code=raw)
        Payment.objects.create(
            order=order, provider_payment_id="tr_voucher_terminal_qa",
            status="open", amount=order.gross_total, currency="EUR",
        )
        VoucherRedemption.objects.filter(order=order).update(
            created_at=self.now - timedelta(hours=2)
        )
        payment_details = {
            "id": "tr_voucher_terminal_qa",
            "status": "open",
            "amount": {"value": str(order.gross_total), "currency": "EUR"},
        }
        with patch("apps.vouchers.tasks.MollieClient") as provider:
            provider.return_value.get_payment.return_value = payment_details
            provider.return_value.list_chargebacks.return_value = {"_embedded": {"chargebacks": []}}
            pending = reconcile_reserved_voucher_payments()
        self.assertEqual(pending["scanned"], 1)
        order.refresh_from_db()
        self.assertEqual(order.voucher_redemption.status, "reserved")
        self.assertEqual(order.voucher_redemption.voucher.used_count, 1)

        payment_details["status"] = "expired"
        with patch("apps.vouchers.tasks.MollieClient") as provider:
            provider.return_value.get_payment.return_value = payment_details
            provider.return_value.list_chargebacks.return_value = {"_embedded": {"chargebacks": []}}
            closed = reconcile_reserved_voucher_payments()
        self.assertEqual(closed["errors"], 0)
        order.refresh_from_db()
        self.assertEqual(order.status, "failed")
        redemption = VoucherRedemption.objects.select_related("voucher").get(order=order)
        self.assertEqual(redemption.status, "cancelled")
        self.assertEqual(redemption.voucher.used_count, 0)
        with patch("apps.vouchers.tasks.MollieClient") as provider:
            self.assertEqual(reconcile_reserved_voucher_payments()["scanned"], 0)
            provider.assert_not_called()

    def test_voucher_reconciler_never_releases_quota_on_provider_error(self):
        from .tasks import reconcile_reserved_voucher_payments

        _, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, voucher_code=raw)
        Payment.objects.create(
            order=order, provider_payment_id="tr_voucher_error_qa",
            status="open", amount=order.gross_total, currency="EUR",
        )
        VoucherRedemption.objects.filter(order=order).update(
            created_at=self.now - timedelta(hours=2)
        )
        with patch("apps.vouchers.tasks.MollieClient") as provider, patch(
            "apps.vouchers.tasks.record_webhook_failure"
        ) as record_failure:
            provider.return_value.get_payment.side_effect = RuntimeError("provider unavailable")
            result = reconcile_reserved_voucher_payments()
        self.assertEqual(result, {"scanned": 1, "reconciled": 0, "errors": 1})
        record_failure.assert_called_once()
        record = VoucherRedemption.objects.select_related("voucher").get(order=order)
        self.assertEqual(record.status, "reserved")
        self.assertEqual(record.voucher.used_count, 1)

    def test_netstyle_customer_vouchers_include_redeemed_public_promotions(self):
        _, raw = self.make(
            kind="percent", title="Public Campaign Alpha Only",
            max_redemptions=3,
        )
        create_order(user=self.admin, product=self.product, voucher_code=raw)
        self._login(self.staff)
        first = self.client.get(f"/ns-admin/customers/{self.company.pk}/vouchers/")
        second = self.client.get(f"/ns-admin/customers/{self.company2.pk}/vouchers/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(first, "Public Campaign Alpha Only")
        self.assertNotContains(second, "Public Campaign Alpha Only")

    def test_customer_order_displays_real_voucher_savings(self):
        _, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, quantity=2, voucher_code=raw)
        self._login(self.admin)
        response = self.client.get("/portal/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.order_number)
        self.assertContains(response, "53,82")
        self.assertContains(response, "17,94")
        self.assertContains(response, "Gutschein")

    def test_existing_purchases_without_vouchers_remain_unchanged(self):
        order = create_order(user=self.admin, product=self.product, quantity=2)
        self.assertEqual(order.gross_total, Decimal("71.76"))
        self.assertEqual(order.tax_total, Decimal("11.46"))
        self.assertFalse(VoucherRedemption.objects.exists())

    def test_confirmed_failed_payment_releases_reserved_discount_quota(self):
        from .services import release_terminal_discount_reservation

        voucher, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, voucher_code=raw)
        payment = Payment.objects.create(
            order=order, provider_payment_id="tr_test_failed_voucher_1",
            status="failed", amount=order.gross_total, currency="EUR",
        )
        order.status = "failed"
        order.save(update_fields=["status", "updated_at"])
        self.assertTrue(release_terminal_discount_reservation(order))
        self.assertFalse(release_terminal_discount_reservation(order))
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 0)
        self.assertEqual(VoucherRedemption.objects.get(order=order).status, "cancelled")
        order2 = create_order(user=self.admin, product=self.product, voucher_code=raw)
        self.assertEqual(order2.voucher_redemption.status, "reserved")
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)

    def test_nonterminal_provider_status_does_not_release_quota(self):
        from .services import release_terminal_discount_reservation

        voucher, raw = self.make(kind="percent", bound_company=self.company)
        order = create_order(user=self.admin, product=self.product, voucher_code=raw)
        payment = Payment.objects.create(
            order=order, provider_payment_id="tr_test_pending_voucher_2",
            status="pending", amount=order.gross_total, currency="EUR",
        )
        order.status = "failed"
        order.save(update_fields=["status", "updated_at"])
        self.assertFalse(release_terminal_discount_reservation(order))
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)
        payment.status = "expired"
        payment.processed_paid = True
        payment.save(update_fields=["status", "processed_paid", "updated_at"])
        self.assertFalse(release_terminal_discount_reservation(order))
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)

    def test_csrf_protects_public_quote_and_authenticated_redemption(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post("/api/v1/vouchers/quote/", {
            "voucher_code": "PF-ABCD-EFGH-JKLM-NPQR-STUV",
            "quantity": 1,
        }).status_code, 403)
        strict.force_login(self.admin)
        strict_session = strict.session
        strict_session["security_version"] = self.admin.security_version
        strict_session["authenticated_at"] = self.now.timestamp()
        strict_session["last_activity_at"] = self.now.timestamp()
        strict_session["two_factor_ok"] = True
        strict_session.save()
        self.assertEqual(strict.post("/portal/vouchers/redeem/", {
            "voucher_code": "PF-ABCD-EFGH-JKLM-NPQR-STUV",
        }).status_code, 403)

    def test_trial_cannot_bypass_blocked_pro_licenses(self):
        existing = License.objects.create(
            owner_user=self.private, product=self.product,
            status="blocked", valid_from=self.now - timedelta(days=2),
            valid_until=self.now + timedelta(days=30),
        )
        _, code = self.make(bound_user=self.private)
        with self.assertRaisesMessage(ValidationError, "gesperrte"):
            redeem_trial(code=code, actor=self.private, company=None)
        self.assertEqual(License.objects.filter(owner_user=self.private).count(), 1)
        self.assertEqual(existing.status, "blocked")
        self.assertFalse(VoucherRedemption.objects.exists())

    def test_corporate_trial_cannot_bypass_payment_review(self):
        existing = License.objects.create(
            company=self.company, product=self.product, status="payment_review",
            valid_from=self.now - timedelta(days=2),
            valid_until=self.now + timedelta(days=30),
        )
        LicenseAssignment.objects.create(license=existing, user=self.member)
        _, code = self.make(bound_company=self.company)
        with self.assertRaisesMessage(ValidationError, "gesperrte"):
            redeem_trial(code=code, actor=self.admin, company=self.company, beneficiary=self.member)
        self.assertEqual(License.objects.filter(company=self.company).count(), 1)
        self.assertFalse(VoucherRedemption.objects.exists())

    def test_multiple_trial_seats_never_grant_to_other_tenants(self):
        _, raw = self.make(bound_company=self.company)
        with self.assertRaises(ValidationError):
            redeem_trial(code=raw, actor=self.other, company=self.company2)
        self.assertEqual(License.objects.count(), 0)


class VoucherTransactionBoundaryTests(TransactionTestCase):
    """Exercise real PostgreSQL FOR UPDATE outside Django TestCase wrapping."""

    def test_direct_order_service_call_without_outer_transaction_is_atomic(self):
        now = timezone.now()
        self.assertFalse(transaction.get_connection().in_atomic_block)
        staff = User.objects.create_user(
            "voucher-tx-staff@example.test", "Secure-2026!",
            is_staff=True, email_verified_at=now,
        )
        buyer = User.objects.create_user(
            "voucher-tx-buyer@example.test", "Secure-2026!",
            email_verified_at=now,
        )
        PrivateCustomerProfile.objects.create(
            user=buyer, customer_number="PV-TRIAL-TX-1", street="Testweg",
            postal_code="57072", city="Siegen", country="DE",
        )
        product = Product.objects.create(
            code="PRO", name="PROMPTFINISHER Pro",
            default_license_days=365, default_device_limit=2,
            reminder_1_days=60, reminder_2_days=30, critical_warning_days=7,
        )
        ProductPrice.objects.create(
            product=product, price_type="new", gross_amount=Decimal("35.88"),
            currency="EUR", valid_from=now,
        )
        TaxRule.objects.create(
            country="DE", customer_type="private", tax_rate=Decimal("19.00"),
            active=True,
        )
        (voucher, raw), = issue_vouchers(
            actor=staff, count=1, title="Transaction safety voucher",
            kind="percent", product=product, percent_off=25,
            max_redemptions=1, starts_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=1),
        )
        order = create_order(user=buyer, product=product, voucher_code=raw)
        self.assertFalse(transaction.get_connection().in_atomic_block)
        self.assertEqual(order.gross_total, Decimal("26.91"))
        self.assertEqual(order.voucher_redemption.status, "reserved")
        voucher.refresh_from_db()
        self.assertEqual(voucher.used_count, 1)
