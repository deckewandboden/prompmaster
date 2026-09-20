from __future__ import annotations

import io
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.accounts.totp import new_secret
from apps.companies.models import Company, Membership, PrivateCustomerProfile
from apps.core.crypto import encrypt


class InteractiveContractParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.forms = []
        self.buttons = []
        self._form_stack = []
        self._current_form = None

    @staticmethod
    def _attrs(attrs):
        return {key: value if value is not None else '' for key, value in attrs}

    def handle_starttag(self, tag, attrs):
        data = self._attrs(attrs)
        if tag == 'a':
            self.links.append(data.get('href', ''))
        elif tag == 'form':
            form = {
                'action': data.get('action', ''),
                'method': data.get('method', 'get').lower(),
                'csrf': False,
            }
            self.forms.append(form)
            self._form_stack.append(self._current_form)
            self._current_form = form
        elif tag == 'input' and self._current_form is not None:
            if data.get('name') == 'csrfmiddlewaretoken':
                self._current_form['csrf'] = True
        elif tag == 'button':
            self.buttons.append({
                'type': data.get('type', 'submit').lower(),
                'inside_form': self._current_form is not None,
                'form': data.get('form', ''),
            })

    def handle_endtag(self, tag):
        if tag == 'form':
            self._current_form = self._form_stack.pop() if self._form_stack else None


@override_settings(ENVIRONMENT='staging')
class RenderedUiActionContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', stdout=io.StringIO())

    def _session_as(self, user):
        self.client.force_login(user)
        if user.two_factor_required and not user.totp_secret_enc:
            user.totp_secret_enc = encrypt(new_secret())
            user.save(update_fields=['totp_secret_enc', 'updated_at'])
        session = self.client.session
        session['security_version'] = user.security_version
        session['two_factor_ok'] = True
        session['authenticated_at'] = timezone.now().timestamp()
        session['last_activity_at'] = timezone.now().timestamp()
        session.save()

    @staticmethod
    def _internal_target(raw, current_path):
        if not raw:
            return current_path
        if raw.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            return None
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc:
            return None
        path = parsed.path or current_path
        if not path.startswith('/'):
            return None
        query = f'?{parsed.query}' if parsed.query else ''
        return path + query

    def _crawl(self, *, user, root, scope_prefix, minimum_pages, minimum_controls):
        self._session_as(user)
        queue = deque([root])
        visited = set()
        controls = 0

        while queue:
            url = queue.popleft()
            canonical = urlsplit(url).path
            if canonical in visited:
                continue
            if len(visited) >= 600:
                self.fail(f'UI crawl exceeded safety bound for {scope_prefix}: {url}')
            visited.add(canonical)

            response = self.client.get(url, follow=True)
            self.assertLess(
                response.status_code,
                400,
                f'Visible UI target failed for {user.email}: {url} -> {response.status_code}',
            )
            content_type = response.get('Content-Type', '')
            if 'text/html' not in content_type:
                continue

            parser = InteractiveContractParser()
            parser.feed(response.content.decode(response.charset or 'utf-8', errors='replace'))
            controls += len(parser.links) + len(parser.forms) + len(parser.buttons)

            for form in parser.forms:
                self.assertIn(form['method'], {'get', 'post'}, f'Unsupported form method on {url}: {form}')
                action = self._internal_target(form['action'], urlsplit(url).path)
                self.assertIsNotNone(action, f'External/dummy form action on {url}: {form}')
                path = urlsplit(action).path
                try:
                    resolve(path)
                except Resolver404 as exc:
                    self.fail(f'Unresolvable form action on {url}: {action}: {exc}')
                if form['method'] == 'post':
                    self.assertTrue(form['csrf'], f'POST form without CSRF token on {url}: {action}')

            for button in parser.buttons:
                if button['type'] == 'submit':
                    self.assertTrue(
                        button['inside_form'] or button['form'],
                        f'Submit button without form contract on {url}: {button}',
                    )
                else:
                    self.assertIn(button['type'], {'button', 'reset'}, f'Unsupported button type on {url}: {button}')

            for href in parser.links:
                if href in {'#', ''} or href.lower().startswith('javascript:'):
                    self.fail(f'Dead/dummy link rendered for {user.email} on {url}: {href!r}')
                target = self._internal_target(href, urlsplit(url).path)
                if target is None:
                    continue
                path = urlsplit(target).path
                if not path.startswith(scope_prefix):
                    continue
                if '/download/' in path:
                    continue
                if target not in visited:
                    queue.append(target)

        self.assertGreaterEqual(len(visited), minimum_pages, f'UI crawl for {user.email} covered too few pages: {sorted(visited)}')
        self.assertGreaterEqual(controls, minimum_controls, f'UI crawl for {user.email} covered too few interactive controls')
        self.client.logout()

    def test_superadmin_rendered_admin_actions_are_wired(self):
        superadmin = (
            UserRole.objects.filter(
                role__code='superadmin',
                user__email__endswith='@promptmaster.invalid',
                user__is_staff=True,
            )
            .select_related('user')
            .order_by('user__email')
            .first()
            .user
        )
        self._crawl(
            user=superadmin,
            root='/ns-admin/',
            scope_prefix='/ns-admin/',
            minimum_pages=25,
            minimum_controls=100,
        )

    def test_company_admin_rendered_portal_actions_are_wired(self):
        company = Company.objects.get(customer_number='DEMO-1001')
        admin = Membership.objects.get(company=company, active=True, role='admin').user
        self._crawl(
            user=admin,
            root='/portal/dashboard/',
            scope_prefix='/portal/',
            minimum_pages=10,
            minimum_controls=45,
        )

    def test_private_customer_rendered_portal_actions_are_wired(self):
        private = PrivateCustomerProfile.objects.select_related('user').get(
            customer_number='DEMO-P-2001'
        )
        self._crawl(
            user=private.user,
            root='/portal/dashboard/',
            scope_prefix='/portal/',
            minimum_pages=7,
            minimum_controls=25,
        )
