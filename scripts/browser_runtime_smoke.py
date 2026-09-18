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
    from apps.companies.models import Company, Invitation, Membership
    from apps.core.crypto import encrypt
    from apps.devices.models import DeviceRegistration
    from apps.legal.models import LegalDocument
    from apps.licenses.models import License, LicenseAssignment
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
    DeviceRegistration.objects.update_or_create(
        token_hash=hashlib.sha256(b'browser-smoke-device').hexdigest(),
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
    order.items.all().delete()
    OrderItem.objects.create(
        order=order,
        product=product,
        price_version=price,
        quantity=1,
        unit_gross=Decimal('35.88'),
        unit_net=Decimal('30.15'),
        tax_rate=Decimal('19.00'),
        product_name_snapshot=product.name,
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

    connections.close_all()
    return {
        'password': password,
        'admin_email': admin.email,
        'admin_secret': admin_secret,
        'customer_email': customer.email,
        'customer_secret': customer_secret,
        'company_id': str(company.pk),
        'member_id': str(member.pk),
        'product_id': str(product.pk),
        'license_id': str(active_license.pk),
        'order_id': str(order.pk),
        'task_id': definition.task_id,
        'version_id': str(version.pk),
        'free_license_id': str(free_license.pk),
    }


def _browser_login(page, base: str, email: str, password: str, secret: str) -> None:
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
    code_input.fill(pyotp.TOTP(secret).now())
    code_input.press('Enter')
    page.wait_for_url(lambda url: '/auth/2fa/' not in url and '/auth/login/' not in url)
    page.wait_for_load_state('networkidle')


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
          const content = document.querySelector('.content');
          const userMeta = document.querySelector('.user-meta');
          return {
            innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            overflowers,
            overlaps: overlaps.slice(0,10),
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

            _browser_login(page, base, email, fixture['password'], secret)

            if role == 'portal':
                page.goto(base + 'portal/dashboard/', wait_until='networkidle')
                search_input = page.locator('.topbar .search input')
                if not search_input.is_visible():
                    raise AssertionError('portal: desktop global search input is not visible')
                search_input.fill('PM-BROWSER-ACTIVE')
                search_input.press('Enter')
                page.wait_for_url(lambda url: '/portal/search/' in str(url))
                if 'PM-BROWSER-ACTIVE' not in page.locator('body').inner_text():
                    raise AssertionError('portal: global search did not return the visible tenant license')

            for width, height in ((390, 844), (768, 1024), (1440, 1000)):
                page.set_viewport_size({'width': width, 'height': height})
                for route, label in routes:
                    _check_backend_page(page, base, route, width, label)

            if page_errors:
                raise AssertionError(f'{role}: browser JS error: {page_errors[0]}')
            if bad_responses:
                raise AssertionError(f'{role}: local HTTP error: {bad_responses[0]}')
            context.close()

        print(
            'DJANGO BACKEND BROWSER SMOKE OK: real login + TOTP 2FA + '
            'portal/admin/prompt-studio + global search + complete mobile navigation + responsive 390/768/1440 + overflow/overlap guards'
        )
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
        page.wait_for_function("!document.querySelector('#pmFeedback').classList.contains('hidden')")
        page.locator('#pmFeedbackText').fill('Mehr Kontext wäre hilfreich.')
        page.locator('#pmFeedbackSend').click()
        page.wait_for_function("document.querySelector('#pmRatingState').textContent.includes('gespeichert')")
        ratings = page.evaluate('window.__pmSmokeRatings')
        if not ratings or ratings[-1].get('feedback') != 'Mehr Kontext wäre hilfreich.':
            raise AssertionError('optional low-rating feedback was not sent')

        run_backend_ui_smoke(browser, backend_fixture)
        browser.close()

    print('BROWSER RUNTIME SMOKE OK: 34-app central catalog + compose + rating/feedback bridge + authenticated backend UI gate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
