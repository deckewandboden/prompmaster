from __future__ import annotations

import io
from datetime import timedelta
from urllib.parse import urlsplit
from unittest.mock import patch

import pyotp
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole
from apps.catalog.models import Feature, Product, ProductPrice
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.core.crypto import encrypt
from apps.core.settings_store import get_setting
from apps.core.sensitive import SENSITIVE_REAUTH_SESSION_KEY
from apps.integrations.models import ServiceAccount
from apps.legal.models import DeletionRequest, LegalDocument, RetentionPolicy
from apps.licenses.models import License, LicenseAssignment, LicenseTerm
from apps.notifications.models import EmailMessage, EmailTemplate
from apps.notifications.services import _render_context
from apps.payments.models import Payment, Refund
from apps.support.models import SupportRequest


@override_settings(ENVIRONMENT='staging')
class RegistrationPurchaseReleaseAcceptanceTests(TestCase):
    password = 'Release-Acceptance-Password-2026!'

    def setUp(self):
        call_command('seed_defaults', verbosity=0, stdout=io.StringIO())
        now = timezone.now() - timedelta(minutes=1)
        for kind in ('terms', 'privacy', 'withdrawal', 'license'):
            LegalDocument.objects.create(
                doc_type=kind,
                version=f'release-{kind}',
                content=f'Release acceptance {kind}',
                valid_from=now,
                active=True,
            )

    def verify_email(self, email):
        message = EmailMessage.objects.filter(
            template__code='verify_email', recipient=email,
        ).latest('created_at')
        path = urlsplit(_render_context(message.context)['url']).path
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email=email)
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)
        return user

    def webhook(self, payment, status):
        payload = {
            'id': payment.provider_payment_id,
            'status': status,
            'amount': {'value': f'{payment.amount:.2f}', 'currency': payment.currency},
            'method': 'banktransfer',
        }
        if status == 'paid':
            payload['paidAt'] = timezone.now().isoformat()
        with (
            patch('apps.payments.views.MollieClient.get_payment', return_value=payload),
            patch(
                'apps.payments.views.MollieClient.list_chargebacks',
                return_value={'_embedded': {'chargebacks': []}},
            ),
        ):
            response = self.client.post('/api/webhooks/mollie/', {'id': payment.provider_payment_id})
        self.assertEqual(response.status_code, 200)

    @patch('apps.companies.portal.MollieClient.create_payment')
    def test_private_registration_to_paid_license(self, create_payment):
        email = 'release-private@example.test'
        response = self.client.post(
            '/auth/register/',
            {
                'next': '/portal/licenses/buy/?quantity=1',
                'customer_type': 'private',
                'first_name': 'Private',
                'last_name': 'Release',
                'email': email,
                'password': self.password,
                'company_name': '',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
            HTTP_X_FORWARDED_FOR='198.18.20.1',
        )
        self.assertEqual(response.status_code, 302)
        user = self.verify_email(email)
        create_payment.return_value = {
            'id': 'tr_release_private_paid',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/private'}},
        }
        response = self.client.post(
            '/portal/licenses/buy/?quantity=1',
            {
                'quantity': '1',
                'accept_terms': 'on',
                'accept_privacy': 'on',
                'accept_withdrawal': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.example.test/private')
        payment = Payment.objects.get(provider_payment_id='tr_release_private_paid')
        self.webhook(payment, 'paid')
        payment.refresh_from_db()
        payment.order.refresh_from_db()
        self.assertEqual((payment.status, payment.order.status), ('paid', 'paid'))
        license_obj = License.objects.get(owner_user=user)
        self.assertEqual(license_obj.status, 'active')
        self.assertTrue(
            LicenseAssignment.objects.filter(
                license=license_obj, user=user, ended_at__isnull=True,
            ).exists()
        )

    @patch('apps.companies.portal.MollieClient.create_payment')
    def test_company_registration_mfa_to_paid_seats(self, create_payment):
        email = 'release-company@example.test'
        response = self.client.post(
            '/auth/register/',
            {
                'next': '/portal/licenses/buy/?quantity=2',
                'customer_type': 'company',
                'first_name': 'Company',
                'last_name': 'Release',
                'email': email,
                'password': self.password,
                'company_name': 'Release Acceptance GmbH',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
            HTTP_X_FORWARDED_FOR='198.18.20.2',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/auth/2fa/setup/')
        user = self.verify_email(email)
        setup = self.client.get('/auth/2fa/setup/')
        self.assertEqual(setup.status_code, 200)
        complete = self.client.post(
            '/auth/2fa/setup/',
            {'code': pyotp.TOTP(setup.context['secret']).now()},
        )
        self.assertEqual(complete.status_code, 200)
        company = Membership.objects.get(user=user, role='admin', active=True).company
        create_payment.return_value = {
            'id': 'tr_release_company_paid',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/company'}},
        }
        response = self.client.post(
            '/portal/licenses/buy/?quantity=2',
            {'quantity': '2', 'accept_terms': 'on', 'accept_privacy': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(provider_payment_id='tr_release_company_paid')
        self.webhook(payment, 'paid')
        self.assertEqual(
            License.objects.filter(company=company, product__code='PRO', status='free').count(),
            2,
        )

    @patch('apps.companies.portal.MollieClient.create_payment')
    def test_cancelled_checkout_creates_no_license(self, create_payment):
        email = 'release-cancel@example.test'
        self.client.post(
            '/auth/register/',
            {
                'customer_type': 'private',
                'first_name': 'Cancel',
                'last_name': 'Release',
                'email': email,
                'password': self.password,
                'company_name': '',
                'accept_terms': 'on',
                'accept_privacy': 'on',
            },
            HTTP_X_FORWARDED_FOR='198.18.20.3',
        )
        user = self.verify_email(email)
        create_payment.return_value = {
            'id': 'tr_release_cancelled',
            'status': 'open',
            '_links': {'checkout': {'href': 'https://checkout.example.test/cancel'}},
        }
        response = self.client.post(
            '/portal/licenses/buy/',
            {
                'quantity': '1',
                'accept_terms': 'on',
                'accept_privacy': 'on',
                'accept_withdrawal': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(provider_payment_id='tr_release_cancelled')
        self.webhook(payment, 'canceled')
        payment.refresh_from_db()
        payment.order.refresh_from_db()
        self.assertEqual((payment.status, payment.order.status), ('canceled', 'canceled'))
        self.assertFalse(License.objects.filter(owner_user=user).exists())


@override_settings(ENVIRONMENT='staging')
class NetstyleMutationReleaseAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', stdout=io.StringIO(), verbosity=0)

    def setUp(self):
        self.admin = User.objects.get(email='demo.superadmin1@promptmaster.invalid')
        self.client.force_login(self.admin)
        if not self.admin.totp_secret_enc:
            from apps.accounts.totp import new_secret
            self.admin.totp_secret_enc = encrypt(new_secret())
            self.admin.save(update_fields=['totp_secret_enc', 'updated_at'])
        session = self.client.session
        session['security_version'] = self.admin.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session[SENSITIVE_REAUTH_SESSION_KEY] = timezone.now().timestamp()
        session.save()

    def test_product_price_settings_and_mollie_mutations(self):
        response = self.client.post(
            '/ns-admin/products/features/new/',
            {'code': 'RELEASE_AUDIT', 'name': 'Release Audit Feature'},
        )
        self.assertEqual(response.status_code, 302)
        feature = Feature.objects.get(code='RELEASE_AUDIT')
        response = self.client.post(
            '/ns-admin/products/new/',
            {
                'code': 'RELEASE-AUDIT',
                'name': 'Release Audit Product',
                'description': 'Release acceptance fixture',
                'active': 'on',
                'visible': 'on',
                'purchasable': 'on',
                'default_license_days': '365',
                'default_device_limit': '2',
                'reminder_1_days': '60',
                'reminder_2_days': '30',
                'critical_warning_days': '7',
                'features': [str(feature.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(code='RELEASE-AUDIT')
        response = self.client.post(
            f'/ns-admin/products/{product.pk}/prices/new/',
            {
                'price_type': 'new',
                'gross_amount': '12.34',
                'currency': 'eur',
                'valid_from': timezone.now().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ProductPrice.objects.filter(
                product=product, price_type='new', gross_amount='12.34', currency='EUR',
            ).exists()
        )
        response = self.client.post(
            '/ns-admin/settings/',
            {
                'support_email': 'release-support@example.test',
                'disk_warning': '81',
                'disk_critical': '91',
                'ram_warning': '82',
                'ram_critical': '92',
                'cpu_warning': '83',
                'backup_warning_hours': '9',
                'backup_critical_hours': '25',
                'restore_warning_days': '36',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_setting('support_email'), 'release-support@example.test')
        response = self.client.post(
            '/ns-admin/mollie/config/',
            {'profile_id': 'pfl_release_acceptance', 'api_key': ''},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_setting('mollie_profile_id'), 'pfl_release_acceptance')

    def test_service_account_create_rotate_revoke(self):
        response = self.client.post(
            '/ns-admin/api/service-accounts/new/',
            {'name': 'Release Acceptance API', 'scopes': ['ops.read', 'prompt.read']},
        )
        self.assertEqual(response.status_code, 200)
        account = ServiceAccount.objects.get(name='Release Acceptance API')
        original_hash = account.token_hash
        response = self.client.post(f'/ns-admin/api/service-accounts/{account.pk}/rotate/')
        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertNotEqual(account.token_hash, original_hash)
        rotated_hash = account.token_hash
        response = self.client.post(f'/ns-admin/api/service-accounts/{account.pk}/revoke/')
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertFalse(account.active)
        response = self.client.post(f'/ns-admin/api/service-accounts/{account.pk}/rotate/')
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.token_hash, rotated_hash)

    def test_legal_privacy_support_and_email_mutations(self):
        old_active = LegalDocument.objects.get(doc_type='license', active=True)
        response = self.client.post(
            '/ns-admin/legal/documents/new/',
            {
                'doc_type': 'license',
                'version': 'release-acceptance-v2',
                'content': 'Release acceptance legal document',
                'valid_from': timezone.now().isoformat(),
                'active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        old_active.refresh_from_db()
        self.assertFalse(old_active.active)
        response = self.client.post(
            '/ns-admin/legal/retention/new/',
            {'data_class': 'expired_sessions', 'retain_days': '45', 'active': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            RetentionPolicy.objects.filter(
                data_class='expired_sessions', retain_days=45, active=True,
            ).exists()
        )
        reject_user = User.objects.create_user(
            'release-reject@example.test', 'Delete-Reject-Password-2026!'
        )
        reject = DeletionRequest.objects.create(user=reject_user)
        response = self.client.post(
            f'/ns-admin/legal/deletions/{reject.pk}/reject/',
            {'notes': 'Identität noch nicht ausreichend bestätigt.'},
        )
        self.assertEqual(response.status_code, 302)
        reject.refresh_from_db()
        self.assertEqual(reject.status, 'rejected')
        process_user = User.objects.create_user(
            'release-process@example.test', 'Delete-Process-Password-2026!'
        )
        PrivateCustomerProfile.objects.create(
            user=process_user, customer_number='RELEASE-P-DELETE'
        )
        deletion = DeletionRequest.objects.create(user=process_user)
        response = self.client.post(f'/ns-admin/legal/deletions/{deletion.pk}/process/')
        self.assertEqual(response.status_code, 302)
        process_user.refresh_from_db()
        self.assertFalse(process_user.is_active)
        self.assertTrue(process_user.email.startswith('deleted+'))
        support = SupportRequest.objects.order_by('created_at').first()
        response = self.client.post(
            f'/ns-admin/support/{support.pk}/status/', {'status': 'closed'}
        )
        self.assertEqual(response.status_code, 302)
        support.refresh_from_db()
        self.assertEqual(support.status, 'closed')
        template = EmailTemplate.objects.order_by('code').first()
        response = self.client.post(
            f'/ns-admin/email/templates/{template.pk}/',
            {
                'subject': 'Release acceptance subject',
                'body_text': 'Release acceptance body',
                'active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertEqual(template.subject, 'Release acceptance subject')

    @patch('apps.core.admin_views._send_staff_setup_email')
    def test_staff_role_toggle_reset_and_assignment(self, _mail):
        support_role = Role.objects.get(code='support')
        response = self.client.post(
            '/ns-admin/roles/users/new/',
            {
                'email': 'release.staff@example.test',
                'first_name': 'Release',
                'last_name': 'Staff',
                'role': str(support_role.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='release.staff@example.test')
        response = self.client.post(f'/ns-admin/roles/users/{user.pk}/toggle/')
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        response = self.client.post(f'/ns-admin/roles/users/{user.pk}/toggle/')
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        user.totp_secret_enc = encrypt('JBSWY3DPEHPK3PXP')
        user.save(update_fields=['totp_secret_enc', 'updated_at'])
        response = self.client.post(f'/ns-admin/roles/users/{user.pk}/reset-2fa/')
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.totp_secret_enc, '')
        ops_role = Role.objects.get(code='ops')
        response = self.client.post(
            '/ns-admin/roles/assign/',
            {'user': str(user.pk), 'role': str(ops_role.pk)},
        )
        self.assertEqual(response.status_code, 302)
        link = UserRole.objects.get(user=user, role=ops_role)
        response = self.client.post(f'/ns-admin/roles/links/{link.pk}/remove/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserRole.objects.filter(pk=link.pk).exists())

    @patch('apps.core.admin_views.submit_refund')
    def test_license_assign_release_block_unblock_and_refund(self, submit_refund):
        company = Company.objects.get(customer_number='DEMO-1001')
        free_license = License.objects.filter(company=company, status='free').first()
        target = (
            Membership.objects.filter(
                company=company,
                active=True,
                role='member',
                user__license_assignments__isnull=True,
            )
            .select_related('user')
            .first()
        )
        self.assertIsNotNone(free_license)
        self.assertIsNotNone(target)
        response = self.client.post(
            f'/ns-admin/licenses/{free_license.pk}/assign/',
            {'user_id': str(target.user_id)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LicenseAssignment.objects.filter(
                license=free_license, user=target.user, ended_at__isnull=True,
            ).exists()
        )
        response = self.client.post(f'/ns-admin/licenses/{free_license.pk}/release/')
        self.assertEqual(response.status_code, 302)
        response = self.client.post(f'/ns-admin/licenses/{free_license.pk}/block-toggle/')
        self.assertEqual(response.status_code, 302)
        free_license.refresh_from_db()
        self.assertEqual(free_license.status, 'blocked')
        response = self.client.post(f'/ns-admin/licenses/{free_license.pk}/block-toggle/')
        self.assertEqual(response.status_code, 302)
        refundable_term = (
            LicenseTerm.objects.filter(
                license__company=company,
                status='active',
                order_item__order__payments__status__in=[
                    'paid', 'chargeback_reversed', 'refunded_partial',
                ],
            )
            .exclude(license__status__in=['blocked', 'payment_review', 'refunded'])
            .select_related('license')
            .order_by('-valid_until')
            .first()
        )
        self.assertIsNotNone(refundable_term)
        response = self.client.post(
            f'/ns-admin/licenses/{refundable_term.license_id}/terms/{refundable_term.pk}/refund/',
            {'reason': 'Release acceptance refund UI', 'confirm': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Refund.objects.filter(term=refundable_term).exists())
        submit_refund.assert_called_once()
