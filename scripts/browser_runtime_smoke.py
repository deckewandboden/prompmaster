#!/usr/bin/env python3
"""Optional browser smoke for the derived Pro runtime without network access.

The test injects a deterministic in-page fetch stub before PromptMaster code is
executed. It validates the 34-app server catalog bridge, task rendering,
server-compose payload and deliberate rating/feedback flow.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'backend/private_assets/promptmaster_pro_runtime.html'
DATA = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'


def mock_catalog() -> dict:
    data = json.loads(DATA.read_text(encoding='utf-8'))
    apps = []
    access = data.get('ACCESS_RULES') or {}
    task_access = data.get('TASK_ACCESS_RULES') or {}
    for sort_order, (code, app) in enumerate((data.get('APP') or {}).items()):
        tasks = []
        for task in app.get('tasks') or []:
            tasks.append({
                'id': task['id'], 'title': task.get('title') or task['id'], 'intent': task.get('intent') or '',
                'required': task.get('required') or [], 'optional': task.get('optional') or [],
                'area': task.get('area') or '', 'family': task.get('family') or 'analysis',
                'sources': task.get('sources') or [], 'outputs': task.get('outputs') or [],
                'focus': task.get('focus') or [], 'audiences': task.get('audiences') or [],
                'access': task.get('access'), 'status': task.get('status') or app.get('status') or '',
                'maxChars': task.get('maxChars'), 'prompt_version': 1, 'policy_version': 1,
                'minimum_tier_rank': int((task_access.get(task['id']) or {}).get('tier', 0)),
                'promptmaster_entitled': True,
            })
        apps.append({
            'code': code, 'name': app.get('name') or code, 'group': app.get('group') or 'm365',
            'icon': app.get('icon') or '', 'color': app.get('color') or '#0c71c3',
            'copy': app.get('copy') or '', 'access': app.get('access') or '',
            'status': app.get('status') or '', 'target': app.get('target') or app.get('name') or code,
            'rule': app.get('rule') or '', 'evidence': app.get('evidence') or [], 'sort_order': sort_order,
            'minimum_tier_rank': int((access.get(code) or {}).get('tier', 0)),
            'promptmaster_entitled': True, 'tasks': tasks,
        })
    return {
        'product_code': 'PRO', 'policy_version': 1, 'source_labels': data.get('SRC_LABEL') or {},
        'application_count': len(apps), 'task_count': sum(len(app['tasks']) for app in apps),
        'applications': apps,
    }


def injected_fetch(catalog: dict) -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False).replace('</', '<\\/')
    return f"""<script>
