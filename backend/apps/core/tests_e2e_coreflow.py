from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlsplit
from unittest.mock import patch

import pyotp
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole
from apps.audit.models import AuditEvent
from apps.catalog.models import Product
from apps.catalog.services import current_price
from apps.companies.models import Membership
from apps.companies.services import create_invitation
from apps.core.security import token_pair
from apps.devices.services import register_device, validate_device_token
from apps.integrations.models import ServiceAccount
from apps.legal.models import LegalDocument
from apps.licenses.models import License, LicenseReminder, LicenseTerm
from apps.licenses.services import assign_license
from apps.notifications.models import EmailMessage
from apps.notifications.services import _render_context
from apps.notifications.tasks import schedule_license_reminders, sync_license_states
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.payments.services import create_refund_request, process_provider_state, submit_refund
from apps.proaccess.services import active_product_assignment


class CommercialCoreFlowE2ETests(TestCase):
    """One integrated contract for all 22 PM-TEST-007 lifecycle steps."""

    admin_email = 'e2e-admin@example.test'
    member_email = 'e2e-member@example.test'
    password = 'E2E-Core-Flow-Password-42!'

    def setUp(self):
        call_command('seed_defaults', verbosity=0)
        self.now = timezone.now()
        self.product = Product.objects.get(code='PRO')
        for doc_type in ('terms', 'privacy'):
            LegalDocument.objects.create(
                doc_type=doc_type,
                version='e2e-v1',
                content=f'E2E {doc_type}',
                valid_from=self.now - timedelta(days=1),
                active=True,
            )

    def _register_verify_and_enable_2fa(self):
        # 1: register the company through the real HTTP registration view.
        response = self.client.post(
            '/auth/register/',
            {
                'customer_type': 'company',
                'first_name': 'Ada',
                'last_name': 'Admin',
                'email': self.admin_email,
                'password': self.password,
                'company_name': 'E2E Muster GmbH',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('/auth/2fa/setup/'))

        admin = User.objects.get(email=self.admin_email)
        membership = Membership.objects.select_related('company').get(
            user=admin,
            role='admin',
            active=True,
        )
        company = membership.company
        self.assertEqual(company.name, 'E2E Muster GmbH')
        self.assertEqual(company.status, 'active')
        self.assertTrue(admin.two_factor_required)
        self.assertIsNone(admin.email_verified_at)

        # 2: follow the actual verification URL through the same renderer used
        # for provider delivery. Sensitive URLs are encrypted in persisted
        # EmailMessage.context and must never be read as plaintext at rest.
        verification = EmailMessage.objects.filter(
            template__code='verify_email',
            recipient=self.admin_email,
        ).latest('created_at')
        verify_url = _render_context(verification.context)['url']
        verify_path = urlsplit(verify_url).path
        verify_response = self.client.get(verify_path)
        self.assertEqual(verify_response.status_code, 200)
        admin.refresh_from_db()
        self.assertIsNotNone(admin.email_verified_at)

        # 3: set up TOTP through the real 2FA setup view.
        setup = self.client.get('/auth/2fa/setup/')
        self.assertEqual(setup.status_code, 200)
        secret = setup.context['secret']
        code = pyotp.TOTP(secret).now()
        complete = self.client.post('/auth/2fa/setup/', {'code': code})
        self.assertEqual(complete.status_code, 200)
        admin.refresh_from_db()
        self.assertTrue(admin.two_factor_required)
        self.assertTrue(admin.totp_secret_enc)
        session = self.client.session
        self.assertTrue(session.get('two_factor_ok'))
        self.assertEqual(int(session['security_version']), int(admin.security_version))
        return admin, company

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

    @staticmethod
    def _paid_payload(payment, *, paid_at=None, status='paid'):
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
        self.admin, self.company = self._register_verify_and_enable_2fa()

        # 4-6: purchase five seats and process canonical Mollie paid state.
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
            term = license_obj.terms.get()
            self.assertEqual(term.valid_until - term.valid_from, timedelta(days=365))
        process_provider_state(
            payment.provider_payment_id,
            self._paid_payload(payment, paid_at=paid_at),
        )
        self.assertEqual(
            License.objects.filter(company=self.company, product=self.product).count(),
            5,
        )

        # 7-8: invite a new member and accept through the actual invite route.
        invitation, raw_token = create_invitation(
            company=self.company,
            actor=self.admin,
            email=self.member_email,
            first_name='Mara',
            last_name='Member',
        )
        self.client.post('/auth/logout/')
        response = self.client.post(
            f'/auth/invite/{raw_token}/',
            {
                'first_name': 'Mara',
                'last_name': 'Member',
                'password': self.password,
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('/portal/dashboard/'))
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.member = User.objects.get(email=self.member_email)
        self.assertIsNotNone(self.member.email_verified_at)
        self.assertTrue(
            Membership.objects.filter(
                company=self.company,
                user=self.member,
                role='member',
                active=True,
            ).exists()
        )

        # 9: assign a free seat to the invited member.
        assigned_license = licenses[0]
        assignment = assign_license(assigned_license, self.member, self.admin)
        assigned_license.refresh_from_db()
        self.assertEqual(assigned_license.status, 'active')
        self.assertEqual(assignment.user_id, self.member.id)

        # 10-12: two devices work; the third is rejected.
        device_one, token_one = register_device(
            self.member, assigned_license, 'Notebook', 'Windows', 'Edge'
        )
        register_device(
            self.member, assigned_license, 'Desktop', 'Windows', 'Edge'
        )
        with self.assertRaises(ValidationError):
            register_device(
                self.member, assigned_license, 'Drittes Gerät', 'Windows', 'Edge'
            )

        # 13: entitlement + live assignment + device token unlock Pro.
        self.assertIsNotNone(active_product_assignment(self.member))
        validated = validate_device_token(self.member, token_one, touch=False)
        self.assertIsNotNone(validated)
        self.assertEqual(validated.pk, device_one.pk)

        # 14-15: T-60 and T-30 each queue one logical reminder for both
        # member and mandatory company admin; repeated scheduling is idempotent.
        t60_end = self._set_term_end_date(assigned_license, 60)
        schedule_license_reminders.run()
        t60 = LicenseReminder.objects.get(
            license=assigned_license,
            kind='t60',
            target_valid_until=t60_end,
        )
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t60.id)).count(), 2
        )
        schedule_license_reminders.run()
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t60.id)).count(), 2
        )

        t30_end = self._set_term_end_date(assigned_license, 30)
        schedule_license_reminders.run()
        t30 = LicenseReminder.objects.get(
            license=assigned_license,
            kind='t30',
            target_valid_until=t30_end,
        )
        self.assertEqual(
            EmailMessage.objects.filter(context__reminder_id=str(t30.id)).count(), 2
        )

        # 16: simulate expiry while preserving the database validity constraint.
        expired_at = timezone.now() - timedelta(seconds=1)
        historical_start = expired_at - timedelta(days=365)
        assigned_license.valid_from = historical_start
        assigned_license.valid_until = expired_at
        assigned_license.save(
            update_fields=['valid_from', 'valid_until', 'updated_at']
        )
        LicenseTerm.objects.filter(
            license=assigned_license,
            status='active',
        ).update(valid_from=historical_start, valid_until=expired_at)
        sync_license_states.run()
        assigned_license.refresh_from_db()
        self.assertEqual(assigned_license.status, 'expired')
        self.assertIsNone(active_product_assignment(self.member))
        self.assertIsNone(validate_device_token(self.member, token_one, touch=False))

        # 17: renewal of an expired seat starts a new exact 365-day term and
        # does not create a sixth license record.
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
            License.objects.filter(company=self.company, product=self.product).count(), 5
        )
        renewal_term = assigned_license.terms.filter(status='active').order_by(
            '-valid_until'
        ).first()
        self.assertIsNotNone(renewal_term)
        self.assertEqual(renewal_term.valid_from, renewal_payment.paid_at)
        self.assertEqual(
            renewal_term.valid_until - renewal_term.valid_from,
            timedelta(days=365),
        )
        self.assertEqual(assigned_license.status, 'active')
        self.assertIsNotNone(active_product_assignment(self.member))
        self.assertIsNotNone(validate_device_token(self.member, token_one, touch=False))

        # 18: refund latest paid term through production refund logic; only the
        # network edge to Mollie is mocked.
        refund = create_refund_request(
            term=renewal_term,
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

        # 19: chargeback on the original purchase moves affected paid licenses
        # into payment review.
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

        # 20: the complete chain leaves auditable business/security evidence.
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

        # 21: a real netstyle Operations role can open the Ops dashboard. Only
        # external infrastructure probes are isolated; RBAC, session security,
        # rendering and database access remain the production code path.
        ops_user = User.objects.create_user(
            'e2e-ops@example.test',
            self.password,
            first_name='E2E',
            last_name='Operations',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='e2e-configured-secret',
        )
        UserRole.objects.create(user=ops_user, role=Role.objects.get(code='ops'))
        self.client.force_login(ops_user)
        session = self.client.session
        session['security_version'] = ops_user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()
        with (
            patch('apps.core.admin_views.snapshot', return_value={'disk_percent': 10.0}),
            patch('apps.core.admin_views.caddy_health', return_value=True),
            patch('apps.core.admin_views.certificate_status', return_value={'status': 'ok'}),
            patch('apps.ops.api._database_payload', return_value={'status': 'ok'}),
            patch('apps.ops.api._service_payload', return_value={'django': True}),
            patch('apps.ops.api._integration_payload', return_value={'mollie': {'configured': True}}),
        ):
            ops_response = self.client.get('/ns-admin/ops/')
        self.assertEqual(ops_response.status_code, 200)
        self.assertEqual(ops_response.context['environment'], settings.ENVIRONMENT)

        # 22: the maintenance snapshot is protected by a real hash-only
        # ServiceAccount credential carrying exactly the ops.read scope.
        raw_service_token, hashed_service_token = token_pair()
        service_account = ServiceAccount.objects.create(
            name='E2E Maintenance Reader',
            token_hash=hashed_service_token,
            scopes=['ops.read'],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        with (
            patch('apps.ops.api.snapshot', return_value={'disk_percent': 10.0}),
            patch('apps.ops.api._database_payload', return_value={'status': 'ok'}),
            patch('apps.ops.api._backup_payload', return_value={'status': 'ok'}),
            patch('apps.ops.api._restore_payload', return_value={'status': 'ok'}),
            patch('apps.ops.api._service_payload', return_value={'django': True}),
            patch('apps.ops.api._integration_payload', return_value={'mollie': {'configured': True}}),
        ):
            snapshot_response = self.client.get(
                '/api/v1/ops/maintenance-snapshot',
                HTTP_AUTHORIZATION=f'Bearer {raw_service_token}',
            )
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response['Cache-Control'], 'no-store')
        snapshot_payload = snapshot_response.json()
        self.assertEqual(snapshot_payload['schema_version'], 1)
        self.assertEqual(snapshot_payload['service_account'], str(service_account.id))
        self.assertEqual(snapshot_payload['database']['status'], 'ok')
        service_account.refresh_from_db()
        self.assertIsNotNone(service_account.last_used_at)
