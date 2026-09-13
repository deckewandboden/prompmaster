import json
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog.models import Product, ProductPrice
from apps.companies.models import Company, Membership
from apps.devices.models import DeviceRegistration
from apps.devices.services import register_device
from apps.orders.models import Order, OrderItem
from apps.payments.services import _activate_order
from apps.licenses.models import License
from apps.proaccess.services import DEVICE_COOKIE, LEGACY_DEVICE_COOKIE


class RealProAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_defaults', verbosity=0)
        call_command('seed_prompt_catalog', verbosity=0)
        now = timezone.now()
        cls.user = User.objects.create_user('real-pro@example.test', 'Secure-Test-Password-42!', email_verified_at=now)
        product = Product.objects.get(code='PRO')
        price = ProductPrice.objects.filter(product=product, price_type='new').first()
        order = Order.objects.create(private_user=cls.user, gross_total=Decimal('35.88'), currency='EUR', idempotency_key='real-pro-flow')
        OrderItem.objects.create(order=order, product=product, price_version=price, quantity=1, unit_gross=Decimal('35.88'), unit_net=Decimal('30.15'), tax_rate=Decimal('19'), product_name_snapshot=product.name)
        _activate_order(order, now)
        cls.license = License.objects.get(owner_user=cls.user)

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_registered_cookie_reaches_real_catalog_and_composer(self):
        response = self.client.post('/pro/device/register/', {'display_name': 'Test browser'})
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies[DEVICE_COOKIE]
        self.assertEqual(cookie['path'], '/')
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(DeviceRegistration.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.client.get('/api/v1/prompts/').json()['catalog']['task_count'], 194)
        before = AuditEvent.objects.count()
        response = self.client.post('/api/v1/prompts/compose/', json.dumps({
            'product': 'PRO', 'task_id': 'PM20-001', 'microsoft_tier': 'chatbasic',
            'input': {'fields': {'Fragestellung': 'PRIVATE-QUESTION-42', 'Kontext': 'Private context'},
                      'audience': 'Management', 'focus': ['Primärquellen'], 'output': 'Fundierte Antwort',
                      'source': 'webwork', 'tone': 'professional', 'detail': 'standard'},
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('PRIVATE-QUESTION-42', response.json()['result']['prompt'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_legacy_cookie_migrates_without_consuming_another_device(self):
        device, raw = register_device(self.user, self.license, 'Existing browser')
        self.client.cookies[LEGACY_DEVICE_COOKIE] = raw
        response = self.client.get('/pro/app/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[DEVICE_COOKIE].value, raw)
        self.assertEqual(response.cookies[LEGACY_DEVICE_COOKIE]['max-age'], 0)
        self.assertEqual(DeviceRegistration.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 200)

    def test_unverified_account_cannot_register_or_compose(self):
        self.user.email_verified_at = None
        self.user.save(update_fields=['email_verified_at'])
        self.assertEqual(self.client.post('/pro/device/register/', {'display_name': 'Denied'}).status_code, 403)
        response = self.client.get('/api/v1/prompts/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'email_verification_required')

    def test_expired_or_revoked_device_is_denied(self):
        device, raw = register_device(self.user, self.license, 'Revoked browser')
        self.client.cookies[DEVICE_COOKIE] = raw
        device.revoked_at = timezone.now()
        device.save()
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 403)
        device.revoked_at = None
        device.save()
        self.license.terms.update(valid_from=timezone.now()-timedelta(days=400), valid_until=timezone.now()-timedelta(days=1))
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 403)

    def test_inactive_company_or_membership_cannot_access_pro(self):
        company = Company.objects.create(customer_number='SEC-COMPANY', name='Company', email='company@example.test')
        membership = Membership.objects.create(company=company, user=self.user, role='member')
        self.license.owner_user = None
        self.license.company = company
        self.license.save()
        device, raw = register_device(self.user, self.license, 'Company browser')
        self.client.cookies[DEVICE_COOKIE] = raw
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 200)
        membership.active = False
        membership.save()
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 403)
        membership.active = True
        membership.save()
        company.status = 'inactive'
        company.save()
        self.assertEqual(self.client.get('/api/v1/prompts/').status_code, 403)
        self.assertEqual(self.client.get('/portal/dashboard/').status_code, 403)