window.__pmSmokeCompose=[]; window.__pmSmokeRatings=[];
window.fetch=async function(url, options){{
  const u=String(url); const method=String(options?.method||'GET').toUpperCase();
  const jsonResponse=(payload,status=200)=>new Response(JSON.stringify(payload),{{status,headers:{{'Content-Type':'application/json'}}}});
  if(u.includes('/api/v1/prompts/?product=PRO')) return jsonResponse({{'ok':true,'catalog':{catalog_json}}});
  if(u.endsWith('/api/v1/prompts/compose/') && method==='POST'){{
    const body=JSON.parse(options?.body||'{{}}'); window.__pmSmokeCompose.push(body);
    return jsonResponse({{'ok':true,'result':{{'prompt':'SERVER TEST PROMPT','ready':true,'progress_percent':100,'task_id':body.task_id,'app_code':'copilot_chat','policy_version':1,'prompt_version':1,'persisted':false}}}});
  }}
  if(u.includes('/rating/') && method==='POST'){{
    const body=JSON.parse(options?.body||'{{}}'); window.__pmSmokeRatings.push(body);
    return jsonResponse({{'ok':true,'rating':{{'stars':body.stars,'feedback_saved':!!body.feedback,'quality_status':'OK','recent_average':'4.50','rating_count':2}}}});
  }}
  return jsonResponse({{'ok':false,'error':{{'message':'unexpected '+u}}}},404);
}};
</script>"""



def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, process, timeout: float = 30.0) -> None:
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise AssertionError(f'Django test server exited early with {process.returncode}')
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.25)
    raise AssertionError(f'Django test server did not become ready: {url}')


def _backend_fixture() -> dict:
    import hashlib
    import sys
    from decimal import Decimal
    from datetime import timedelta

    backend = ROOT / 'backend'
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    import django
    django.setup()

    from django.db import connections
    from django.utils import timezone
    from apps.accounts.models import Role, User, UserRole
    from apps.catalog.models import Product
    from apps.catalog.services import current_price
    from apps.companies.models import Company, Invitation, Membership, PrivateCustomerProfile
    from apps.core.crypto import encrypt
    from apps.devices.models import DeviceRegistration
    from apps.legal.models import LegalDocument
    from apps.licenses.models import License, LicenseAssignment, LicenseTerm
    from apps.orders.models import Order, OrderItem
    from apps.payments.models import Payment
    from apps.prompts.models import PromptDefinition
    from apps.support.models import SupportRequest

    now = timezone.now()
    password = 'BrowserSmoke!2026-Strong'
    admin_secret = 'JBSWY3DPEHPK3PXP'
    customer_secret = 'MFRGGZDFMZTWQ2LK'

    def upsert_user(email, first, last, *, secret='', staff=False, superuser=False):
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first,
                'last_name': last,
                'is_active': True,
                'is_staff': staff,
                'is_superuser': superuser,
            },
        )
        user.first_name = first
        user.last_name = last
        user.is_active = True
        user.is_staff = staff
        user.is_superuser = superuser
        user.email_verified_at = now
        user.two_factor_required = bool(secret)
        user.totp_secret_enc = encrypt(secret) if secret else ''
        user.last_totp_step = -1
        user.security_version = 1
        user.set_password(password)
        user.save()
        return user

    admin = upsert_user(
        'browser-admin@example.invalid',
        'Browser',
        'Admin',
        secret=admin_secret,
        staff=True,
        superuser=True,
    )
    superadmin = Role.objects.filter(code='superadmin').first()
    if superadmin:
        UserRole.objects.get_or_create(user=admin, role=superadmin)

    first_time_admin = upsert_user(
        'browser-first-mfa-admin@example.invalid',
        'First MFA',
        'Admin',
        staff=True,
        superuser=True,
    )
    first_time_admin.two_factor_required = True
    first_time_admin.totp_secret_enc = ''
    first_time_admin.last_totp_step = -1
    first_time_admin.save(
        update_fields=[
            'two_factor_required', 'totp_secret_enc',
            'last_totp_step', 'updated_at',
        ]
    )
    if superadmin:
        UserRole.objects.get_or_create(user=first_time_admin, role=superadmin)

    customer = upsert_user(
        'browser-company@example.invalid',
        'Kunden',
        'Admin',
        secret=customer_secret,
    )
    member = upsert_user(
        'browser-member@example.invalid',
        'Test',
        'Mitarbeiter',
    )

    company, _ = Company.objects.update_or_create(
        customer_number='C-BROWSER-SMOKE',
        defaults={
            'name': 'Browser Smoke GmbH',
            'email': customer.email,
            'phone': '+49 123 456789',
            'street': 'Teststraße',
            'house_number': '1',
            'postal_code': '57072',
            'city': 'Siegen',
            'country': 'DE',
            'status': 'active',
        },
    )
    Membership.objects.update_or_create(
        company=company,
        user=customer,
        defaults={'role': 'admin', 'active': True},
    )
    Membership.objects.update_or_create(
        company=company,
        user=member,
        defaults={'role': 'member', 'active': True},
    )

    private_user = upsert_user(
        'browser-private@example.invalid',
        'Private',
        'Customer',
    )
    private_profile, _ = PrivateCustomerProfile.objects.update_or_create(
        user=private_user,
        defaults={
            'customer_number': 'P-BROWSER-SMOKE',
            'street': 'Privatweg',
            'house_number': '7',
            'postal_code': '57072',
            'city': 'Siegen',
            'country': 'DE',
        },
    )
    Invitation.objects.update_or_create(
        token_hash=hashlib.sha256(b'browser-smoke-invitation').hexdigest(),
        defaults={
            'company': company,
            'email': 'browser-invite@example.invalid',
            'first_name': 'Invite',
            'last_name': 'User',
            'expires_at': now + timedelta(hours=24),
            'accepted_at': None,
            'revoked_at': None,
            'invited_by': customer,
        },
    )

    for doc_type in ('terms', 'privacy'):
        LegalDocument.objects.update_or_create(
            doc_type=doc_type,
            version='browser-smoke-v1',
            defaults={
                'content': f'Browser smoke {doc_type}',
                'valid_from': now - timedelta(days=1),
                'active': True,
            },
        )

    product = Product.objects.get(code='PRO')
    price = current_price(product, 'new', now)
    if not price:
        raise AssertionError('Browser fixture requires current PRO new price')

    active_license, _ = License.objects.update_or_create(
        license_number='PM-BROWSER-ACTIVE',
        defaults={
            'company': company,
            'owner_user': None,
            'product': product,
            'status': 'active',
            'valid_from': now - timedelta(days=30),
            'valid_until': now + timedelta(days=335),
        },
    )
    free_license, _ = License.objects.update_or_create(
        license_number='PM-BROWSER-FREE',
        defaults={
            'company': company,
            'owner_user': None,
            'product': product,
            'status': 'free',
            'valid_from': now - timedelta(days=5),
            'valid_until': now + timedelta(days=360),
        },
    )
    LicenseAssignment.objects.filter(license=active_license, ended_at__isnull=True).exclude(user=customer).update(ended_at=now)
    LicenseAssignment.objects.get_or_create(
        license=active_license,
        user=customer,
        ended_at=None,
    )
    deterministic_device_hash = hashlib.sha256(b'browser-smoke-device').hexdigest()
    DeviceRegistration.objects.filter(
        user=customer,
        license=active_license,
        revoked_at__isnull=True,
    ).exclude(token_hash=deterministic_device_hash).delete()
    DeviceRegistration.objects.update_or_create(
        token_hash=deterministic_device_hash,
        defaults={
            'user': customer,
            'license': active_license,
            'display_name': 'Browser Smoke Notebook',
            'os_family': 'Windows',
            'browser_family': 'Chromium',
            'last_seen_at': now,
            'revoked_at': None,
        },
    )

    order, _ = Order.objects.update_or_create(
        order_number='PM-BROWSER-ORDER',
        defaults={
            'company': company,
            'private_user': None,
            'status': 'paid',
            'currency': 'EUR',
            'gross_total': Decimal('35.88'),
            'tax_total': Decimal('5.73'),
            'billing_snapshot': {'company': company.name},
            'idempotency_key': 'browser-smoke-order-v1',
        },
    )
    # LicenseTerm protects its OrderItem. Remove only this deterministic smoke
    # fixture's term before rebuilding the order item so repeated local runs
    # remain idempotent.
    LicenseTerm.objects.filter(order_item__order=order).delete()
    order.items.all().delete()
    order_item = OrderItem.objects.create(
        order=order,
        product=product,
        price_version=price,
        quantity=1,
        unit_gross=Decimal('35.88'),
        unit_net=Decimal('30.15'),
        tax_rate=Decimal('19.00'),
        product_name_snapshot=product.name,
    )
    LicenseTerm.objects.update_or_create(
        license=active_license,
        order_item=order_item,
        defaults={
            'valid_from': active_license.valid_from,
            'valid_until': active_license.valid_until,
            'paid_gross_amount': Decimal('35.88'),
            'status': 'active',
            'refunded_at': None,
        },
    )
    Payment.objects.update_or_create(
        provider_payment_id='tr_browser_smoke_paid',
        defaults={
            'order': order,
            'provider': 'mollie',
            'status': 'paid',
            'amount': Decimal('35.88'),
            'currency': 'EUR',
            'method': 'banktransfer',
            'paid_at': now,
            'processed_paid': True,
            'last_provider_payload': {},
        },
    )
    SupportRequest.objects.update_or_create(
        user=customer,
        company=company,
        subject='Browser Smoke Support',
        defaults={
            'license': active_license,
            'category': 'technical',
            'message': 'Repräsentativer Browser-Smoke-Datensatz.',
            'status': 'new',
        },
    )

    definition = PromptDefinition.objects.filter(active=True).prefetch_related('versions').order_by('task_id').first()
    if not definition:
        raise AssertionError('Browser fixture requires seeded Prompt Studio definitions')
    version = definition.versions.order_by('-version').first()
    if not version:
        raise AssertionError('Browser fixture requires seeded Prompt Studio version')

    # Seed the exact staging demo estate too. Browser acceptance then uses the
    # same five companies, three private customers and duplicated netstyle
    # role identities that operators receive after bootstrap.
    import io
    from django.core.management import call_command
    demo_output = io.StringIO()
    call_command('seed_demo_data', stdout=demo_output, verbosity=0)
    demo_credentials = {}
    for line in demo_output.getvalue().splitlines():
        if '@promptmaster.invalid' not in line or '|' not in line:
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) >= 4 and '@promptmaster.invalid' in parts[1]:
            demo_credentials[parts[1]] = {
                'password': parts[2],
                'label': parts[0],
                'note': parts[3],
            }
    if len(demo_credentials) != 26:
        raise AssertionError(
            f'Browser demo fixture expected 26 login identities, got {len(demo_credentials)}'
        )

    demo_companies = list(
        Company.objects.filter(customer_number__startswith='DEMO-')
        .order_by('customer_number')
        .values_list('customer_number', flat=True)
    )
    demo_private = list(
        PrivateCustomerProfile.objects.filter(customer_number__startswith='DEMO-P-')
        .order_by('customer_number')
        .values_list('customer_number', flat=True)
    )
    if demo_companies != ['DEMO-1001', 'DEMO-1002', 'DEMO-1003', 'DEMO-1004', 'DEMO-1005']:
        raise AssertionError(f'Browser demo companies incomplete: {demo_companies}')
    if demo_private != ['DEMO-P-2001', 'DEMO-P-2002', 'DEMO-P-2003']:
        raise AssertionError(f'Browser private demo customers incomplete: {demo_private}')

    connections.close_all()
    return {
        'password': password,
        'admin_email': admin.email,
        'admin_secret': admin_secret,
        'first_time_admin_email': first_time_admin.email,
        'customer_email': customer.email,
        'customer_secret': customer_secret,
        'member_email': member.email,
        'company_id': str(company.pk),
        'private_customer_id': str(private_profile.pk),
        'member_id': str(member.pk),
        'product_id': str(product.pk),
        'license_id': str(active_license.pk),
        'order_id': str(order.pk),
        'task_id': definition.task_id,
        'version_id': str(version.pk),
        'free_license_id': str(free_license.pk),
        'demo_credentials': demo_credentials,
        'demo_companies': demo_companies,
        'demo_private': demo_private,
    }


def _browser_first_time_mfa_login(page, base: str, email: str, password: str, expected_path: str) -> None:
    import pyotp

    response = page.goto(base + 'auth/login/', wait_until='networkidle')
    if not response or response.status != 200:
        raise AssertionError(f'first-time login page failed for {email}')
    page.locator('input[name="email"]').fill(email)
    password_input = page.locator('input[name="password"]')
    password_input.fill(password)
    password_input.press('Enter')
    page.wait_for_url('**/auth/2fa/setup/**')
    secret = page.locator('#totpSecret').inner_text().strip()
    if not secret:
        raise AssertionError(f'first-time MFA secret missing for {email}')
    page.locator('input[name="code"]').fill(pyotp.TOTP(secret).now())
    page.locator('input[name="code"]').press('Enter')
    page.wait_for_selector('.recovery-codes')
    continue_button = page.locator('.result-actions a.btn.primary')
    if continue_button.get_attribute('href') != expected_path:
        raise AssertionError(
            f'first-time MFA for {email} continues to '
            f'{continue_button.get_attribute("href")}, expected {expected_path}'
        )
    # Use a DOM click and own the navigation wait explicitly. Playwright's
    # Locator.click() waits for every scheduled navigation and can hang for 30s
    # on this post-MFA handoff even after the link was successfully activated.
    # The acceptance contract is the resulting URL + loaded destination, not
    # Playwright's implicit navigation bookkeeping.
    continue_button.evaluate("(el) => el.click()")
    page.wait_for_url(
        lambda url: expected_path in str(url),
        wait_until='domcontentloaded',
        timeout=15000,
    )
    page.wait_for_load_state('domcontentloaded')


_LAST_SUCCESSFUL_TOTP_BY_EMAIL = {}


def _fresh_browser_totp(email: str, secret: str) -> str:
    """Return a TOTP code not already consumed by this browser acceptance run."""
    import time
    import pyotp

    totp = pyotp.TOTP(secret)
    previous = _LAST_SUCCESSFUL_TOTP_BY_EMAIL.get(email)
    code = totp.now()
    deadline = time.monotonic() + 35.0

    while previous is not None and code == previous:
        if time.monotonic() >= deadline:
            raise AssertionError(f'fresh TOTP not available in time for {email}')
        time.sleep(0.25)
        code = totp.now()

    return code


def _browser_login(page, base: str, email: str, password: str, secret: str, expected_path: str) -> None:
    import pyotp

    response = page.goto(base + 'auth/login/', wait_until='networkidle')
    if not response or response.status != 200:
        raise AssertionError(f'login page failed for {email}')
    page.locator('input[name="email"]').fill(email)
    password_input = page.locator('input[name="password"]')
    password_input.fill(password)
    # Submit through the focused form control instead of depending on a
    # presentation-level button selector. This still exercises the browser's
    # normal HTML form submit path and survives harmless template refactors.
    password_input.press('Enter')
    page.wait_for_url('**/auth/2fa/**')
    code_input = page.locator('input[name="code"]')
    two_factor_layout = page.evaluate(
        """() => {
          const card = document.querySelector('.auth-login-card');
          const input = document.querySelector('.auth-login-form input[name="code"]');
          const button = document.querySelector('.auth-login-form .auth-submit');
          if (!card || !input || !button) return null;
          const i = input.getBoundingClientRect();
          const b = button.getBoundingClientRect();
          const c = card.getBoundingClientRect();
          return {
            cardWidth: c.width,
            inputWidth: i.width,
            buttonWidth: b.width,
            inputHeight: i.height,
            buttonHeight: b.height,
            overlap: !(i.bottom <= b.top),
          };
        }"""
    )
    if (
        not two_factor_layout
        or two_factor_layout['cardWidth'] < 300
        or abs(two_factor_layout['inputWidth'] - two_factor_layout['buttonWidth']) > 2
        or two_factor_layout['inputHeight'] < 44
        or two_factor_layout['buttonHeight'] < 42
        or two_factor_layout['overlap']
    ):
        raise AssertionError(f'2FA layout is unstable: {two_factor_layout}')
    submitted_code = _fresh_browser_totp(email, secret)
    code_input.fill(submitted_code)
    code_input.press('Enter')
    page.wait_for_url(lambda url: '/auth/2fa/' not in url and '/auth/login/' not in url)
    page.wait_for_load_state('networkidle')
    if expected_path not in page.url:
        raise AssertionError(f'login for {email} ended at {page.url}, expected {expected_path}')
    _LAST_SUCCESSFUL_TOTP_BY_EMAIL[email] = submitted_code


def _browser_login_password_only(page, base: str, email: str, password: str, expected_path: str) -> None:
    response = page.goto(base + 'auth/login/', wait_until='networkidle')
    if not response or response.status != 200:
        raise AssertionError(f'login page failed for {email}')
    page.locator('input[name="email"]').fill(email)
    password_input = page.locator('input[name="password"]')
    password_input.fill(password)
    password_input.press('Enter')
    page.wait_for_url(lambda url: '/auth/login/' not in str(url) and '/auth/2fa/' not in str(url))
    page.wait_for_load_state('networkidle')
    if expected_path not in page.url:
        raise AssertionError(f'password-only login for {email} ended at {page.url}, expected {expected_path}')


def _check_backend_page(page, base: str, path: str, width: int, label: str) -> None:
    response = page.goto(base + path.lstrip('/'), wait_until='networkidle')
    if not response or response.status != 200:
        status = response.status if response else 'no response'
        raise AssertionError(f'{label} {width}px: HTTP {status} for {path}')
    if '/auth/login/' in page.url or '/auth/2fa/' in page.url:
        raise AssertionError(f'{label} {width}px: unexpected auth redirect for {path}')

    metrics = page.evaluate(
        """() => {
          const visible = (el) => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const selectors = '.content input,.content select,.content textarea,.content .btn,.content .card,.content .page-head';
          const overflowers = [...document.querySelectorAll(selectors)]
            .filter(visible)
            .map(el => {
              const r = el.getBoundingClientRect();
              return {
                tag: el.tagName.toLowerCase(),
                cls: typeof el.className === 'string' ? el.className.slice(0, 100) : '',
                left: Math.round(r.left),
                right: Math.round(r.right),
                width: Math.round(r.width),
              };
            })
            .filter(x => x.left < -1 || x.right > innerWidth + 1)
            .slice(0, 10);

          const controls = [...document.querySelectorAll('.content a.btn,.content button')]
            .filter(visible)
            .map(el => {
              const r = el.getBoundingClientRect();
              return {el, left:r.left, right:r.right, top:r.top, bottom:r.bottom, text:(el.textContent||'').trim().slice(0,60)};
            });
          const overlaps = [];
          for (let i=0;i<controls.length;i++) {
            for (let j=i+1;j<controls.length;j++) {
              const a=controls[i], b=controls[j];
              const w=Math.min(a.right,b.right)-Math.max(a.left,b.left);
              const h=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
              if (w > 2 && h > 2) overlaps.push([a.text,b.text]);
            }
          }

          const sidebar = document.querySelector('.sidebar');
          const mobileTitle = document.querySelector('.mobile-title');
          const mobileMenu = document.querySelector('.mobile-menu');
          const mobileLinks = mobileMenu
            ? [...mobileMenu.querySelectorAll('a')].filter(visible)
            : [];
          const mobileRows = new Set(
            mobileLinks.map(el => Math.round(el.getBoundingClientRect().top))
          ).size;
          const badAnchors = [...document.querySelectorAll('.content a')]
            .filter(visible)
            .map(el => ({text:(el.textContent||'').trim().slice(0,60), href:(el.getAttribute('href')||'').trim()}))
            .filter(row => !row.href || row.href === '#' || row.href.toLowerCase().startsWith('javascript:'));
          const orphanSubmitButtons = [...document.querySelectorAll('.content button')]
            .filter(visible)
            .filter(el => (el.getAttribute('type') || 'submit').toLowerCase() === 'submit' && !el.closest('form'))
            .map(el => (el.textContent||'').trim().slice(0,60));
          const postFormsMissingCsrf = [...document.querySelectorAll('.content form')]
            .filter(form => (form.getAttribute('method') || 'get').toLowerCase() === 'post')
            .filter(form => !form.querySelector('input[name="csrfmiddlewaretoken"]'))
            .map(form => form.getAttribute('action') || location.pathname);

          const content = document.querySelector('.content');
          const userMeta = document.querySelector('.user-meta');
          const brandLogo = document.querySelector('.sidebar .brand img');
          const inlineConfirmForms = [...document.querySelectorAll('form[onsubmit]')]
            .filter(form => (form.getAttribute('onsubmit') || '').includes('confirm('))
            .map(form => form.getAttribute('action') || location.pathname);
          return {
            innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            overflowers,
            overlaps: overlaps.slice(0,10),
            badAnchors: badAnchors.slice(0,10),
            orphanSubmitButtons: orphanSubmitButtons.slice(0,10),
            postFormsMissingCsrf: postFormsMissingCsrf.slice(0,10),
            h1: (document.querySelector('h1')?.textContent || '').trim(),
            activeNav: document.querySelectorAll('.nav a.active').length,
            sidebarDisplay: sidebar ? getComputedStyle(sidebar).display : 'missing',
            mobileTitleDisplay: mobileTitle ? getComputedStyle(mobileTitle).display : 'missing',
            mobileTitleText: (mobileTitle?.textContent || '').trim(),
            mobileMenuDisplay: mobileMenu ? getComputedStyle(mobileMenu).display : 'missing',
            mobileMenuCount: mobileLinks.length,
            mobileMenuRows: mobileRows,
            mobileMenuHeight: mobileMenu ? Math.round(mobileMenu.getBoundingClientRect().height) : 0,
            contentPaddingBottom: content ? parseFloat(getComputedStyle(content).paddingBottom || '0') : 0,
            userMetaDisplay: userMeta ? getComputedStyle(userMeta).display : 'missing',
            brandLogoPath: brandLogo ? new URL(brandLogo.src).pathname : '',
            brandNaturalWidth: brandLogo?.naturalWidth || 0,
            inlineConfirmForms: inlineConfirmForms.slice(0,10),
          };
        }"""
    )

    if metrics['scrollWidth'] > metrics['innerWidth'] + 1:
        raise AssertionError(
            f'{label} {width}px: horizontal overflow '
            f'{metrics["scrollWidth"]}>{metrics["innerWidth"]}; {metrics["overflowers"]}'
        )
    if metrics['overflowers']:
        raise AssertionError(f'{label} {width}px: controls/cards leave viewport: {metrics["overflowers"]}')
    if metrics['overlaps']:
        raise AssertionError(f'{label} {width}px: overlapping actions: {metrics["overlaps"]}')
    if metrics['badAnchors']:
        raise AssertionError(f'{label} {width}px: unwired/invalid links: {metrics["badAnchors"]}')
    if metrics['orphanSubmitButtons']:
        raise AssertionError(
            f'{label} {width}px: submit buttons without form: {metrics["orphanSubmitButtons"]}'
        )
    if metrics['postFormsMissingCsrf']:
        raise AssertionError(
            f'{label} {width}px: POST forms without CSRF token: {metrics["postFormsMissingCsrf"]}'
        )
    if metrics['inlineConfirmForms']:
        raise AssertionError(
            f'{label} {width}px: browser-native confirm handlers still active: {metrics["inlineConfirmForms"]}'
        )
    if metrics['brandLogoPath'] != '/static/brand/promptmaster-logo-clean.svg':
        raise AssertionError(
            f'{label} {width}px: legacy brand asset active: {metrics["brandLogoPath"]}'
        )
    if metrics['brandNaturalWidth'] < 300:
        raise AssertionError(
            f'{label} {width}px: brand asset is not high-resolution enough: {metrics["brandNaturalWidth"]}'
        )
    if not metrics['h1']:
        raise AssertionError(f'{label} {width}px: page has no visible H1')
    if metrics['activeNav'] < 1:
        raise AssertionError(f'{label} {width}px: no active desktop navigation state for {path}')

    if width <= 700:
        if metrics['sidebarDisplay'] != 'none':
            raise AssertionError(f'{label} {width}px: sidebar must be hidden')
        if metrics['mobileTitleDisplay'] == 'none' or not metrics['mobileTitleText'].startswith('PROMPTMASTER'):
            raise AssertionError(f'{label} {width}px: PromptMaster mobile header missing')
        if metrics['mobileMenuDisplay'] == 'none':
            raise AssertionError(f'{label} {width}px: mobile bottom navigation missing')
        if metrics['mobileMenuCount'] != 5:
            raise AssertionError(
                f'{label} {width}px: expected 5 mobile navigation entries, '
                f'got {metrics["mobileMenuCount"]}'
            )
        if metrics['mobileMenuRows'] != 1:
            raise AssertionError(
                f'{label} {width}px: mobile navigation wraps into '
                f'{metrics["mobileMenuRows"]} rows'
            )
        if metrics['contentPaddingBottom'] < metrics['mobileMenuHeight'] + 4:
            raise AssertionError(
                f'{label} {width}px: content padding does not clear mobile navigation '
                f'({metrics["contentPaddingBottom"]} < {metrics["mobileMenuHeight"]} + 4)'
            )
        if metrics['userMetaDisplay'] != 'none':
            raise AssertionError(f'{label} {width}px: verbose user metadata must be hidden')
    else:
        if metrics['sidebarDisplay'] == 'none':
            raise AssertionError(f'{label} {width}px: desktop/tablet sidebar missing')
        if metrics['mobileTitleDisplay'] != 'none':
            raise AssertionError(f'{label} {width}px: mobile title visible outside mobile breakpoint')



def _check_public_page(page, base: str, path: str, width: int, label: str) -> None:
    page.set_viewport_size({'width': width, 'height': 900})
    response = page.goto(base + path.lstrip('/'), wait_until='networkidle')
    if not response or response.status != 200:
        status = response.status if response else 'no response'
        raise AssertionError(f'{label} {width}px: HTTP {status} for {path}')
    metrics = page.evaluate(
        """() => {
          const visible = (el) => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const elements = [...document.querySelectorAll(
            '.login-card,.legal-page,.login-card input,.login-card select,.login-card textarea,.login-card .btn'
          )].filter(visible);
          const overflowers = elements.map(el => {
            const r = el.getBoundingClientRect();
            return {tag:el.tagName.toLowerCase(),left:Math.round(r.left),right:Math.round(r.right)};
          }).filter(x => x.left < -1 || x.right > innerWidth + 1);
          const badAnchors = [...document.querySelectorAll('a')]
            .filter(visible)
            .map(el => ({text:(el.textContent||'').trim().slice(0,60), href:(el.getAttribute('href')||'').trim()}))
            .filter(row => !row.href || row.href === '#' || row.href.toLowerCase().startsWith('javascript:'));
          const orphanSubmitButtons = [...document.querySelectorAll('button')]
            .filter(visible)
            .filter(el => (el.getAttribute('type') || 'submit').toLowerCase() === 'submit' && !el.closest('form'))
            .map(el => (el.textContent||'').trim().slice(0,60));
          const postFormsMissingCsrf = [...document.querySelectorAll('form')]
            .filter(form => (form.getAttribute('method') || 'get').toLowerCase() === 'post')
            .filter(form => !form.querySelector('input[name="csrfmiddlewaretoken"]'))
            .map(form => form.getAttribute('action') || location.pathname);
          const loginLogo = document.querySelector('.login-logo img, .legal-page-head img');
          return {
            innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            h1: (document.querySelector('h1')?.textContent || '').trim(),
            overflowers,
            badAnchors: badAnchors.slice(0,10),
            orphanSubmitButtons: orphanSubmitButtons.slice(0,10),
            postFormsMissingCsrf: postFormsMissingCsrf.slice(0,10),
            loginLogoPath: loginLogo ? new URL(loginLogo.src).pathname : '',
            loginLogoNaturalWidth: loginLogo?.naturalWidth || 0,
          };
        }"""
    )
    if metrics['scrollWidth'] > metrics['innerWidth'] + 1:
        raise AssertionError(
            f'{label} {width}px: horizontal overflow '
            f'{metrics["scrollWidth"]}>{metrics["innerWidth"]}'
        )
    if metrics['overflowers']:
        raise AssertionError(f'{label} {width}px: public UI leaves viewport: {metrics["overflowers"]}')
    if metrics['badAnchors']:
        raise AssertionError(f'{label} {width}px: unwired public links: {metrics["badAnchors"]}')
    if metrics['orphanSubmitButtons']:
        raise AssertionError(
            f'{label} {width}px: public submit buttons without form: {metrics["orphanSubmitButtons"]}'
        )
    if metrics['postFormsMissingCsrf']:
        raise AssertionError(
            f'{label} {width}px: public POST forms without CSRF: {metrics["postFormsMissingCsrf"]}'
        )
    if metrics['loginLogoPath']:
        if metrics['loginLogoPath'] != '/static/brand/promptmaster-logo-clean.svg':
            raise AssertionError(
                f'{label} {width}px: legacy auth logo asset active: {metrics["loginLogoPath"]}'
            )
        if metrics['loginLogoNaturalWidth'] < 300:
            raise AssertionError(
                f'{label} {width}px: auth logo source too small: {metrics["loginLogoNaturalWidth"]}'
            )
    if not metrics['h1']:
        raise AssertionError(f'{label} {width}px: page has no visible H1')



def _check_product_v2_shell(page, label: str, width: int) -> None:
    metrics = page.evaluate(
        """() => {
          const logo = document.querySelector('.pmv2-brand img');
          const header = document.querySelector('.pmv2-header');
          const left = document.querySelector('#pmv2ConfigScroll');
          const right = document.querySelector('.pmv2-prompt-panel');
          const output = document.querySelector('#promptOutput');
          const optionSpan = document.querySelector('#audienceGrid .option > span');
          const optionInput = optionSpan?.previousElementSibling;
          const nextButton = document.querySelector('.pmv2-next');
          const promptActionButtons = [...document.querySelectorAll('.pmv2-prompt-panel > .actions .btn')];
          const styleOf = (el) => {
            if (!el) return null;
            const style = getComputedStyle(el);
            return {
              backgroundColor: style.backgroundColor,
              backgroundImage: style.backgroundImage,
              color: style.color,
              fontFamily: style.fontFamily,
            };
          };
          const optionRestStyle = styleOf(optionSpan);
          let optionSelectedStyle = null;
          if (optionSpan && optionInput && !optionInput.disabled) {
            const wasChecked = optionInput.checked;
            optionInput.checked = true;
            optionSelectedStyle = styleOf(optionSpan);
            optionInput.checked = wasChecked;
          }
          const headerRect = header?.getBoundingClientRect();
          const widest = [...document.querySelectorAll('body *')]
            .map(el => {
              const r = el.getBoundingClientRect();
              return {
                tag: el.tagName,
                cls: typeof el.className === 'string' ? el.className.slice(0,120) : '',
                id: el.id || '',
                left: Math.round(r.left),
                right: Math.round(r.right),
                width: Math.round(r.width),
              };
            })
            .filter(x => x.right > innerWidth + 1 || x.left < -1)
            .sort((a,b) => Math.max(b.right-innerWidth,-b.left) - Math.max(a.right-innerWidth,-a.left))
            .slice(0,8);
          return {
            innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            widest,
            logoPath: logo ? new URL(logo.src).pathname : '',
            logoNaturalWidth: logo?.naturalWidth || 0,
            headerLeft: headerRect?.left ?? -1,
            headerRight: headerRect?.right ?? -1,
            leftOverflowY: left ? getComputedStyle(left).overflowY : '',
            rightOverflowY: right ? getComputedStyle(right).overflowY : '',
            rightPosition: right ? getComputedStyle(right).position : '',
            outputOverflowY: output ? getComputedStyle(output).overflowY : '',
            optionRestStyle,
            optionSelectedStyle,
            nextButtonStyle: styleOf(nextButton),
            promptActionStyles: promptActionButtons.map(styleOf),
            nestedScroll: [left,output].filter(Boolean).some(el => (
              ['auto','scroll'].includes(getComputedStyle(el).overflowY)
              && el.scrollHeight > el.clientHeight + 2
            )),
          };
        }"""
    )
    if metrics['scrollWidth'] > metrics['innerWidth'] + 1:
        raise AssertionError(
            f'{label} {width}px: V2 horizontal overflow '
            f'{metrics["scrollWidth"]}>{metrics["innerWidth"]}; offenders={metrics["widest"]}'
        )
    if metrics['headerLeft'] < -1 or metrics['headerRight'] > metrics['innerWidth'] + 1:
        raise AssertionError(f'{label} {width}px: V2 header leaves viewport: {metrics}')
    if metrics['logoPath'] != '/static/brand/promptmaster-logo-clean.svg':
        raise AssertionError(f'{label} {width}px: V2 legacy logo active: {metrics["logoPath"]}')
    if metrics['logoNaturalWidth'] < 300:
        raise AssertionError(f'{label} {width}px: V2 logo source too small: {metrics["logoNaturalWidth"]}')
    if metrics['leftOverflowY'] != 'visible':
        raise AssertionError(f'{label} {width}px: left V2 column gained nested scrolling: {metrics}')
    if metrics['nestedScroll']:
        raise AssertionError(f'{label} {width}px: V2 config/textarea contains an unapproved nested scroll area: {metrics}')
    if width <= 1180:
        if metrics['rightPosition'] != 'relative' or metrics['rightOverflowY'] != 'visible':
            raise AssertionError(f'{label} {width}px: stacked prompt panel contract invalid: {metrics}')
    else:
        if metrics['rightPosition'] != 'sticky' or metrics['rightOverflowY'] not in {'auto','scroll'}:
            raise AssertionError(f'{label} {width}px: desktop prompt rail must stay sticky and bounded: {metrics}')
    if metrics['outputOverflowY'] not in {'hidden','clip','visible'}:
        raise AssertionError(f'{label} {width}px: prompt output gained its own scrollbar: {metrics}')

    # Visual regression guard for the exact 2026-09-24 screenshots:
    # legacy embedded CSS paints .option > span white and forces Verdana on
    # .btn. V2 must override the actual visible child and every prompt action.
    option_rest = metrics.get('optionRestStyle')
    option_selected = metrics.get('optionSelectedStyle')
    # Pro renders audience/focus options only after a task is selected. When
    # the control exists, verify both its resting and checked presentation.
    if option_rest and 'gradient' not in (option_rest.get('backgroundImage') or ''):
        raise AssertionError(
            f'{label} {width}px: V2 audience option still exposes legacy light surface: '
            f'{option_rest}'
        )
    if option_selected and 'gradient' not in (option_selected.get('backgroundImage') or ''):
        raise AssertionError(
            f'{label} {width}px: selected V2 option still exposes legacy light surface: '
            f'{option_selected}'
        )

    next_style = metrics.get('nextButtonStyle') or {}
    if 'Segoe UI' not in (next_style.get('fontFamily') or ''):
        raise AssertionError(
            f'{label} {width}px: V2 workflow button typography regressed: {next_style}'
        )

    prompt_actions = metrics.get('promptActionStyles') or []
    if len(prompt_actions) < 2:
        raise AssertionError(f'{label} {width}px: prompt action button set incomplete: {prompt_actions}')
    for action_style in prompt_actions:
        if 'gradient' not in (action_style.get('backgroundImage') or ''):
            raise AssertionError(
                f'{label} {width}px: flat prompt action button returned: {action_style}'
            )
        if 'Segoe UI' not in (action_style.get('fontFamily') or ''):
            raise AssertionError(
                f'{label} {width}px: prompt action button typography regressed: {action_style}'
            )


def _browser_register_verify_to_buy(
    page, base: str, *, customer_type: str, email: str, password: str,
    quantity: int, company_name: str = '',
) -> None:
    from urllib.parse import quote, urlencode

    import pyotp
    from django.core import signing
    from django.db import close_old_connections

    from apps.accounts.models import User
    from apps.accounts.views import EMAIL_VERIFY_SALT

    next_path = f'/portal/licenses/buy/?quantity={quantity}'
    response = page.goto(
        base + 'auth/register/?' + urlencode({'next': next_path}),
        wait_until='networkidle',
    )
    if not response or response.status != 200:
        raise AssertionError(f'registration page failed for {customer_type}')

    page.locator('select[name="customer_type"]').select_option(customer_type)
    company_row = page.locator('[data-company-field]')
    company_input = page.locator('input[name="company_name"]')
    if customer_type == 'private':
        if company_row.is_visible() or company_input.is_enabled():
            raise AssertionError('private registration exposes company-name field')
    else:
        if not company_row.is_visible() or not company_input.is_enabled():
            raise AssertionError('company registration hides company-name field')
        if company_input.get_attribute('required') is None:
            raise AssertionError('company registration does not require company name in browser')
    page.locator('input[name="first_name"]').fill('Browser')
    page.locator('input[name="last_name"]').fill(
        'Firma' if customer_type == 'company' else 'Privat'
    )
    page.locator('input[name="email"]').fill(email)
    page.locator('input[name="password"]').fill(password)
    if customer_type == 'company':
        page.locator('input[name="company_name"]').fill(company_name)
    page.locator('input[name="accept_terms"]').check()
    page.locator('input[name="accept_privacy"]').check()
    page.locator('button[type="submit"]').click()

    if customer_type == 'company':
        page.wait_for_url('**/auth/2fa/setup/**')
        secret = page.locator('#totpSecret').inner_text().strip()
        if not secret:
            raise AssertionError('company registration did not expose TOTP secret')
        page.locator('input[name="code"]').fill(pyotp.TOTP(secret).now())
        page.locator('button[type="submit"]').click()
        page.wait_for_selector('.recovery-codes')
        continue_button = page.locator('.result-actions a.btn.primary')
        if '/portal/licenses/buy/' not in (continue_button.get_attribute('href') or ''):
            raise AssertionError('company registration lost checkout destination after MFA')

    # Buying is blocked until e-mail verification; verify before checkout.
    page.wait_for_load_state('networkidle')

    def _verification_token():
        close_old_connections()
        user = User.objects.get(email=email)
        value = signing.dumps(
            {'uid': str(user.id), 'email': user.email, 'next': next_path},
            salt=EMAIL_VERIFY_SALT,
        )
        close_old_connections()
        return value

    with ThreadPoolExecutor(max_workers=1) as pool:
        token = pool.submit(_verification_token).result()
    verify = page.goto(
        base + 'auth/verify/' + quote(token, safe='') + '/',
        wait_until='networkidle',
    )
    if not verify or verify.status != 200:
        raise AssertionError(f'email verification route failed for {email}')
    if not page.locator('.result-actions a.btn.primary').is_visible():
        raise AssertionError(f'verification result has no continue action for {email}')
    verification_continue = page.locator('.result-actions a.btn.primary')
    verification_continue.evaluate("(el) => el.click()")
    page.wait_for_url(
        lambda url: '/portal/licenses/buy/' in str(url),
        wait_until='domcontentloaded',
        timeout=15000,
    )
    page.wait_for_load_state('domcontentloaded')

    def _is_verified():
        close_old_connections()
        verified = bool(User.objects.get(email=email).email_verified_at)
        close_old_connections()
        return verified

    with ThreadPoolExecutor(max_workers=1) as pool:
        verified = pool.submit(_is_verified).result()
    if not verified:
        raise AssertionError(f'email verification was not persisted for {email}')
    quantity_field = page.locator('input[name="quantity"]')
    if not quantity_field.is_visible() or quantity_field.input_value() != str(quantity):
        raise AssertionError(
            f'registration checkout quantity drift for {email}: '
            f'{quantity_field.input_value() if quantity_field.count() else "missing"}'
        )
    for name in ('accept_terms', 'accept_privacy'):
        if not page.locator(f'input[name="{name}"]').is_visible():
            raise AssertionError(f'checkout legal acceptance missing after registration: {name}')


def run_backend_ui_smoke(browser, fixture=None) -> None:
    if os.getenv('BACKEND_UI_BROWSER_SMOKE') != '1':
        return
    if fixture is None:
        raise AssertionError('Backend browser fixture was not prepared before Playwright startup')

    import subprocess
    import sys

    port = _free_port()
    base = f'http://127.0.0.1:{port}/'
    env = os.environ.copy()
    env.setdefault('ENVIRONMENT', 'development')
    env.setdefault('ALLOWED_HOSTS', '127.0.0.1,localhost')
    env.setdefault('SESSION_COOKIE_SECURE', '0')
    env.setdefault('CSRF_COOKIE_SECURE', '0')

    process = subprocess.Popen(
        [sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
        cwd=str(ROOT / 'backend'),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_http(base + 'health/live/', process)

        public_context = browser.new_context(viewport={'width': 1440, 'height': 900})
        public_page = public_context.new_page()
        public_routes = [
            ('auth/login/', 'Login'),
            ('auth/register/', 'Registrierung'),
            ('auth/password-reset/', 'Passwortreset'),
            ('legal/terms/', 'AGB'),
            ('legal/privacy/', 'Datenschutz'),
        ]
        for width in (360, 390, 768, 1440, 1920):
            for route, label in public_routes:
                _check_public_page(public_page, base, route, width, label)

        # Real browser registration acceptance for both supported customer types.
        for registration in (
            {
                'customer_type': 'private',
                'email': 'browser-register-private@example.invalid',
                'quantity': 1,
                'company_name': '',
            },
            {
                'customer_type': 'company',
                'email': 'browser-register-company@example.invalid',
                'quantity': 3,
                'company_name': 'Browser Registration GmbH',
            },
        ):
            registration_context = browser.new_context(
                viewport={'width': 1440, 'height': 1000}
            )
            registration_page = registration_context.new_page()
            _browser_register_verify_to_buy(
                registration_page,
                base,
                customer_type=registration['customer_type'],
                email=registration['email'],
                password='Browser-Registration-Password-42!',
                quantity=registration['quantity'],
                company_name=registration['company_name'],
            )
            registration_context.close()

        # FREE keeps its reviewed 16-task local logic but must expose the same
        # complete 34-app catalog as PRO, with the other 28 apps visibly locked.
        public_page.set_viewport_size({'width': 1440, 'height': 1000})
        free_response = public_page.goto(base + 'free/', wait_until='domcontentloaded')
        if not free_response or free_response.status != 200:
            raise AssertionError('Free runtime: HTTP 200 expected')
        public_page.wait_for_function(
            "document.querySelectorAll('[data-appwrap]').length === 34",
            timeout=15000,
        )
        free_catalog = public_page.evaluate(
            """() => ({
              total: document.querySelectorAll('[data-appwrap]').length,
              base: document.querySelectorAll('[data-appwrap][data-prolocked="0"]').length,
              locked: document.querySelectorAll('[data-appwrap][data-prolocked="1"]').length,
              freeTasks: Object.values(APP).flatMap(a => a.tasks || []).filter(t => t[3] === 'free').length,
              hasPowerAutomate: !!document.querySelector('[data-central-code="power_automate"]'),
              hasGithubCopilot: !!document.querySelector('[data-central-code="github_copilot"]'),
              bridgeLoaded: performance.getEntriesByType('resource')
                .some(r => r.name.includes('/static/js/free_catalog_bridge.20260918.js')),
            })"""
        )
        if free_catalog != {
            'total': 34,
            'base': 6,
            'locked': 28,
            'freeTasks': 16,
            'hasPowerAutomate': True,
            'hasGithubCopilot': True,
            'bridgeLoaded': True,
        }:
            raise AssertionError(f'Free runtime catalog contract drift: {free_catalog}')

        public_page.wait_for_function("document.body.classList.contains('pmv2')")
        v2_free_layout = public_page.evaluate(
            """() => {
              const left = document.querySelector('#pmv2ConfigScroll');
              const right = document.querySelector('.pmv2-prompt-panel');
              const logo = document.querySelector('.pmv2-brand img');
              const freeApps = document.querySelector('#freeApps');
              const toggle = document.querySelector('.pmv2-pro-toggle');
              const firstLicense = document.querySelector('.license-option > span');
              const flow7 = document.querySelector('.pmv2-flow-step[data-pmv2-step="7"] span');
              const firstFreeCopy = document.querySelector('#freeApps .app-copy');
              const firstFreeFooter = document.querySelector('#freeApps .app-footer');
              return {
                left: !!left,
                right: !!right,
                logoPath: logo ? new URL(logo.src).pathname : '',
                logoNaturalWidth: logo?.naturalWidth || 0,
                bodyOverflowY: getComputedStyle(document.body).overflowY,
                rootScrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
                leftOverflowY: left ? getComputedStyle(left).overflowY : '',
                rightOverflowY: right ? getComputedStyle(right).overflowY : '',
                rightPosition: right ? getComputedStyle(right).position : '',
                rightHeight: right?.getBoundingClientRect().height ?? 0,
                toggleAfterFreeApps: !!(freeApps && toggle && freeApps.nextElementSibling === toggle),
                flow7Text: flow7?.textContent?.trim() || '',
                licenseBackground: firstLicense ? getComputedStyle(firstLicense).backgroundColor : '',
                freeCopyDisplay: firstFreeCopy ? getComputedStyle(firstFreeCopy).display : '',
                freeFooterDisplay: firstFreeFooter ? getComputedStyle(firstFreeFooter).display : '',
              };
            }"""
        )
        if (
            not v2_free_layout['left']
            or not v2_free_layout['right']
            or v2_free_layout['logoPath'] != '/static/brand/promptmaster-logo-clean.svg'
            or v2_free_layout['logoNaturalWidth'] < 300
            or v2_free_layout['bodyOverflowY'] not in {'auto', 'scroll'}
            or v2_free_layout['rootScrollBehavior'] != 'auto'
            or v2_free_layout['leftOverflowY'] != 'visible'
            or v2_free_layout['rightOverflowY'] not in {'auto', 'scroll'}
            or v2_free_layout['rightPosition'] != 'sticky'
            or v2_free_layout['rightHeight'] < 300
            or not v2_free_layout['toggleAfterFreeApps']
            or v2_free_layout['flow7Text'] != 'Prompt-Check'
            or v2_free_layout['freeCopyDisplay'] != 'none'
            or v2_free_layout['freeFooterDisplay'] != 'none'
            or v2_free_layout['licenseBackground'] not in {'rgba(0, 0, 0, 0)', 'transparent'}
        ):
            raise AssertionError(f'Free V2 approved desktop shell invalid: {v2_free_layout}')

        single_scroll_probe = public_page.evaluate(
            """async () => {
              const left = document.querySelector('#pmv2ConfigScroll');
              const right = document.querySelector('.pmv2-prompt-panel');
              window.scrollTo(0, 0);
              await new Promise(resolve => setTimeout(resolve, 40));
              const beforeTop = right.getBoundingClientRect().top;
              const maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);
              const targetY = Math.min(700, maxScroll);
              window.scrollTo(0, targetY);
              await new Promise(resolve => setTimeout(resolve, 100));
              const afterTop = right.getBoundingClientRect().top;
              const expectedTop = Math.max(18, beforeTop - scrollY);
              return {
                windowY: scrollY,
                maxScroll,
                targetY,
                beforeTop,
                afterTop,
                expectedTop,
                stickyError: Math.abs(afterTop - expectedTop),
                leftTop: left.scrollTop,
                rightTop: right.scrollTop,
                rightPosition: getComputedStyle(right).position,
              };
            }"""
        )
        if (
            single_scroll_probe['leftTop'] >= 3
            or single_scroll_probe['rightTop'] >= 3
            or single_scroll_probe['rightPosition'] != 'sticky'
            or abs(single_scroll_probe['windowY'] - single_scroll_probe['targetY']) > 3
            or single_scroll_probe['afterTop'] < 17
            or single_scroll_probe['stickyError'] > 5
        ):
            raise AssertionError(f'Free V2 must use one browser scrollbar with sticky prompt: {single_scroll_probe}')

        public_page.locator('#resetBtn').click()
        public_page.wait_for_timeout(500)
        reset_probe = public_page.evaluate(
            """() => {
              const left = document.querySelector('#pmv2ConfigScroll');
              return {
                leftTop: left?.scrollTop ?? -1,
                windowY: scrollY,
                hasConfig: !!left,
              };
            }"""
        )
        if (
            not reset_probe['hasConfig']
            or reset_probe['leftTop'] >= 3
            or reset_probe['windowY'] >= 3
        ):
            raise AssertionError(f'Free V2 reset did not return to top: {reset_probe}')

        # Current Free must generate the authoritative prompt through the
        # database-backed PromptLegacyContract API, not the embedded JS composer.
        if public_page.locator('body').get_attribute('data-pm-free-compose') != 'server':
            raise AssertionError('Free V2 database compose mode is not active')
        public_page.locator('[data-appwrap="chat"]').click()
        public_page.wait_for_function(
            "() => !document.querySelector('#taskSection')?.classList.contains('hidden')"
        )
        public_page.locator('[data-task="chat_sum"]').click()
        public_page.wait_for_function(
            "() => !document.querySelector('#contextSection')?.classList.contains('hidden')"
        )
        public_page.locator('#goalInput').fill('Kernaussagen und nächste Schritte')
        public_page.locator('#sourceContextInput').fill('Browser-Free-DB-Probe')
        public_page.locator('input[name="audience"][value="self"]').check(force=True)
        public_page.locator('input[name="focus"][value="Kernaussagen"]').check(force=True)
        public_page.locator('#detailSelect').select_option('short')
        public_page.locator('#formatSelect').select_option('bullets')
        public_page.locator('#toneSelect').select_option('professional')
        public_page.wait_for_function(
            """() => {
              const output=document.querySelector('#promptOutput');
              return output?.dataset.source==='database'
                && output.value.includes('Browser-Free-DB-Probe')
                && document.querySelector('#promptStatus')?.textContent==='PROMPT BEREIT'
                && document.querySelector('#copyBtn')?.disabled===false;
            }""",
            timeout=10000,
        )
        free_db_probe = public_page.evaluate(
            """() => ({
              source: document.querySelector('#promptOutput')?.dataset.source || '',
              prompt: document.querySelector('#promptOutput')?.value || '',
              copyState: document.querySelector('#copyState')?.textContent || '',
            })"""
        )
        if (
            free_db_probe['source'] != 'database'
            or 'Browser-Free-DB-Probe' not in free_db_probe['prompt']
            or 'Aus Prompt-Datenbank erstellt' not in free_db_probe['copyState']
        ):
            raise AssertionError(
                f'Free V2 did not render database-composed prompt: {free_db_probe}'
            )
        public_page.locator('#resetBtn').click()
        public_page.wait_for_timeout(250)

        pro_toggle = public_page.locator('.pmv2-pro-toggle')
        if not pro_toggle.is_visible():
            raise AssertionError('Free V2: Pro-app expand control missing')
        pro_toggle.click()
        public_page.wait_for_function(
            "() => !document.querySelector('.pmv2-free-pro-block')?.hidden"
        )
        visible_locked = public_page.locator(
            '.pmv2-free-pro-block [data-prolocked="1"]'
        ).count()
        if visible_locked != 28:
            raise AssertionError(f'Free V2: expected 28 expanded Pro apps, got {visible_locked}')

        public_page.locator('[data-central-code="power_automate"] .app-card').click()
        public_page.wait_for_function(
            "document.querySelector('#proModal')?.classList.contains('open')"
        )
        if 'Power Automate' not in public_page.locator('#proModal').inner_text():
            raise AssertionError('Free runtime: locked app does not open its Pro explanation')
        pro_modal_text = public_page.locator('#proModal').inner_text()
        if 'CopilotPromptMaster' in pro_modal_text:
            raise AssertionError(f'Free V2 Pro modal exposes legacy brand naming: {pro_modal_text}')
        if 'PromptMaster Pro anfragen' not in pro_modal_text:
            raise AssertionError('Free V2 Pro modal CTA is not normalized')

        public_page.locator('[data-close="proModal"]').first.click()

        word_wrap = public_page.locator('[data-appwrap="word"]')
        if (
            word_wrap.get_attribute('role') != 'button'
            or word_wrap.get_attribute('tabindex') != '0'
        ):
            raise AssertionError('Free V2 license-locked Word card is not keyboard interactive')
        word_wrap.scroll_into_view_if_needed()
        word_wrap.focus()
        public_page.keyboard.press('Enter')
        public_page.wait_for_function(
            "document.querySelector('#businessModal')?.classList.contains('open')"
        )
        license_modal = public_page.locator('#businessModal')
        license_modal_text = license_modal.inner_text()
        if 'Copilot Business anfragen' in license_modal_text:
            raise AssertionError(
                f'Free V2 Microsoft-license modal exposes factually wrong CTA: {license_modal_text}'
            )
        tier_switch_text = license_modal.locator('#switchBusinessBtn').inner_text().strip()
        tier_contact_text = license_modal.locator(
            '.modal-actions a[href*="netstyle.de/kontakt"]'
        ).inner_text().strip()
        expected_tier_contact = (
            tier_switch_text[:-len(' auswählen')] + ' anfragen'
            if tier_switch_text.endswith(' auswählen')
            else ''
        )
        if not expected_tier_contact or tier_contact_text != expected_tier_contact:
            raise AssertionError(
                'Free V2 Microsoft-license CTA does not match required tier: '
                f'{tier_contact_text!r} != {expected_tier_contact!r}'
            )
        public_page.locator('[data-close="businessModal"]').first.click()

        public_page.locator('[data-appwrap="chat"] .app-card').click()
        public_page.wait_for_function(
            "document.querySelectorAll('#taskGrid .task').length >= 2"
        )
        public_page.wait_for_timeout(450)
        app_scroll_probe = public_page.evaluate(
            """() => {
              const rect = document.querySelector('#taskSection').getBoundingClientRect();
              const docTop = rect.top + scrollY;
              const maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);
              const expectedWindowY = Math.min(Math.max(0, docTop - 18), maxScroll);
              const expectedTop = docTop - expectedWindowY;
              return {
                top: rect.top,
                windowY: scrollY,
                docTop,
                maxScroll,
                expectedWindowY,
                expectedTop,
              };
            }"""
        )
        if (
            abs(app_scroll_probe['top'] - app_scroll_probe['expectedTop']) > 6
            or abs(app_scroll_probe['windowY'] - app_scroll_probe['expectedWindowY']) > 6
            or app_scroll_probe['windowY'] < 10
        ):
            raise AssertionError(f'Free V2 app -> task page autoscroll missed target: {app_scroll_probe}')

        public_page.locator('#taskGrid .task[data-prolocked="0"]').first.click()
        public_page.wait_for_timeout(450)
        task_scroll_probe = public_page.evaluate(
            """() => {
              const rect = document.querySelector('#contextSection').getBoundingClientRect();
              const docTop = rect.top + scrollY;
              const maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);
              const expectedWindowY = Math.min(Math.max(0, docTop - 18), maxScroll);
              const expectedTop = docTop - expectedWindowY;
              return {
                top: rect.top,
                windowY: scrollY,
                docTop,
                maxScroll,
                expectedWindowY,
                expectedTop,
              };
            }"""
        )
        if (
            abs(task_scroll_probe['top'] - task_scroll_probe['expectedTop']) > 6
            or abs(task_scroll_probe['windowY'] - task_scroll_probe['expectedWindowY']) > 6
            or task_scroll_probe['windowY'] < 10
        ):
            raise AssertionError(f'Free V2 task -> context page autoscroll missed target: {task_scroll_probe}')

        context_scroll_before = public_page.evaluate('scrollY')
        public_page.locator('#sourceContextInput').click()
        public_page.wait_for_timeout(180)
        context_scroll_after = public_page.evaluate('scrollY')
        if abs(context_scroll_after - context_scroll_before) > 3:
            raise AssertionError(
                'Free V2 focusing the second context field moved the page: '
                f'{context_scroll_before} -> {context_scroll_after}'
            )
        usable_chat_tasks = public_page.locator(
            '#taskGrid .task[data-prolocked="0"]'
        ).count()
        if usable_chat_tasks != 2:
            raise AssertionError(
                f'Free runtime: expected 2 usable Copilot Chat tasks, got {usable_chat_tasks}'
            )
        expected_free_counts = {
            'chat': 2, 'outlook': 6, 'teams': 2,
            'word': 2, 'excel': 2, 'powerpoint': 2,
        }
        selected_tier = public_page.evaluate(
            "() => document.querySelector('input[name=mslicense]:checked')?.value || ''"
        )
        # Task contracts are independent of the selected Microsoft tier. Apps
        # may be Microsoft-license-locked, but their reviewed Free task mapping
        # must remain exactly 16 across the six base applications.
        free_counts = public_page.evaluate(
            """() => Object.fromEntries(
              ['chat','outlook','teams','word','excel','powerpoint'].map(id => [
                id, (APP[id]?.tasks || []).filter(t => t[3] === 'free').length
              ])
            )"""
        )
        if free_counts != expected_free_counts:
            raise AssertionError(
                f'Free runtime task mapping drift ({selected_tier}): {free_counts}'
            )

        for width, height in ((360,800),(390,844),(768,1024),(1440,1000),(1920,1080)):
            public_page.set_viewport_size({'width': width, 'height': height})
            response = public_page.goto(base + 'free/', wait_until='networkidle')
            if not response or response.status != 200:
                raise AssertionError(f'Free V2 responsive shell {width}px: HTTP failure')
            public_page.wait_for_function("document.body.classList.contains('pmv2')")
            _check_product_v2_shell(public_page, 'Free V2 responsive shell', width)

        public_context.close()

        portal_routes = [
            ('portal/dashboard/', 'Portal Dashboard'),
            ('portal/search/?q=PM-BROWSER-ACTIVE', 'Portal Suche'),
            ('portal/more/', 'Portal Mehr'),
            ('portal/team/', 'Portal Team'),
            ('portal/team/invitations/', 'Portal Einladungen'),
            ('portal/team/invite/', 'Portal Einladung erstellen'),
            (f'portal/team/{fixture["member_id"]}/', 'Portal Teammitglied'),
            ('portal/licenses/', 'Portal Lizenzen'),
            ('portal/licenses/buy/', 'Portal Lizenzkauf'),
            ('portal/licenses/renew/', 'Portal Verlängerungsübersicht'),
            (f'portal/licenses/{fixture["license_id"]}/', 'Portal Lizenzdetail'),
            (f'portal/licenses/{fixture["license_id"]}/renew/', 'Portal Lizenz verlängern'),
            ('portal/devices/', 'Portal Geräte'),
            ('portal/orders/', 'Portal Bestellungen'),
            ('portal/company/', 'Portal Unternehmen'),
            ('portal/profile/', 'Portal Einstellungen'),
            ('portal/security/', 'Portal Sicherheit'),
            ('portal/help/', 'Portal Hilfe'),
        ]
        admin_routes = [
            ('ns-admin/', 'Admin Dashboard'),
            ('ns-admin/search/?q=PM-BROWSER', 'Admin Suche'),
            ('ns-admin/more/', 'Admin Mehr'),
            ('ns-admin/customers/', 'Admin Kunden'),
            ('ns-admin/customers/private/', 'Admin Privatkunden'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/', 'Admin Privatkundendetail'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/portal-preview/', 'Admin Privatkunden-Portalvorschau'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/licenses/', 'Admin Privatkundenlizenzen'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/devices/', 'Admin Privatkundengeräte'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/orders/', 'Admin Privatkundenbestellungen'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/payments/', 'Admin Privatkundenzahlungen'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/emails/', 'Admin Privatkunden-E-Mails'),
            (f'ns-admin/customers/private/{fixture["private_customer_id"]}/audit/', 'Admin Privatkundenaudit'),
            (f'ns-admin/customers/{fixture["company_id"]}/', 'Admin Kundendetail'),
            (f'ns-admin/customers/{fixture["company_id"]}/company/', 'Admin Unternehmen'),
            (f'ns-admin/customers/{fixture["company_id"]}/portal-preview/', 'Admin Portalvorschau'),
            (f'ns-admin/customers/{fixture["company_id"]}/users/', 'Admin Kundenbenutzer'),
            (f'ns-admin/customers/{fixture["company_id"]}/licenses/', 'Admin Kundenlizenzen'),
            (f'ns-admin/customers/{fixture["company_id"]}/devices/', 'Admin Kundengeräte'),
            (f'ns-admin/customers/{fixture["company_id"]}/orders/', 'Admin Kundenbestellungen'),
            (f'ns-admin/customers/{fixture["company_id"]}/payments/', 'Admin Kundenzahlungen'),
            (f'ns-admin/customers/{fixture["company_id"]}/emails/', 'Admin Kunden-E-Mails'),
            (f'ns-admin/customers/{fixture["company_id"]}/privacy/', 'Admin Kundendatenschutz'),
            (f'ns-admin/customers/{fixture["company_id"]}/audit/', 'Admin Kundenaudit'),
            ('ns-admin/licenses/', 'Admin Lizenzen'),
            (f'ns-admin/licenses/{fixture["license_id"]}/', 'Admin Lizenzdetail'),
            ('ns-admin/orders/', 'Admin Bestellungen'),
            (f'ns-admin/orders/{fixture["order_id"]}/', 'Admin Bestelldetail'),
            ('ns-admin/payments/', 'Admin Zahlungen'),
            ('ns-admin/products/', 'Admin Produkte'),
            (f'ns-admin/products/{fixture["product_id"]}/', 'Admin Produktdetail'),
            ('ns-admin/products/features/', 'Admin Produktmerkmale'),
            ('ns-admin/email/', 'Admin E-Mail'),
            ('ns-admin/email/log/', 'Admin E-Mail-Protokoll'),
            ('ns-admin/mollie/', 'Admin Mollie'),
            ('ns-admin/mollie/events/', 'Admin Mollie-Ereignisse'),
            ('ns-admin/statistics/', 'Admin Statistik'),
            ('ns-admin/ops/', 'Admin System'),
            ('ns-admin/ops/services/', 'Admin Dienste'),
            ('ns-admin/ops/database/', 'Admin Datenbank'),
            ('ns-admin/ops/backups/', 'Admin Backups'),
            ('ns-admin/ops/restore-tests/', 'Admin Restore-Tests'),
            ('ns-admin/ops/alerts/', 'Admin Systemmeldungen'),
            ('ns-admin/api/', 'Admin API'),
            ('ns-admin/legal/', 'Admin Recht'),
            ('ns-admin/legal/documents/', 'Admin Rechtsdokumente'),
            ('ns-admin/legal/retention/', 'Admin Aufbewahrung'),
            ('ns-admin/legal/deletions/', 'Admin Löschanfragen'),
            ('ns-admin/support/', 'Admin Support'),
            ('ns-admin/audit/', 'Admin Audit'),
            ('ns-admin/roles/', 'Admin Rollen'),
            ('ns-admin/settings/', 'Admin Einstellungen'),
            ('ns-admin/prompt-studio/', 'Prompt Studio'),
            ('ns-admin/prompt-studio/quality/', 'Prompt Qualität'),
            (f'ns-admin/prompt-studio/{fixture["task_id"]}/', 'Prompt Definition'),
            (f'ns-admin/prompt-studio/version/{fixture["version_id"]}/', 'Prompt Version'),
            ('ns-admin/content/faqs/', 'Admin FAQ'),
        ]

        # One public login serves ordinary customer users too. A company member
        # without a Pro seat must land in the customer portal, must not see a
        # Pro launch link, and must never enter the netstyle security domain.
        member_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        member_page = member_context.new_page()
        _browser_login_password_only(
            member_page,
            base,
            fixture['member_email'],
            fixture['password'],
            '/portal/dashboard/',
        )
        member_page.goto(base + 'portal/more/', wait_until='networkidle')
        member_hrefs = set(member_page.locator('.content a').evaluate_all(
            "els => els.map(e => new URL(e.href).pathname)"
        ))
        if '/pro/' in member_hrefs:
            raise AssertionError('unlicensed company member sees a Pro launch link')
        forbidden_admin = member_page.goto(base + 'ns-admin/', wait_until='networkidle')
        if not forbidden_admin or forbidden_admin.status != 403:
            raise AssertionError('customer member can enter the netstyle admin domain')
        member_context.close()

        # First-time netstyle admin MFA must finish inside the admin backend,
        # never on the public marketing page or in the customer portal.
        first_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        first_page = first_context.new_page()
        first_page.goto(base + 'auth/login/', wait_until='networkidle')
        first_page.locator('input[name="email"]').fill(fixture['first_time_admin_email'])
        first_page.locator('input[name="password"]').fill(fixture['password'])
        first_page.locator('input[name="password"]').press('Enter')
        first_page.wait_for_url('**/auth/2fa/setup/**')
        setup_logo = first_page.locator('.login-logo img')
        if '/static/brand/promptmaster-logo-clean.svg' not in setup_logo.get_attribute('src'):
            raise AssertionError('first-time MFA still uses the low-resolution logo asset')
        if first_page.locator('[data-copy-target]').count() != 2:
            raise AssertionError('first-time MFA copy controls missing')
        secret = first_page.locator('#totpSecret').inner_text().strip()
        import pyotp
        first_page.locator('input[name="code"]').fill(pyotp.TOTP(secret).now())
        first_page.locator('input[name="code"]').press('Enter')
        first_page.wait_for_selector('.recovery-codes')
        continue_button = first_page.locator('.result-actions a.btn.primary')
        if 'netstyle Admin-Backend' not in continue_button.inner_text():
            raise AssertionError('first-time staff MFA exposes the wrong continuation label')
        if continue_button.get_attribute('href') != '/ns-admin/':
            raise AssertionError('first-time staff MFA does not continue to /ns-admin/')
        continue_button.evaluate("(el) => el.click()")
        first_page.wait_for_url(
            '**/ns-admin/',
            wait_until='domcontentloaded',
            timeout=15000,
        )
        first_page.wait_for_load_state('domcontentloaded')
        if '/ns-admin/' not in first_page.url:
            raise AssertionError('first-time staff MFA did not enter the netstyle backend')
        first_context.close()

        # Real demo identities: exercise every generated login credential through
        # the browser. Privileged identities perform first-time MFA enrollment;
        # customer members/private customers land according to their actual
        # seeded entitlement state. This catches broken post-login routing that
        # route-only smoke tests cannot see.
        demo_credentials = fixture['demo_credentials']
        demo_login_expectations = {}
        for email, meta in demo_credentials.items():
            if email.startswith('demo.superadmin') or email.startswith('demo.support') or email.startswith('demo.ops') or email.startswith('demo.prompts'):
                demo_login_expectations[email] = ('mfa', '/ns-admin/')
            elif '.admin@promptmaster.invalid' in email:
                demo_login_expectations[email] = ('mfa', '/portal/dashboard/')
            elif email.startswith('demo.privat1@') or email.startswith('demo.privat2@'):
                demo_login_expectations[email] = ('password', '/pro/')
            elif email.startswith('demo.privat3@'):
                demo_login_expectations[email] = ('password', '/portal/dashboard/')
            else:
                # Seeded company users with an assigned seat launch Pro; the
                # last login user of each company is intentionally unlicensed.
                demo_login_expectations[email] = (
                    'password',
                    '/portal/dashboard/' if 'ohne PRO-Lizenz' in meta['note'] else '/pro/',
                )

        if len(demo_login_expectations) != 26:
            raise AssertionError(
                f'demo browser login matrix incomplete: {len(demo_login_expectations)} identities'
            )

        for demo_index, email in enumerate(sorted(demo_login_expectations), start=1):
            mode, expected = demo_login_expectations[email]
            # Login throttling is intentionally per client IP (10 attempts /
            # 5 minutes). This acceptance suite represents 26 independent demo
            # people, not a brute-force attack from one workstation. Give each
            # browser context its own TEST-NET-style client address so the
            # production throttle remains active and is not weakened just to
            # make the test pass.
            context = browser.new_context(
                viewport={'width': 1440, 'height': 1000},
                extra_http_headers={
                    'X-Forwarded-For': f'198.18.1.{demo_index}',
                },
            )
            page = context.new_page()
            if mode == 'mfa':
                _browser_first_time_mfa_login(
                    page, base, email, demo_credentials[email]['password'], expected
                )
            else:
                _browser_login_password_only(
                    page, base, email, demo_credentials[email]['password'], expected
                )
            if expected == '/ns-admin/':
                if page.goto(base + 'ns-admin/', wait_until='networkidle').status != 200:
                    raise AssertionError(f'demo netstyle identity cannot open dashboard: {email}')
            elif expected == '/portal/dashboard/':
                if page.goto(base + 'portal/dashboard/', wait_until='networkidle').status != 200:
                    raise AssertionError(f'demo portal identity cannot open dashboard: {email}')
            else:
                pro_response = page.goto(base + 'pro/', wait_until='networkidle')
                if not pro_response or pro_response.status != 200:
                    raise AssertionError(f'demo licensed identity cannot enter Pro: {email}')
            context.close()

        for role, email, secret, routes in (
            ('portal', fixture['customer_email'], fixture['customer_secret'], portal_routes),
            ('admin', fixture['admin_email'], fixture['admin_secret'], admin_routes),
        ):
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            page_errors = []
            bad_responses = []
            page.on('pageerror', lambda exc, target=page_errors: target.append(str(exc)))
            page.on(
                'response',
                lambda response, target=bad_responses: (
                    target.append(f'{response.status} {response.url}')
                    if response.status >= 400 and response.url.startswith(base)
                    else None
                ),
            )

            _browser_login(
                page, base, email, fixture['password'], secret,
                '/portal/dashboard/' if role == 'portal' else '/ns-admin/',
            )

            if role == 'admin':
                admin_logo = page.locator('.sidebar .brand img')
                if '/static/brand/promptmaster-logo-clean.svg' not in admin_logo.get_attribute('src'):
                    raise AssertionError('admin shell still uses the low-resolution logo asset')

                page.goto(
                    base + f'ns-admin/customers/{fixture["company_id"]}/devices/',
                    wait_until='networkidle',
                )
                native_dialogs = []
                def _capture_native_dialog(dialog):
                    native_dialogs.append(dialog.message)
                    dialog.dismiss()
                page.on('dialog', _capture_native_dialog)
                revoke_button = page.locator('form[action*="/revoke/"] button').first
                if revoke_button.count() != 1:
                    raise AssertionError('admin device revoke action missing for confirmation UI test')
                revoke_button.click()
                page.wait_for_timeout(100)
                if native_dialogs:
                    raise AssertionError(f'admin still opens browser-native confirm dialog: {native_dialogs}')
                confirm_backdrop = page.locator('.pm-confirm-backdrop:not([hidden])')
                if confirm_backdrop.count() != 1 or 'Gerätezugang wirklich widerrufen' not in confirm_backdrop.inner_text():
                    raise AssertionError('admin branded confirmation dialog did not open for device revoke')
                confirm_backdrop.locator('[data-confirm-cancel]').click()
                if page.locator('.pm-confirm-backdrop:not([hidden])').count():
                    raise AssertionError('admin branded confirmation dialog did not close')

                page.goto(
                    base + f'ns-admin/licenses/{fixture["license_id"]}/',
                    wait_until='networkidle',
                )
                action_row = page.locator('.card-action-row').first
                if action_row.count() != 1:
                    raise AssertionError('admin license destructive action spacing wrapper missing')
                spacing = action_row.evaluate(
                    """el => {
                      const previous = el.previousElementSibling;
                      if (!previous) return -1;
                      return el.getBoundingClientRect().top - previous.getBoundingClientRect().bottom;
                    }"""
                )
                if spacing < 10:
                    raise AssertionError(f'admin license destructive action has insufficient spacing: {spacing}')

            if role == 'portal':
                page.goto(base + 'portal/profile/', wait_until='networkidle')
                profile_labels = set(page.locator('label').all_text_contents())
                flattened_labels = ' '.join(profile_labels)
                for german_label in ('Vorname', 'Nachname'):
                    if german_label not in flattened_labels:
                        raise AssertionError(
                            f'portal profile: German label missing: {german_label}'
                        )
                if any(token in flattened_labels for token in ('street', 'house_number', 'postal_code')):
                    raise AssertionError(
                        f'portal profile: raw English/internal address labels visible: {flattened_labels}'
                    )

                company_response = page.goto(base + 'portal/company/', wait_until='networkidle')
                if company_response and company_response.status == 200:
                    company_labels = ' '.join(page.locator('label').all_text_contents())
                    for german_label in ('Firmenname', 'Telefon', 'Straße', 'Hausnummer', 'PLZ', 'Ort', 'Land'):
                        if german_label not in company_labels:
                            raise AssertionError(
                                f'portal company: German label missing: {german_label}'
                            )
                    if any(token in company_labels for token in ('phone', 'street', 'house_number', 'postal_code', 'city', 'country')):
                        raise AssertionError(
                            f'portal company: raw English/internal labels visible: {company_labels}'
                        )

                page.goto(base + 'portal/dashboard/', wait_until='networkidle')
                search_input = page.locator('.topbar .search input')
                if not search_input.is_visible():
                    raise AssertionError('portal: desktop global search input is not visible')
                search_input.fill('PM-BROWSER-ACTIVE')
                search_input.press('Enter')
                page.wait_for_url(lambda url: '/portal/search/' in str(url))
                if 'PM-BROWSER-ACTIVE' not in page.locator('body').inner_text():
                    raise AssertionError('portal: global search did not return the visible tenant license')

                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(base + 'portal/more/', wait_until='networkidle')
                hrefs = set(page.locator('.content a').evaluate_all(
                    "els => els.map(e => new URL(e.href).pathname)"
                ))
                expected = {
                    '/portal/search/', '/portal/profile/', '/portal/security/', '/portal/help/',
                    '/auth/logout/', '/portal/licenses/buy/', '/portal/orders/', '/portal/company/',
                    '/pro/',
                }
                missing = sorted(expected - hrefs)
                if missing:
                    raise AssertionError(f'portal mobile More navigation missing: {missing}')

                page.set_viewport_size({'width': 1440, 'height': 1000})
                customer_pro = page.goto(base + 'pro/', wait_until='networkidle')
                if not customer_pro or customer_pro.status != 200:
                    raise AssertionError('licensed customer admin cannot reach PromptMaster Pro flow')
                if '/pro/device/register/' not in page.url:
                    raise AssertionError(
                        f'new customer browser did not enter device registration: {page.url}'
                    )
                device_name = page.locator('input[name="display_name"]')
                if not device_name.is_visible():
                    raise AssertionError('PromptMaster Pro device registration form is missing')
                device_name.fill('Browser Smoke Firefox/Edge')
                device_name.press('Enter')
                page.wait_for_url('**/pro/app/')
                page.wait_for_load_state('networkidle')

                page.wait_for_function("document.body.classList.contains('pmv2')")
                customer_utility_paths = set(page.locator('.pmv2-header-actions a').evaluate_all(
                    "els => els.map(e => new URL(e.href).pathname)"
                ))
                required_customer_utility = {'/portal/dashboard/', '/auth/logout/'}
                if not required_customer_utility.issubset(customer_utility_paths):
                    raise AssertionError(
                        'customer Pro V2 session navigation missing: '
                        f'{sorted(required_customer_utility - customer_utility_paths)}'
                    )

                page.wait_for_function(
                    "document.querySelectorAll('#catalog .app-card').length === 34"
                )
                direct_pro_apps = page.locator('#catalog .app-card').count()
                if direct_pro_apps != 34:
                    raise AssertionError(
                        f'PromptMaster Pro V2 must expose all 34 apps directly, got {direct_pro_apps}'
                    )

                pro_fixed_probe = page.evaluate(
                    """async () => {
                      const left = document.querySelector('#pmv2ConfigScroll');
                      const right = document.querySelector('.pmv2-prompt-panel');
                      window.scrollTo(0, 0);
                      await new Promise(resolve => setTimeout(resolve, 40));
                      const beforeTop = right.getBoundingClientRect().top;
                      const maxScroll = Math.max(0, document.documentElement.scrollHeight - innerHeight);
                      const targetY = Math.min(700, maxScroll);
                      window.scrollTo(0, targetY);
                      await new Promise(resolve => setTimeout(resolve, 100));
                      const afterTop = right.getBoundingClientRect().top;
                      const expectedTop = Math.max(18, beforeTop - scrollY);
                      return {
                        leftTop: left.scrollTop,
                        rightTop: right.scrollTop,
                        windowY: scrollY,
                        maxScroll,
                        targetY,
                        beforeTop,
                        afterTop,
                        expectedTop,
                        stickyError: Math.abs(afterTop - expectedTop),
                        rightPosition: getComputedStyle(right).position,
                      };
                    }"""
                )
                if (
                    pro_fixed_probe['leftTop'] >= 3
                    or pro_fixed_probe['rightTop'] >= 3
                    or pro_fixed_probe['rightPosition'] != 'sticky'
                    or abs(pro_fixed_probe['windowY'] - pro_fixed_probe['targetY']) > 3
                    or pro_fixed_probe['afterTop'] < 17
                    or pro_fixed_probe['stickyError'] > 5
                ):
                    raise AssertionError(
                        f'PromptMaster Pro V2 single-scroll sticky panel invalid: {pro_fixed_probe}'
                    )
                page.locator('#resetBtn').click()
                page.wait_for_function("window.scrollY < 3")
                customer_catalog_probe = page.evaluate(
                    """async () => {
                      const r = await fetch('/api/v1/prompts/?product=PRO', {
                        credentials: 'same-origin',
                        headers: {Accept: 'application/json'}
                      });
                      return {status: r.status, body: await r.json()};
                    }"""
                )
                if customer_catalog_probe['status'] != 200 or not customer_catalog_probe['body'].get('ok'):
                    raise AssertionError(
                        f'customer PromptMaster API access failed: {customer_catalog_probe}'
                    )
                customer_compose_probe = page.evaluate(
                    """async () => {
                      const runtimeSource = [...document.scripts]
                        .map(script => script.textContent || '')
                        .find(source => source.includes("const PM_CSRF='")) || '';
                      const csrfMatch = runtimeSource.match(/const PM_CSRF='([^']+)'/);
                      const csrf = csrfMatch?.[1] || '';
                      if (!csrf) {
                        return {status: 0, body: null, text: 'embedded CSRF token missing'};
                      }
                      const r = await fetch('/api/v1/prompts/compose/', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                          Accept: 'application/json',
                          'Content-Type': 'application/json',
                          'X-CSRFToken': decodeURIComponent(csrf),
                        },
                        body: JSON.stringify({
                          product: 'PRO',
                          task_id: 'PM20-001',
                          microsoft_tier: 'chatbasic',
                          input: {
                            fields: {
                              Fragestellung: 'Browser Kundenfunktionstest',
                              Kontext: 'PromptMaster Kundenbackend'
                            },
                            audience: 'Management',
                            focus: ['Primärquellen'],
                            output: 'Fundierte Antwort',
                            source: 'webwork',
                            tone: 'professional',
                            detail: 'standard'
                          }
                        })
                      });
                      const text = await r.text();
                      let body = null;
                      try { body = JSON.parse(text); } catch (_error) {}
                      return {
                        status: r.status,
                        contentType: r.headers.get('content-type') || '',
                        body,
                        text: text.slice(0, 500)
                      };
                    }"""
                )
                if (
                    customer_compose_probe['status'] != 200
                    or not (customer_compose_probe.get('body') or {}).get('ok')
                    or 'Browser Kundenfunktionstest'
                    not in (customer_compose_probe.get('body') or {}).get('result', {}).get('prompt', '')
                ):
                    raise AssertionError(
                        f'customer PromptMaster compose failed: {customer_compose_probe}'
                    )
            else:
                page.set_viewport_size({'width': 1440, 'height': 1000})
                dashboard_response = page.goto(base + 'ns-admin/', wait_until='networkidle')
                if not dashboard_response or dashboard_response.status != 200:
                    raise AssertionError('admin dashboard post-install acceptance failed')
                dashboard_visual = page.evaluate(
                    """() => {
                      const bars = [...document.querySelectorAll('.revenue-bar')];
                      const donut = document.querySelector('.donut-live');
                      const alerts = document.querySelector('.alert-stack');
                      return {
                        barCount: bars.length,
                        maxBarHeight: bars.length ? Math.max(...bars.map(
                          bar => bar.getBoundingClientRect().height
                        )) : 0,
                        donutPresent: !!donut,
                        donutBackground: donut ? getComputedStyle(donut).backgroundImage : '',
                        alertGap: alerts ? parseFloat(getComputedStyle(alerts).rowGap || getComputedStyle(alerts).gap || '0') : 0,
                      };
                    }"""
                )
                if dashboard_visual['barCount'] and dashboard_visual['maxBarHeight'] <= 3.5:
                    raise AssertionError(
                        f'admin dashboard revenue chart collapsed: {dashboard_visual}'
                    )
                if dashboard_visual['donutPresent'] and 'conic-gradient' not in dashboard_visual['donutBackground']:
                    raise AssertionError(
                        f'admin dashboard license donut missing: {dashboard_visual}'
                    )
                if dashboard_visual['alertGap'] < 7:
                    raise AssertionError(
                        f'admin dashboard action alerts have no visual spacing: {dashboard_visual}'
                    )

                launcher_contract = page.evaluate(
                    """() => {
                      const links = [...document.querySelectorAll('a')];
                      const pick = label => links.find(a => a.textContent.trim().includes(label));
                      return Object.fromEntries(['PromptMaster Pro', 'PromptMaster Free'].map(label => {
                        const a = pick(label);
                        return [label, a ? {
                          path: new URL(a.href).pathname,
                          target: a.target,
                          rel: a.rel,
                        } : null];
                      }));
                    }"""
                )
                expected_launchers = {
                    'PromptMaster Pro': '/pro/',
                    'PromptMaster Free': '/free/',
                }
                for label, path in expected_launchers.items():
                    row = launcher_contract.get(label)
                    if (
                        not row
                        or row.get('path') != path
                        or row.get('target') != '_blank'
                        or 'noopener' not in (row.get('rel') or '').split()
                    ):
                        raise AssertionError(
                            f'admin launcher contract invalid for {label}: {row}'
                        )
                dashboard_launchers = page.locator('.page-actions a[target="_blank"]')
                if dashboard_launchers.count() < 2:
                    raise AssertionError('admin dashboard must expose Free and Pro as new-tab launchers')

                page.goto(base + 'ns-admin/orders/', wait_until='networkidle')
                customer_sort = page.locator('th a', has_text='Kunde').first
                if not customer_sort.is_visible():
                    raise AssertionError('admin orders: customer column is not sortable')
                customer_sort.click()
                page.wait_for_load_state('networkidle')
                if 'sort=customer' not in page.url:
                    raise AssertionError(f'admin orders: customer sort did not activate: {page.url}')
                if not page.get_by_role('link', name='Sortierung zurücksetzen').is_visible():
                    raise AssertionError('admin orders: explicit sort reset is missing')

                page.goto(base + 'ns-admin/ops/', wait_until='networkidle')
                ops_text = page.locator('body').inner_text()
                for expected_text in (
                    'Docker-Host-VM',
                    'RAM verfügbar',
                    'Docker-Container',
                    'Dateiobjekte (Inodes)',
                ):
                    if expected_text not in ops_text:
                        raise AssertionError(
                            f'admin ops: monitoring scope/explanation missing: {expected_text}'
                        )

                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(base + 'ns-admin/more/', wait_until='networkidle')
                hrefs = set(page.locator('.content a').evaluate_all(
                    "els => els.map(e => new URL(e.href).pathname)"
                ))
                expected = {
                    '/ns-admin/search/', '/ns-admin/customers/', '/ns-admin/licenses/',
                    '/ns-admin/orders/', '/ns-admin/products/', '/ns-admin/prompt-studio/',
                    '/ns-admin/content/faqs/', '/ns-admin/email/', '/ns-admin/mollie/',
                    '/ns-admin/statistics/', '/ns-admin/ops/', '/ns-admin/api/',
                    '/ns-admin/legal/', '/ns-admin/support/', '/ns-admin/audit/',
                    '/ns-admin/roles/', '/ns-admin/settings/', '/pro/', '/auth/logout/',
                }
                missing = sorted(expected - hrefs)
                if missing:
                    raise AssertionError(f'admin mobile More navigation missing: {missing}')

                page.set_viewport_size({'width': 1440, 'height': 1000})
                pro_response = page.goto(base + 'pro/', wait_until='networkidle')
                if not pro_response or pro_response.status != 200:
                    raise AssertionError('netstyle staff cannot open PromptMaster Pro')
                page.wait_for_function("document.body.classList.contains('pmv2')")
                utility_paths = set(page.locator('.pmv2-header-actions a').evaluate_all(
                    "els => els.map(e => new URL(e.href).pathname)"
                ))
                required_utility_paths = {'/ns-admin/', '/auth/logout/'}
                if not required_utility_paths.issubset(utility_paths):
                    raise AssertionError(
                        f'netstyle Pro V2 session navigation missing: {sorted(required_utility_paths - utility_paths)}'
                    )
                catalog_probe = page.evaluate(
                    """async () => {
                      const r = await fetch('/api/v1/prompts/?product=PRO', {
                        credentials: 'same-origin',
                        headers: {Accept: 'application/json'}
                      });
                      return {status: r.status, body: await r.json()};
                    }"""
                )
                if catalog_probe['status'] != 200 or not catalog_probe['body'].get('ok'):
                    raise AssertionError(
                        f'netstyle PromptMaster API access failed: {catalog_probe}'
                    )
                if catalog_probe['body']['catalog'].get('task_count') != 194:
                    raise AssertionError('netstyle PromptMaster catalog is incomplete')
                staff_compose_probe = page.evaluate(
                    """async () => {
                      const runtimeSource = [...document.scripts]
                        .map(script => script.textContent || '')
                        .find(source => source.includes("const PM_CSRF='")) || '';
                      const csrfMatch = runtimeSource.match(/const PM_CSRF='([^']+)'/);
                      const csrf = csrfMatch?.[1] || '';
                      if (!csrf) {
                        return {status: 0, body: null, text: 'embedded CSRF token missing'};
                      }
                      const r = await fetch('/api/v1/prompts/compose/', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                          Accept: 'application/json',
                          'Content-Type': 'application/json',
                          'X-CSRFToken': decodeURIComponent(csrf),
                        },
                        body: JSON.stringify({
                          product: 'PRO',
                          task_id: 'PM20-001',
                          microsoft_tier: 'chatbasic',
                          input: {
                            fields: {
                              Fragestellung: 'Browser netstyle Funktionstest',
                              Kontext: 'PromptMaster Adminbackend'
                            },
                            audience: 'Management',
                            focus: ['Primärquellen'],
                            output: 'Fundierte Antwort',
                            source: 'webwork',
                            tone: 'professional',
                            detail: 'standard'
                          }
                        })
                      });
                      const text = await r.text();
                      let body = null;
                      try { body = JSON.parse(text); } catch (_error) {}
                      return {
                        status: r.status,
                        contentType: r.headers.get('content-type') || '',
                        body,
                        text: text.slice(0, 500)
                      };
                    }"""
                )
                if (
                    staff_compose_probe['status'] != 200
                    or not (staff_compose_probe.get('body') or {}).get('ok')
                    or 'Browser netstyle Funktionstest'
                    not in (staff_compose_probe.get('body') or {}).get('result', {}).get('prompt', '')
                ):
                    raise AssertionError(
                        f'netstyle PromptMaster compose failed: {staff_compose_probe}'
                    )

                for width, height in ((360,800),(390,844),(768,1024),(1440,1000),(1920,1080)):
                    page.set_viewport_size({'width': width, 'height': height})
                    response = page.goto(base + 'pro/app/', wait_until='networkidle')
                    if not response or response.status != 200:
                        raise AssertionError(f'Pro V2 responsive shell {width}px: HTTP failure')
                    page.wait_for_function("document.body.classList.contains('pmv2')")
                    _check_product_v2_shell(page, 'Pro V2 responsive shell', width)

            for width, height in ((360, 800), (390, 844), (768, 1024), (1440, 1000), (1920, 1080)):
                page.set_viewport_size({'width': width, 'height': height})
                for route, label in routes:
                    _check_backend_page(page, base, route, width, label)

            if page_errors:
                raise AssertionError(f'{role}: browser JS error: {page_errors[0]}')
            if bad_responses:
                raise AssertionError(f'{role}: local HTTP error: {bad_responses[0]}')
            context.close()

        print(
            'DJANGO BACKEND BROWSER SMOKE OK: real login + existing/first-time TOTP 2FA + '
            'public auth/legal + portal/admin/prompt-studio + global search + complete mobile navigation + responsive 360/390/768/1440/1920 + overflow/overlap guards'
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

def _run_cross_browser_product_v2(browser, fixture: dict, engine: str) -> None:
    """Targeted Free/Pro V2 compatibility gate for Firefox and WebKit."""
    import subprocess
    import sys

    port = _free_port()
    base = f'http://127.0.0.1:{port}/'
    env = os.environ.copy()
    env.setdefault('ENVIRONMENT', 'development')
    env.setdefault('ALLOWED_HOSTS', '127.0.0.1,localhost')
    env.setdefault('SESSION_COOKIE_SECURE', '0')
    env.setdefault('CSRF_COOKIE_SECURE', '0')
    process = subprocess.Popen(
        [sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
        cwd=str(ROOT / 'backend'),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_http(base + 'health/live/', process)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()

        response = page.goto(base + 'free/', wait_until='domcontentloaded')
        if not response or response.status != 200:
            raise AssertionError(f'{engine} Free V2: HTTP 200 expected')
        page.wait_for_function(
            "document.body.classList.contains('pmv2') && "
            "document.querySelectorAll('[data-appwrap]').length === 34",
            timeout=15000,
        )
        free_layout = page.evaluate(
            """async () => {
              const left = document.querySelector('#pmv2ConfigScroll');
              const right = document.querySelector('.pmv2-prompt-panel');
              if (!left || !right) return null;
              window.scrollTo(0, 0);
              await new Promise(resolve => setTimeout(resolve, 40));
              const beforeTop = right.getBoundingClientRect().top;
              const maxScroll = Math.max(0, document.documentElement.scrollHeight-innerHeight);
              const targetY = Math.min(600, maxScroll);
              window.scrollTo(0, targetY);
              await new Promise(resolve => setTimeout(resolve, 100));
              const afterTop = right.getBoundingClientRect().top;
              const expectedTop = Math.max(18, beforeTop - scrollY);
              return {
                leftTop: left.scrollTop,
                rightTop: right.scrollTop,
                windowY: scrollY,
                maxScroll,
                targetY,
                beforeTop,
                afterTop,
                expectedTop,
                stickyError: Math.abs(afterTop - expectedTop),
                bodyOverflowY: getComputedStyle(document.body).overflowY,
                leftOverflowY: getComputedStyle(left).overflowY,
                rightOverflowY: getComputedStyle(right).overflowY,
                rightPosition: getComputedStyle(right).position,
              };
            }"""
        )
        if (
            not free_layout
            or free_layout['leftTop'] >= 3
            or free_layout['rightTop'] >= 3
            or free_layout['bodyOverflowY'] not in {'auto', 'scroll'}
            or free_layout['leftOverflowY'] != 'visible'
            or free_layout['rightOverflowY'] not in {'auto', 'scroll'}
            or free_layout['rightPosition'] != 'sticky'
            or abs(free_layout['windowY'] - free_layout['targetY']) > 3
            or free_layout['afterTop'] < 17
            or free_layout['stickyError'] > 5
        ):
            raise AssertionError(f'{engine} Free V2 single-scroll layout unstable: {free_layout}')
        page.locator('#resetBtn').click()
        page.wait_for_function("window.scrollY < 3")

        _browser_login(
            page,
            base,
            fixture['admin_email'],
            fixture['password'],
            fixture['admin_secret'],
            '/ns-admin/',
        )
        pro_response = page.goto(base + 'pro/app/', wait_until='domcontentloaded')
        if not pro_response or pro_response.status != 200:
            raise AssertionError(f'{engine} Pro V2: HTTP 200 expected')
        page.wait_for_function(
            "document.body.dataset.pmv2Ready === '1' && "
            "document.querySelectorAll('#catalog .app-card').length === 34 && "
            "document.querySelectorAll('#pmv2AppSearch').length === 1",
            timeout=15000,
        )
        if page.locator('#pmv2AppSearch').count() != 1:
            raise AssertionError(f'{engine} Pro V2 search control missing after V2 ready')
        page.locator('#pmv2AppSearch').fill('Planner')
        page.wait_for_timeout(100)
        visible_apps = page.locator('#catalog .app-card:not(.pmv2-search-hidden)').count()
        if visible_apps != 1:
            raise AssertionError(f'{engine} Pro V2 search expected 1 Planner result, got {visible_apps}')
        page.locator('#pmv2AppSearch').fill('')
        page.wait_for_timeout(80)

        locked_card = page.locator('#catalog .app-card.locked').first
        if locked_card.count() == 0:
            raise AssertionError(f'{engine} Pro V2: expected Microsoft-tier locked app cards')
        locked_card.hover()
        page.wait_for_timeout(120)
        locked_hover = locked_card.evaluate(
            """el => {
              const style = getComputedStyle(el);
              const tag = el.querySelector('.tag');
              const tagStyle = tag ? getComputedStyle(tag) : null;
              return {
                background: style.backgroundImage,
                transform: style.transform,
                tagBackground: tagStyle?.backgroundColor || '',
                tagColor: tagStyle?.color || '',
              };
            }"""
        )
        if (
            '75, 38, 121' not in locked_hover['background']
            or locked_hover['transform'] == 'none'
            or locked_hover['tagColor'] not in {'rgb(248, 239, 255)', 'rgba(248, 239, 255, 1)'}
        ):
            raise AssertionError(
                f'{engine} Pro locked-app hover is not dark violet: {locked_hover}'
            )

        reset_action = page.locator('.pmv2-prompt-panel > .actions .btn').first
        reset_action.hover()
        page.wait_for_timeout(120)
        action_hover = reset_action.evaluate(
            """el => {
              const style = getComputedStyle(el);
              return {
                background: style.backgroundImage,
                color: style.color,
                transform: style.transform,
              };
            }"""
        )
        if (
            '87, 39, 130' not in action_hover['background']
            or action_hover['color'] not in {
                'rgb(255, 255, 255)', 'rgba(255, 255, 255, 1)',
                'rgb(253, 253, 253)', 'rgba(253, 253, 253, 1)',
            }
            or action_hover['transform'] == 'none'
        ):
            raise AssertionError(
                f'{engine} Pro prompt-action hover is not dark violet: {action_hover}'
            )

        # Populate the dynamic Pro controls before validating their computed
        # style. This catches the exact white selected option regression from
        # the 2026-09-24 Pro screenshot in Firefox/WebKit as well as Chromium.
        page.locator('[data-app="copilot_chat"]').click()
        page.wait_for_function(
            "() => document.querySelectorAll('#taskGrid [data-task]').length > 0"
        )
        page.locator('#taskGrid [data-task]').first.evaluate("(el) => el.click()")
        page.wait_for_function(
            "() => document.querySelectorAll('#audienceGrid .option > span').length > 0"
        )
        page.wait_for_function(
            "() => document.querySelectorAll('.input-card.required .task-input').length > 0"
        )
        required_probe = page.evaluate(
            """() => {
              const input = document.querySelector('.input-card.required .task-input');
              const mark = document.querySelector('.input-card.required .required-mark');
              const guard = document.querySelector('.pmv2-prompt-guard');
              const style = mark ? getComputedStyle(mark) : null;
              return {
                required: input?.required === true,
                ariaRequired: input?.getAttribute('aria-required') || '',
                ariaInvalid: input?.getAttribute('aria-invalid') || '',
                markText: (mark?.textContent || '').trim(),
                markBackground: style?.backgroundImage || '',
                guardVisible: !!guard && !guard.hidden,
                guardText: (guard?.textContent || '').trim(),
              };
            }"""
        )
        if (
            not required_probe['required']
            or required_probe['ariaRequired'] != 'true'
            or required_probe['ariaInvalid'] != 'true'
            or required_probe['markText'] != 'PFLICHTFELD'
            or 'gradient' not in required_probe['markBackground']
            or not required_probe['guardVisible']
            or 'Pflichtfelder fehlen' not in required_probe['guardText']
        ):
            raise AssertionError(
                f'{engine} Pro required-field guidance regressed: {required_probe}'
            )

        _check_product_v2_shell(page, f'{engine} Pro V2 selected controls', 1440)

        # Reproduce the exact Power Automate screenshot path end-to-end. One
        # missing required field must block composition; once Quell- und
        # Zielsystem are present the server-generated prompt must appear.
        page.locator('input[name="mslicense"][value="premium"]').check(force=True)
        page.wait_for_timeout(100)
        page.locator('[data-app="power_automate"]').click()
        page.wait_for_function(
            "() => document.querySelectorAll('#taskGrid [data-task]').length > 0"
        )
        page.locator('#taskGrid [data-task="PM20-159"]').evaluate("(el) => el.click()")
        page.wait_for_function(
            "() => document.querySelectorAll('.input-card.required .task-input').length === 2"
        )
        required_inputs = page.locator('.input-card.required .task-input')
        required_inputs.nth(0).fill('Sage 100 Browserquelle')
        page.wait_for_timeout(350)
        if page.locator('#promptOutput').input_value().strip():
            raise AssertionError(
                f'{engine} Pro PM20-159 composed before Zielsystem was provided'
            )
        required_inputs.nth(1).fill('CRM Browserziel')
        page.wait_for_function(
            """() => {
              const output=document.querySelector('#promptOutput');
              return document.querySelector('#promptStatus')?.textContent==='BEREIT ZUM KOPIEREN'
                && !!output?.value
                && output.value.includes('Sage 100 Browserquelle')
                && output.value.includes('CRM Browserziel');
            }""",
            timeout=10000,
        )
        power_automate_prompt = page.locator('#promptOutput').input_value()
        if (
            'Sage 100 Browserquelle' not in power_automate_prompt
            or 'CRM Browserziel' not in power_automate_prompt
        ):
            raise AssertionError(
                f'{engine} Pro PM20-159 server prompt missing required inputs'
            )

        context.close()
        print(f'{engine.upper()} PROMPTMASTER V2 UI OK')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _run_cross_browser_2fa_layout(browser, fixture: dict, engine: str) -> None:
    import subprocess
    import sys

    port = _free_port()
    base = f'http://127.0.0.1:{port}/'
    env = os.environ.copy()
    env.setdefault('ENVIRONMENT', 'development')
    env.setdefault('ALLOWED_HOSTS', '127.0.0.1,localhost')
    env.setdefault('SESSION_COOKIE_SECURE', '0')
    env.setdefault('CSRF_COOKIE_SECURE', '0')
    process = subprocess.Popen(
        [sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
        cwd=str(ROOT / 'backend'),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_http(base + 'health/live/', process)
        context = browser.new_context(viewport={'width': 460, 'height': 820})
        page = context.new_page()
        response = page.goto(base + 'auth/login/', wait_until='networkidle')
        if not response or response.status != 200:
            raise AssertionError(f'{engine} 2FA layout: login page failed')
        page.locator('input[name="email"]').fill(fixture['admin_email'])
        password_input = page.locator('input[name="password"]')
        password_input.fill(fixture['password'])
        password_input.press('Enter')
        page.wait_for_url('**/auth/2fa/**')
        page.wait_for_load_state('networkidle')
        layout = page.evaluate(
            """() => {
              const card = document.querySelector('.auth-login-card');
              const form = document.querySelector('.auth-login-form');
              const input = form?.querySelector('input[name="code"]');
              const button = form?.querySelector('.auth-submit');
              if (!card || !form || !input || !button) return null;
              const c = card.getBoundingClientRect();
              const f = form.getBoundingClientRect();
              const i = input.getBoundingClientRect();
              const b = button.getBoundingClientRect();
              return {
                cardLeft: c.left, cardRight: c.right, cardWidth: c.width,
                formLeft: f.left, formRight: f.right,
                inputLeft: i.left, inputRight: i.right, inputWidth: i.width,
                buttonLeft: b.left, buttonRight: b.right, buttonWidth: b.width,
                inputHeight: i.height, buttonHeight: b.height,
                verticalGap: b.top - i.bottom,
                overflow: (
                  i.left < c.left || i.right > c.right ||
                  b.left < c.left || b.right > c.right
                ),
              };
            }"""
        )
        if (
            not layout
            or layout['cardWidth'] < 300
            or layout['overflow']
            or abs(layout['inputLeft'] - layout['buttonLeft']) > 1.5
            or abs(layout['inputRight'] - layout['buttonRight']) > 1.5
            or abs(layout['inputWidth'] - layout['buttonWidth']) > 2
            or layout['inputHeight'] < 44
            or layout['buttonHeight'] < 42
            or layout['verticalGap'] < 10
        ):
            raise AssertionError(f'{engine} 2FA layout unstable: {layout}')
        context.close()
        print(f'{engine.upper()} 2FA LAYOUT OK: {layout}')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(f'BROWSER SMOKE SKIPPED: playwright fehlt ({exc})')
    executable = os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
    backend_fixture = _backend_fixture() if os.getenv('BACKEND_UI_BROWSER_SMOKE') == '1' else None
    catalog = mock_catalog()
    if (catalog['application_count'], catalog['task_count']) != (34, 194):
        raise SystemExit('BROWSER SMOKE FAIL: catalog count drift')
    html = RUNTIME.read_text(encoding='utf-8')
    # Prevent all asset network access and inject the mocked API before product JS.
    html = html.replace('https://netstyle.de/public_pictures/netstyle%20Logo%20OHNE%20Netz%20FREIGESTELLT.png', 'data:image/gif;base64,R0lGODlhAQABAAAAACw=')
    html = html.replace('</head>', injected_fetch(catalog) + '</head>', 1)

    with sync_playwright() as pw:
        launch_kwargs = {'headless': True, 'args': ['--no-sandbox']}
        if executable:
            launch_kwargs['executable_path'] = executable
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_content(html, wait_until='domcontentloaded')
        page.wait_for_function("document.querySelectorAll('#catalog .app-card').length === 34")
        app_ids = page.locator('#catalog .app-card').evaluate_all("els => els.map(e => e.dataset.app)")
        if len(app_ids) != 34 or len(set(app_ids)) != 34:
            raise AssertionError(f'expected 34 unique app cards, got {len(app_ids)}/{len(set(app_ids))}')
        if 'power_automate' not in app_ids or 'github_copilot' not in app_ids:
            raise AssertionError('expanded 34-app catalog is not visible')

        # Exercise every catalog application and every one of the 194 task
        # render paths in the browser. Server composition parity for all 194
        # tasks is covered by validate_prompt_runtime; this loop validates the
        # interactive DOM contract and dynamic field generation task-by-task.
        premium = page.locator('input[name="mslicense"][value="premium"]')
        premium.check(force=True)
        rendered_tasks = 0
        for source_app in catalog['applications']:
            app_code = source_app['code']
            page.locator(f'[data-app="{app_code}"]').click()
            expected_tasks = source_app['tasks']
            page.wait_for_function(
                f"document.querySelectorAll('#taskGrid [data-task]').length === {len(expected_tasks)}"
            )
            for source_task in expected_tasks:
                task_id = source_task['id']
                page.locator(f'[data-task="{task_id}"]').click()
                expected_fields = len(source_task.get('required') or []) + len(source_task.get('optional') or [])
                actual_fields = page.locator('#inputGrid .task-input').count()
                if actual_fields != expected_fields:
                    raise AssertionError(
                        f'{app_code}/{task_id}: expected {expected_fields} rendered input fields, '
                        f'got {actual_fields}'
                    )
                rendered_tasks += 1
        if rendered_tasks != 194:
            raise AssertionError(f'expected to exercise 194 Pro task render paths, got {rendered_tasks}')

        page.locator('[data-app="copilot_chat"]').click()
        page.wait_for_function("document.querySelectorAll('#taskGrid [data-task]').length === 5")
        page.locator('[data-task="PM20-001"]').click()
        page.locator('.task-input').first.fill('Wie verbessern wir den Support?')
        page.wait_for_function("document.querySelector('#promptOutput').value === 'SERVER TEST PROMPT'")
        compose_bodies = page.evaluate('window.__pmSmokeCompose')
        if not compose_bodies or compose_bodies[-1].get('task_id') != 'PM20-001':
            raise AssertionError('server compose was not called for PM20-001')
        if compose_bodies[-1].get('input', {}).get('fields', {}).get('Fragestellung') != 'Wie verbessern wir den Support?':
            raise AssertionError('required field did not reach compose payload')

        page.locator('#pmRatingButton').click()
        page.locator('[data-pm-stars="2"]').click()
        page.wait_for_function("!document.querySelector('#pmFeedbackReveal').classList.contains('hidden')")
        if not page.locator('#pmFeedback').evaluate("el => el.classList.contains('hidden')"):
            raise AssertionError('low-rating feedback field opened without deliberate Feedback ergänzen action')
        page.locator('#pmFeedbackReveal').click()
        page.wait_for_function("!document.querySelector('#pmFeedback').classList.contains('hidden')")
        page.locator('#pmFeedbackText').fill('Mehr Kontext wäre hilfreich.')
        page.locator('#pmFeedbackSend').click()
        page.wait_for_function("document.querySelector('#pmRatingState').textContent.includes('gespeichert')")
        ratings = page.evaluate('window.__pmSmokeRatings')
        if not ratings or ratings[-1].get('feedback') != 'Mehr Kontext wäre hilfreich.':
            raise AssertionError('optional low-rating feedback was not sent')

        # 4-5 stars are complete ratings: no additional feedback prompt.
        page.locator('[data-pm-stars="5"]').click()
        page.wait_for_function("document.querySelector('#pmRatingState').textContent.includes('5 ★ gespeichert')")
        if not page.locator('#pmFeedbackReveal').evaluate("el => el.classList.contains('hidden')"):
            raise AssertionError('high rating incorrectly asks for extra feedback')
        if not page.locator('#pmFeedback').evaluate("el => el.classList.contains('hidden')"):
            raise AssertionError('high rating incorrectly leaves feedback field visible')

        run_backend_ui_smoke(browser, backend_fixture)
        browser.close()

        if backend_fixture is not None:
            for engine_name, browser_type in (
                ('firefox', pw.firefox),
                ('webkit', pw.webkit),
            ):
                engine_browser = browser_type.launch(headless=True)
                try:
                    _run_cross_browser_2fa_layout(
                        engine_browser,
                        backend_fixture,
                        engine_name,
                    )
                    _run_cross_browser_product_v2(
                        engine_browser,
                        backend_fixture,
                        engine_name,
                    )
                finally:
                    engine_browser.close()

    print('BROWSER RUNTIME SMOKE OK: 34 apps / 194 task render paths + compose + rating/feedback + V2 Free/Pro layout in Chromium/Firefox/WebKit')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
