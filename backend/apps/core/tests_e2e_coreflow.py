from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog.models import Product
from apps.catalog.services import current_price
from apps.companies.models import Company, Membership
from apps.companies.services import create_invitation
from apps.core.crypto import encrypt
from apps.devices.services import register_device, validate_device_token
from apps.licenses.models import License, LicenseReminder, LicenseTerm
from apps.licenses.services import assign_license
from apps.notifications.models import EmailMessage
from apps.notifications.tasks import schedule_license_reminders, sync_license_states
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.payments.services import create_refund_request, process_provider_state, submit_refund
from apps.proaccess.services import active_product_assignment


class CommercialCoreFlowE2ETests(TestCase):
    """Single contract for the PM-TEST-007 commercial lifecycle.

    Dedicated auth/browser tests validate the registration forms, e-mail token,
    CSRF and TOTP UI in depth. This contract starts from the completed
    registration/verification/2FA state and then keeps every commercial state
    transition in one chain so incompatible service changes cannot pass in
    isolation.
    """

    password = 'E2E-Core-Flow-Password-42!'

    def setUp(self):
        call_command('seed_defaults', verbosity=0)
        self.now = timezone.now()
        self.product = Product.objects.get(code='PRO')
        self.company = Company.objects.create(
            customer_number='E2E-COMPANY-001',
            name='E2E Muster GmbH',
            email='e2e-company@example.test',
            country='DE',
            status='active',
        )
        self.admin = User.objects.create_user(
            'e2e-admin@example.test',
            self.password,
            first_name='Ada',
            last_name='Admin',
            email_verified_at=self.now,
            two_factor_required=True,
            totp_secret_enc=encrypt('JBSWY3DPEHPK3PXP'),
        )
        Membership.objects.create(
            company=self.company,
            user=self.admin,
            role='admin',
            active=True,
        )
        self.member = User.objects.create_user(
            'e2e-member@example.test',
            self.password,
            first_name='Mara',
            last_name='Member',
            email_verified_at=self.now,
        )

    def _order(self, *, number, quantity, price_type, target_license=None):
        price = current_price(self.product, price_type, timezone.now())
        self.assertIsNotNone(price)
        gross = price.gross_amount * quantity
        order = Order.objects.create(
            order_number=number,
            company=self.company,
            status='payment_open',
            currency=price.currency,
            gross_total=gross,
            tax_total=(gross - (gross / Decimal('1.19'))).quantize(Decimal('0.01')),
            billing_snapshot={'company': self.company.name},
            idempotency_key=f'e2e:{number}',
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            price_version=price,
            quantity=quantity,
            unit_gross=price.gross_amount,
            unit_net=(price.gross_amount / Decimal('1.19')).quantize(Decimal('0.01')),
            tax_rate=Decimal('19.00'),
            product_name_snapshot=self.product.name,
            target_license=target_license,
        )
        payment = Payment.objects.create(
            order=order,
            provider='mollie',
            provider_payment_id=f'tr_{number.lower().replace("-", "_")}',
            status='open',
            amount=gross,
            currency=price.currency,
        )
        return order, payment

    def _paid_payload(self, payment, *, paid_at=None, status='paid'):
        paid_at = paid_at or timezone.now()
        return {
            'id': payment.provider_payment_id,
            'status': status,
            'amount': {
                'value': f'{payment.amount:.2f}',
                'currency': payment.currency,
            },
            'method': 'banktransfer',
            'paidAt': paid_at.isoformat(),
        }

    def _set_term_end_date(self, license_obj, days):
        target_date = timezone.localdate() + timedelta(days=days)
        target = timezone.make_aware(
            datetime.combine(target_date, time(hour=12)),
            timezone.get_current_timezone(),
        )
        license_obj.valid_until = target
        license_obj.save(update_fields=['valid_until', 'updated_at'])
        LicenseTerm.objects.filter(
            license=license_obj,
            status='active',
        ).update(valid_until=target)
        return target

    def test_complete_commercial_core_flow(self):
        # 1-3: company exists; admin identity is verified and 2FA-enforced.
        self.assertEqual(self.company.status, 'active')
        self.assertIsNotNone(self.admin.email_verified_at)
        self.assertTrue(self.admin.two_factor_required)
        self.assertTrue(self.admin.totp_secret_enc)

        # 4-6: buy five seats and confirm the canonical Mollie paid state.
        order, payment = self._order(
            number='E2E-NEW-001',
            quantity=5,
            price_type='new',
        )
        paid_at = timezone.now()
        process_provider_state(
            payment.provider_payment_id,
            self._paid_payload(payment, paid_at=paid_at),
        )
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, 'paid')
        self.assertEqual(payment.status, 'paid')
        licenses = list(
            License.objects.filter(company=self.company, product=self.product)
            .order_by('created_at', 'id')
        )
        self.assertEqual(len(licenses), 5)
        for license_obj in licenses:
            self.assertEqual(license_obj.status, 'free')
            self.assertEqual(
                license_obj.valid_until - license_obj.valid_from,
                timedelta(days=365),
            )
        # A duplicate provider notification must not create another five seats.
        process_provider_state(
            payment.provider_payment_id,
            self._paid_payload(payment, paid_at=paid_at),
        )
        self.assertEqual(
            License.objects.filter(company=self.company, product=self.product).count(),
            5,
        )

        # 7-8: invite an existing verified identity and accept over the real URL.
        invitation, raw_token = create_invitation(
            company=self.company,
            actor=self.admin,
            email=self.member.email,
            first_name=self.member.first_name,
            last_name=self.member.last_name,
        )
        self.client.force_login(self.member)
        session = self.client.session
        session['security_version'] = self.member.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()
        response = self.client.post(f'/auth/invite/{raw_token}/')
        self.assertEqual(response.status_code, 200)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(
            Membership.objects.filter(
                company=self.company,
                user=self.member,
                role='member',
                active=True,
            ).exists()
        )

        # 9: assign one of the free seats to the invited member.
        assigned_license = licenses[0]
        assignment = assign_license(assigned_license, self.member, self.admin)
        assigned_license.refresh_from_db()
        self.assertEqual(assigned_license.status, 'active')
        self.assertEqual(assignment.user_id, self.member.id)

        # 10-12: exactly two devices are allowed; the third is rejected.
        device_one, token_one = register_device(
            self.member,
            assigned_license,
            'Notebook',
            'Windows',
            'Edge',
        )
        _device_two, _token_two = register_device(
            self.member,
            assigned_license,
            'Desktop',
            'Windows',
            'Edge',
        )
        with self.assertRaises(ValidationError):
            register_device(
                self.member,
                assigned_license,
                'Drittes Gerät',
                'Windows',
                'Edge',
            )

        # 13: entitlement + live assignment + device token unlock Pro.
        self.assertIsNotNone(active_product_assignment(self.member))
        validated = validate_device_token(self.member, token_one, touch=False)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.pk, device_one.pk)

        # 14-15: T-60 and T-30 reminders each create one logical reminder and
        # mail rows for the assigned member plus mandatory company admin.
        t60_end = self._set_term_end_date(assigned_license, 60)
        schedule_license_reminders.run()
        t60 = LicenseReminder.objects.get(
            license=assigned_license,
            kind='t60',
            target_valid_until=t60_end,
        )
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t60.id)).count(),
            2,
        )
        # Re-running the scheduler is idempotent for the same target date.
        schedule_license_reminders.run()
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t60.id)).count(),
            2,
        )

        t30_end = self._set_term_end_date(assigned_license, 30)
        schedule_license_reminders.run()
        t30 = LicenseReminder.objects.get(
            license=assigned_license,
            kind='t30',
            target_valid_until=t30_end,
        )
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t30.id)).count(),
            2,
        )

        # 16: term expiry removes effective Pro access.
        expired_at = timezone.now() - timedelta(seconds=1)
        assigned_license.valid_until = expired_at
        assigned_license.save(update_fields=['valid_until', 'updated_at'])
        LicenseTerm.objects.filter(
            license=assigned_license,
            status='active',
        ).update(valid_until=expired_at)
        sync_license_states.run()
        assigned_license.refresh_from_db()
        self.assertEqual(assigned_license.status, 'expired')
        self.assertIsNone(active_product_assignment(self.member))
        self.assertIsNone(validate_device_token(self.member, token_one, touch=False))

        # 17: paying a renewal restarts an expired seat at payment time and
        # restores access without creating a sixth license record.
        renewal_order, renewal_payment = self._order(
            number='E2E-RENEW-001',
            quantity=1,
            price_type='renewal',
            target_license=assigned_license,
        )
        renewal_paid_at = timezone.now()
        process_provider_state(
            renewal_payment.provider_payment_id,
            self._paid_payload(renewal_payment, paid_at=renewal_paid_at),
        )
        assigned_license.refresh_from_db()
        renewal_payment.refresh_from_db()
        self.assertEqual(renewal_order.items.count(), 1)
        self.assertEqual(renewal_payment.status, 'paid')
        self.assertEqual(
            License.objects.filter(company=self.company, product=self.product).count(),
            5,
        )
        self.assertEqual(assigned_license.status, 'active')
        self.assertEqual(
            assigned_license.valid_until - renewal_paid_at,
            timedelta(days=365),
        )
        self.assertIsNotNone(active_product_assignment(self.member))
        self.assertIsNotNone(validate_device_token(self.member, token_one, touch=False))

        # 18: refund the latest paid term through the production refund path.
        latest_term = assigned_license.terms.filter(status='active').order_by('-valid_until').first()
        refund = create_refund_request(
            term=latest_term,
            actor=self.admin,
            reason='E2E Vertragsbeendigung',
        )
        with patch(
            'apps.payments.services.MollieClient.create_refund',
            return_value={'id': 're_e2e_core_flow', 'status': 'refunded'},
        ):
            submit_refund(refund)
        refund.refresh_from_db()
        assigned_license.refresh_from_db()
        self.assertEqual(refund.status, 'succeeded')
        self.assertIsNone(active_product_assignment(self.member))
        self.assertIsNone(validate_device_token(self.member, token_one, touch=False))

        # 19: a chargeback on the original five-seat payment puts affected
        # paid licenses into payment review.
        chargeback_payload = self._paid_payload(payment, status='charged_back')
        chargeback_payload.pop('paidAt', None)
        process_provider_state(payment.provider_payment_id, chargeback_payload)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'chargeback')
        self.assertTrue(
            License.objects.filter(
                company=self.company,
                product=self.product,
                status='payment_review',
            ).exists()
        )

        # 20: the chain must leave auditable security/business evidence.
        required_actions = {
            'invitation.created',
            'license.assigned',
            'device.registered',
            'refund.created',
            'refund.succeeded',
            'license.chargeback_review',
        }
        actual_actions = set(AuditEvent.objects.values_list('action', flat=True))
        self.assertTrue(required_actions.issubset(actual_actions))
