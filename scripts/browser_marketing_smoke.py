#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'marketing' / 'dist'
DATA = ROOT / 'backend' / 'apps' / 'prompts' / 'data' / 'pm20_golden_logic.json'


def app_names() -> list[str]:
    data = json.loads(DATA.read_text(encoding='utf-8'))
    return [str(v.get('name') or k) for k, v in (data.get('APP') or {}).items()]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(f'MARKETING BROWSER SMOKE SKIPPED: playwright fehlt ({exc})')

    index = DIST / 'index.html'
    if not index.exists():
        raise SystemExit('MARKETING BROWSER SMOKE FAIL: marketing/dist/index.html fehlt')
    names = app_names()
    if len(names) != 34:
        raise SystemExit(f'MARKETING BROWSER SMOKE FAIL: expected 34 apps, got {len(names)}')

    html = index.read_text(encoding='utf-8')
    match = re.search(r'<script type="module"[^>]+src="([^"]+)"[^>]*></script>', html)
    if not match:
        raise SystemExit('MARKETING BROWSER SMOKE FAIL: marketing module script not found')
    bundle_path = DIST / match.group(1).lstrip('/')
    if not bundle_path.exists():
        raise SystemExit('MARKETING BROWSER SMOKE FAIL: marketing JS bundle missing')
    integration = (DIST / 'integration-patch.js').read_text(encoding='utf-8')

    payload = {
        'currency': 'EUR', 'priceBasis': 'gross', 'taxBasisPoints': 1900, 'market': 'DE',
        'products': [
            {'id': 'PROMPTMASTER_FREE', 'monthlyGrossCents': 0, 'termMonths': 0, 'active': True},
            {'id': 'PROMPTMASTER_PRO', 'monthlyGrossCents': 299, 'annualGrossCents': 3588, 'termMonths': 12, 'active': True, 'purchasable': True},
        ],
        'maxQuantity': 999, 'checkoutEnabled': True, 'loginEnabled': True, 'freeUrl': '/free/',
        'proApplicationCount': len(names), 'proApplicationNames': names,
    }
    payload_json = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    prelude = f'''<script>\nwindow.fetch=async function(url){{\n  if(String(url).includes('catalog.json')) return new Response(JSON.stringify({payload_json}),{{status:200,headers:{{'Content-Type':'application/json'}}}});\n  return new Response('',{{status:404}});\n}};\n</script>'''

    # No external network/files are needed for this DOM smoke. The committed
    # HTML is pre-rendered by finalize.mjs; integration-patch is then executed
    # against the same DOM using the live-catalog contract.
    html = re.sub(r'<link rel="stylesheet"[^>]+href="[^"]+"[^>]*>', '', html)
    html = html.replace(match.group(0), '')
    html = html.replace('<script src="/integration-patch.js" defer></script>', '')
    html = html.replace('</head>', prelude + '</head>', 1)
    html = html.replace('</body>', '<script>' + integration + '</script></body>', 1)

    executable = os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
    with sync_playwright() as pw:
        launch = {'headless': True, 'args': ['--no-sandbox']}
        if executable:
            launch['executable_path'] = executable
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_content(html, wait_until='domcontentloaded')
        page.wait_for_function("document.querySelectorAll('.product').length === 2")
        page.wait_for_function("[...document.querySelectorAll('.mini-label')].some(e => e.textContent.trim()==='MIT PRO ZUSÄTZLICH' && e.nextElementSibling?.children.length===28)")
        if page.locator('.product.free').count() != 1 or page.locator('.product.pro').count() != 1:
            raise AssertionError('Free/Pro hero cards missing')
        page.wait_for_function("document.querySelector('.product.pro .price')?.textContent.includes('2,99')")
        if page.locator('#faq details').count() != 20:
            raise AssertionError('expected 20 FAQ entries')
        if page.locator('#particle-head').count() != 1:
            raise AssertionError('particle head canvas missing')
        if page.get_by_text('28 zusätzliche Microsoft-Anwendungen', exact=True).count() < 1:
            raise AssertionError('34-app catalog bridge did not update comparison')
        browser.close()

    print('MARKETING BROWSER SMOKE OK: public page + price + 34-app bridge + FAQ + particle-head canvas')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
