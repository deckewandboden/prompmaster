#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'marketing' / 'dist'
DATA = ROOT / 'backend' / 'apps' / 'prompts' / 'data' / 'pm20_golden_logic.json'
TARGETS = (
    (360, 800),
    (390, 844),
    (768, 1024),
    (1440, 1000),
    (1920, 1080),
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        return


def app_names() -> list[str]:
    data = json.loads(DATA.read_text(encoding='utf-8'))
    return [str(v.get('name') or k) for k, v in (data.get('APP') or {}).items()]


def fail(message: str) -> None:
    raise AssertionError(f'MARKETING BROWSER SMOKE FAIL: {message}')


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(f'MARKETING BROWSER SMOKE SKIPPED: playwright fehlt ({exc})')

    index = DIST / 'index.html'
    required_assets = (
        index,
        DIST / 'catalog.json',
        DIST / 'integration-patch.js',
        DIST / 'models' / 'head.glb',
        DIST / 'models' / 'night-landscape.png',
        DIST / 'brand' / 'design-reference.jpeg',
    )
    missing = [str(path.relative_to(ROOT)) for path in required_assets if not path.is_file()]
    if missing:
        fail('fehlende Build-Artefakte: ' + ', '.join(missing))

    names = app_names()
    if len(names) != 34:
        fail(f'expected 34 apps, got {len(names)}')

    handler = partial(QuietHandler, directory=str(DIST))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/'

    try:
        executable = (
            os.getenv('CHROMIUM_PATH')
            or shutil.which('chromium')
            or shutil.which('chromium-browser')
            or shutil.which('google-chrome')
        )
        with sync_playwright() as pw:
            launch = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--enable-webgl',
                    '--ignore-gpu-blocklist',
                    '--use-gl=angle',
                    '--use-angle=swiftshader',
                ],
            }
            if executable:
                launch['executable_path'] = executable
            browser = pw.chromium.launch(**launch)

            for width, height in TARGETS:
                page = browser.new_page(
                    viewport={'width': width, 'height': height},
                    device_scale_factor=1,
                )
                page_errors: list[str] = []
                bad_responses: list[str] = []
                page.on('pageerror', lambda exc, target=page_errors: target.append(str(exc)))
                page.on(
                    'response',
                    lambda response, target=bad_responses: (
                        target.append(f'{response.status} {response.url}')
                        if response.status >= 400 and response.url.startswith(base)
                        else None
                    ),
                )

                page.goto(base, wait_until='networkidle')
                page.wait_for_selector('.scene-world')
                page.wait_for_selector('.product.free')
                page.wait_for_selector('.product.pro')
                page.wait_for_function(
                    "document.querySelector('.product.pro .price')?.textContent.includes('2,99')"
                )
                page.wait_for_function(
                    "document.querySelectorAll('#faq details').length === 20"
                )
                page.wait_for_function(
                    "document.querySelector('#particle-head') && "
                    "document.querySelector('.head-fallback')?.hidden === true",
                    timeout=15000,
                )
                page.wait_for_timeout(900)

                metrics = page.evaluate(
                    """() => {
                      const one = (s) => document.querySelector(s);
                      const rect = (s) => one(s).getBoundingClientRect();
                      const free = rect('.product.free');
                      const pro = rect('.product.pro');
                      const center = rect('.hero-center');
                      const canvas = rect('#particle-head');
                      const scene = getComputedStyle(one('.scene-world'));
                      const landscape = getComputedStyle(one('.landscape'));
                      const header = getComputedStyle(one('header'));
                      const freeStyle = getComputedStyle(one('.product.free'));
                      const proStyle = getComputedStyle(one('.product.pro'));
                      return {
                        innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        freeHeight: free.height,
                        proHeight: pro.height,
                        freeTop: free.top,
                        proTop: pro.top,
                        centerTop: center.top,
                        centerBottom: center.bottom,
                        canvasWidth: canvas.width,
                        canvasHeight: canvas.height,
                        scenePosition: scene.position,
                        landscapeImage: landscape.backgroundImage,
                        headerPosition: header.position,
                        freeBorder: freeStyle.borderColor,
                        proBorder: proStyle.borderColor,
                        canvasVisible: !!(canvas.width && canvas.height),
                        fallbackHidden: one('.head-fallback').hidden,
                        motionVisible: !!one('.motion-button') && getComputedStyle(one('.motion-button')).display !== 'none',
                        productCount: document.querySelectorAll('.product').length,
                        faqCount: document.querySelectorAll('#faq details').length,
                        proExtraApps: [...document.querySelectorAll('.mini-label')].some(
                          e => e.textContent.trim() === 'MIT PRO ZUSÄTZLICH'
                            && e.nextElementSibling?.children.length === 28
                        ),
                        overflowers: [...document.querySelectorAll('body *')]
                          .map(e => {
                            const r = e.getBoundingClientRect();
                            return {
                              tag: e.tagName.toLowerCase(),
                              cls: typeof e.className === 'string' ? e.className.slice(0, 90) : '',
                              left: Math.round(r.left),
                              right: Math.round(r.right),
                              width: Math.round(r.width),
                            };
                          })
                          .filter(x => x.right > innerWidth + 1 || x.left < -1)
                          .sort((a, b) => (b.right - innerWidth) - (a.right - innerWidth))
                          .slice(0, 8),
                      };
                    }"""
                )

                if metrics['scrollWidth'] > metrics['innerWidth'] + 1:
                    fail(
                        f'{width}px: horizontaler Overflow {metrics["scrollWidth"]} > '
                        f'{metrics["innerWidth"]}; Elemente: {metrics["overflowers"]}'
                    )
                if metrics['productCount'] != 2:
                    fail(f'{width}px: Free/Pro-Karten fehlen')
                if abs(metrics['freeHeight'] - metrics['proHeight']) > 4:
                    fail(
                        f'{width}px: Produktkarten nicht gleich hoch '
                        f'({metrics["freeHeight"]:.1f}/{metrics["proHeight"]:.1f})'
                    )
                if metrics['scenePosition'] != 'fixed':
                    fail(f'{width}px: Nachtlandschaft ist nicht viewport-fixiert')
                if 'night-landscape' not in metrics['landscapeImage']:
                    fail(f'{width}px: Nachtlandschaft ist nicht geladen')
                if metrics['headerPosition'] != 'fixed':
                    fail(f'{width}px: Marketing-Navigation ist nicht fixiert')
                if not metrics['canvasVisible'] or metrics['canvasWidth'] < width * 0.95:
                    fail(f'{width}px: Kopf-Canvas füllt die Szene nicht')
                if not metrics['fallbackHidden']:
                    fail(f'{width}px: WebGL-Kopf fiel auf Text-Fallback zurück')
                if not metrics['motionVisible']:
                    fail(f'{width}px: Steuerung der Kopfanimation fehlt')
                if metrics['freeBorder'] == metrics['proBorder']:
                    fail(f'{width}px: Free-/Pro-Karten haben keine getrennte Cyan/Violett-Inszenierung')
                if metrics['faqCount'] != 20:
                    fail(f'{width}px: erwartete 20 FAQ fehlen')
                if not metrics['proExtraApps']:
                    fail(f'{width}px: 28 zusätzliche Pro-Anwendungen fehlen')

                if width <= 650:
                    first_card_top = min(metrics['freeTop'], metrics['proTop'])
                    if first_card_top < metrics['centerBottom'] - 4:
                        fail(f'{width}px: Produktkarten liegen nicht unterhalb des Kopfbereichs')

                if page_errors:
                    fail(f'{width}px: Browser-JS-Fehler: {page_errors[0]}')
                if bad_responses:
                    fail(f'{width}px: fehlende lokale Ressource: {bad_responses[0]}')

                if width == 1440:
                    canvas = page.locator('#particle-head')
                    before = hashlib.sha256(canvas.screenshot()).hexdigest()
                    page.mouse.move(width * 0.15, height * 0.35)
                    page.wait_for_timeout(600)
                    page.mouse.move(width * 0.85, height * 0.60)
                    page.wait_for_timeout(600)
                    after = hashlib.sha256(canvas.screenshot()).hexdigest()
                    if before == after:
                        fail('1440px: Partikelkopf rendert, aber sichtbare Animation/Pointer-Reaktion fehlt')

                page.close()

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(
        'MARKETING BROWSER SMOKE OK: real HTTP/CSS/JS + night landscape + '
        'animated particle head + responsive 390/768/1440/1920 + price/catalog/FAQ'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
