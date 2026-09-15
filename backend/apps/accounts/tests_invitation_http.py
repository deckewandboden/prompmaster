"""Invitation acceptance through a real HTTP server and the full middleware stack."""
from datetime import timedelta
from html.parser import HTMLParser

import requests
from django.core.cache import cache
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import User
from apps.companies.models import Company, Membership
from apps.companies.services import create_invitation


class FormParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.csrf = None
        self.methods = []
        self.submit = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.methods.append(attrs.get('method', 'get').lower())
        if tag == 'input' and attrs.get('name') == 'csrfmiddlewaretoken':
            self.csrf = attrs.get('value')
        if tag == 'button' and attrs.get('type') == 'submit':
            self.submit = True


@override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
                   SECURE_SSL_REDIRECT=False)
class InvitationHTTPTests(LiveServerTestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(
            customer_number='INV-HTTP', name='Muster & Partner <GmbH>',
            email='company@example.test')
        self.admin = User.objects.create_user('admin@example.test', 'Invitation-Test-Password!')
        self.user = User.objects.create_user('member@example.test', 'Invitation-Test-Password!')
        self.invitation, self.raw = create_invitation(
            company=self.company, actor=self.admin, email=self.user.email)
        self.http = requests.Session()
        self.addCleanup(self.http.close)
        login_url = self.live_server_url + '/auth/login/'
        page = self.http.get(login_url, timeout=10)
        self.assertEqual(page.status_code, 200)
        csrf = FormParser(page.text).csrf
        self.assertTrue(csrf)
        response = self.http.post(login_url, data={
            'email': self.user.email, 'password': 'Invitation-Test-Password!',
            'csrfmiddlewaretoken': csrf,
        }, allow_redirects=False, timeout=10)
        self.assertEqual(response.status_code, 302)

    def url(self, token=None):
        return self.live_server_url + '/auth/invite/' + (token or self.raw) + '/'

    def assert_not_joined(self):
        self.invitation.refresh_from_db()
        self.assertIsNone(self.invitation.accepted_at)
        self.assertFalse(Membership.objects.filter(user=self.user).exists())

    def test_confirmation_csrf_membership_and_consumed_link(self):
        page = self.http.get(self.url(), timeout=10)
        self.assertEqual(page.status_code, 200)
        self.assertIn(str(escape(self.company.name)), page.text)
        self.assertNotIn('{{', page.text)
        self.assertNotIn('{%', page.text)
        self.assertIn('Firma beitreten', page.text)
        form = FormParser(page.text)
        self.assertEqual(form.methods, ['post'])
        self.assertTrue(form.csrf)
        self.assertTrue(form.submit)
        self.assert_not_joined()
        self.assertEqual(self.http.head(self.url(), timeout=10).status_code, 200)
        self.assert_not_joined()
        for data in ({}, {'csrfmiddlewaretoken': 'invalid'}):
            response = self.http.post(self.url(), data=data, timeout=10)
            self.assertEqual(response.status_code, 403)
            self.assert_not_joined()
        response = self.http.post(self.url(), data={
            'csrfmiddlewaretoken': form.csrf}, timeout=10)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Einladung angenommen', response.text)
        membership = Membership.objects.get(user=self.user, company=self.company)
        self.assertTrue(membership.active)
        self.assertEqual(membership.role, 'member')
        self.invitation.refresh_from_db()
        accepted_at = self.invitation.accepted_at
        self.assertIsNotNone(accepted_at)
        for method in ('get', 'post'):
            response = self.http.request(method, self.url(), data={
                'csrfmiddlewaretoken': form.csrf}, timeout=10)
            self.assertIn('Einladung ungültig oder abgelaufen', response.text)
            self.assertNotIn('Einladung angenommen', response.text)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.accepted_at, accepted_at)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)

    def test_invalid_token_cannot_join(self):
        csrf = FormParser(self.http.get(self.url(), timeout=10).text).csrf
        for method in ('get', 'post'):
            response = self.http.request(method, self.url('invalid-token'),
                data={'csrfmiddlewaretoken': csrf}, timeout=10)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Einladung ungültig oder abgelaufen', response.text)
            self.assert_not_joined()

    def test_token_expired_after_confirmation_page_cannot_join(self):
        csrf = FormParser(self.http.get(self.url(), timeout=10).text).csrf
        self.invitation.expires_at = timezone.now() - timedelta(seconds=1)
        self.invitation.save(update_fields=['expires_at'])
        for method in ('get', 'post'):
            response = self.http.request(method, self.url(),
                data={'csrfmiddlewaretoken': csrf}, timeout=10)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Einladung ungültig oder abgelaufen', response.text)
            self.assert_not_joined()
