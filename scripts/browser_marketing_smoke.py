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
from PIL import Image, ImageChops, ImageStat

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


def compare_head_render(reference: Path, candidate: Path) -> dict:
    # The product requirement is not merely "a head exists" in Firefox.
    # Compare the unobstructed central hero region against the canonical
    # Chromium/Edge render. Cards sit outside this crop, so font rendering and
    # controls do not dilute the visual gate.
    crop = (480, 90, 960, 720)
    ref = Image.open(reference).convert('RGB').crop(crop)
    cand = Image.open(candidate).convert('RGB').crop(crop)
    diff = ImageChops.difference(ref, cand)
    mae = sum(ImageStat.Stat(diff).mean) / 3.0

    def bright_count(image, threshold=70):
        histogram = image.convert('L').histogram()
        return sum(histogram[threshold + 1:])

    ref_bright = bright_count(ref)
    cand_bright = bright_count(cand)
    bright_ratio = cand_bright / max(1, ref_bright)
    return {
        'mae': mae,
        'reference_bright': ref_bright,
        'candidate_bright': cand_bright,
        'bright_ratio': bright_ratio,
    }


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
        engine = os.getenv('PM_BROWSER_ENGINE', 'chromium').strip().lower()
        if engine not in {'chromium', 'firefox', 'webkit'}:
            fail(f'unbekannte Browser-Engine: {engine}')
        artifact_dir = ROOT / 'browser-artifacts'
        artifact_dir.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            if engine == 'chromium':
                executable = (
                    os.getenv('CHROMIUM_PATH')
                    or shutil.which('chromium')
                    or shutil.which('chromium-browser')
                    or shutil.which('google-chrome')
                )
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
            elif engine == 'firefox':
                browser = pw.firefox.launch(headless=True)
            else:
                browser = pw.webkit.launch(headless=True)

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
                    "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                    timeout=15000,
                )
                page.wait_for_timeout(900)
                if width == 1440:
                    live_path = artifact_dir / f'{engine}-1440-live.png'
                    page.screenshot(
                        path=str(live_path),
                        full_page=False,
                    )
                    if engine == 'firefox':
                        edge_reference = artifact_dir / 'chromium-1440-live.png'
                        if not edge_reference.is_file():
                            fail(f'{engine}: canonical Chromium/Edge screenshot missing')
                        visual = compare_head_render(edge_reference, live_path)
                        if visual['mae'] > 20.0:
                            fail(
                                f'{engine}: head differs too strongly from Edge '
                                f'(central MAE={visual["mae"]:.2f}, max=20.00)'
                            )
                        if not 0.65 <= visual['bright_ratio'] <= 1.45:
                            fail(
                                f'{engine}: head point energy differs from Edge '
                                f'(ratio={visual["bright_ratio"]:.3f}, allowed 0.65..1.45)'
                            )

                metrics = page.evaluate(
                    """() => {
                      const one = (s) => document.querySelector(s);
                      const rect = (s) => one(s).getBoundingClientRect();
                      const free = rect('.product.free');
                      const pro = rect('.product.pro');
                      const center = rect('.hero-center');
                      const renderer = one('.head-stage').dataset.headRenderer || '';
                      const headCanvas = renderer === 'canvas2d'
                        ? one('.head-fallback-canvas')
                        : one('#particle-head');
                      const canvas = headCanvas.getBoundingClientRect();
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
                        headRenderer: renderer,
                        fallbackHidden: one('.head-fallback').hidden,
                        motionControlPresent: !!one('.motion-button'),
                        headOverlayPresent: !!document.querySelector('.hero-title,.core-sentence'),
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
                    fail(f'{engine} {width}px: Kopf-Canvas füllt die Szene nicht')
                if metrics['headRenderer'] not in {'webgl', 'canvas2d'}:
                    fail(f'{engine} {width}px: kein aktiver Kopf-Renderer ({metrics["headRenderer"]})')
                if engine == 'chromium' and metrics['headRenderer'] != 'webgl':
                    fail(f'{width}px: Chromium muss den primären WebGL-Renderer validieren')
                if metrics['motionControlPresent']:
                    fail(f'{engine} {width}px: unerwünschte Bewegungssteuerung ist sichtbar')
                if metrics['headOverlayPresent']:
                    fail(f'{engine} {width}px: sichtbarer Text liegt im Kopfbereich')
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
                    selector = (
                        '.head-fallback-canvas'
                        if metrics['headRenderer'] == 'canvas2d'
                        else '#particle-head'
                    )
                    canvas = page.locator(selector)
                    before = hashlib.sha256(canvas.screenshot()).hexdigest()
                    page.mouse.move(width * 0.15, height * 0.35)
                    page.wait_for_timeout(600)
                    page.mouse.move(width * 0.85, height * 0.60)
                    page.wait_for_timeout(600)
                    after = hashlib.sha256(canvas.screenshot()).hexdigest()
                    if before == after:
                        fail(
                            f'{engine} 1440px: Kopf rendert, aber sichtbare '
                            'Animation/Pointer-Reaktion fehlt'
                        )
                    page.locator('#plus').click()
                    page.wait_for_function(
                        "document.querySelector('#quantity')?.value === '2' && "
                        "document.querySelector('[data-price=\"gross\"]')?.textContent.includes('71,76')"
                    )
                    page.locator('#minus').click()
                    page.wait_for_function(
                        "document.querySelector('#quantity')?.value === '1' && "
                        "document.querySelector('[data-price=\"gross\"]')?.textContent.includes('35,88')"
                    )

                page.close()

            if engine == 'chromium':
                # Export clean WebGL scene masters without navigation/cards.
                # These are generated from the canonical Chromium/Edge renderer
                # and can be used as pixel-stable no-WebGL fallbacks.
                for master_width, master_height in (
                    (1912, 948),
                    (1920, 1032),
                    (1440, 1000),
                    (768, 1024),
                    (390, 844),
                ):
                    master_page = browser.new_page(
                        viewport={'width': master_width, 'height': master_height},
                        device_scale_factor=1,
                    )
                    master_page.goto(base, wait_until='networkidle')
                    master_page.wait_for_function(
                        "document.querySelector('.head-stage')?.dataset.headRenderer === 'webgl' && "
                        "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                        timeout=15000,
                    )
                    master_page.wait_for_timeout(900)
                    master_page.add_style_tag(
                        content='header, main, footer, .skip { visibility: hidden !important; }'
                    )
                    master_page.screenshot(
                        path=str(
                            artifact_dir
                            / f'edge-scene-master-{master_width}x{master_height}.png'
                        ),
                        full_page=False,
                    )
                    master_page.close()

            # Deterministic no-WebGL acceptance. This simulates Firefox/VDI/
            # enterprise clients where WebGL context creation is unavailable.
            # The product must still show a real head through Canvas2D without
            # asking users to change browser or GPU settings.
            fallback_page = browser.new_page(
                viewport={'width': 1440, 'height': 1000},
                device_scale_factor=1,
            )
            fallback_errors: list[str] = []
            fallback_page.on('pageerror', lambda exc: fallback_errors.append(str(exc)))
            fallback_page.add_init_script(
                """(() => {
                  const original = HTMLCanvasElement.prototype.getContext;
                  HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
                      return null;
                    }
                    return original.call(this, type, ...args);
                  };
                })();"""
            )
            fallback_page.goto(base, wait_until='networkidle')
            fallback_page.wait_for_selector('.scene-world')
            fallback_page.wait_for_function(
                "document.querySelector('#particle-head')?.hidden === true && "
                "document.querySelector('.head-fallback')?.hidden === false && "
                "document.querySelector('.head-fallback')?.dataset.ready === '1' && "
                "document.querySelector('.head-fallback-canvas')",
                timeout=15000,
            )
            fallback_page.wait_for_timeout(900)
            fallback_page.screenshot(
                path=str(artifact_dir / f'{engine}-1440-forced-no-webgl.png'),
                full_page=False,
            )
            fallback_metrics = fallback_page.evaluate(
                """() => ({
                  canvasHidden: document.querySelector('#particle-head')?.hidden === true,
                  fallbackVisible: document.querySelector('.head-fallback')?.hidden === false,
                  fallbackCanvasVisible: (() => {
                    const c = document.querySelector('.head-fallback-canvas');
                    if (!c) return false;
                    const r = c.getBoundingClientRect();
                    return r.width > 300 && r.height > 300;
                  })(),
                  motionControlPresent: !!document.querySelector('.motion-button'),
                  headOverlayPresent: !!document.querySelector('.hero-title,.core-sentence'),
                  fallbackText: (document.querySelector('.head-fallback')?.textContent || '').trim(),
                  headBounds: document.querySelector('.head-stage')?.dataset.headBounds || '',
                  headModelRequested: performance.getEntriesByType('resource')
                    .some(r => r.name.includes('/models/head.glb')),
                  ctaVisible: !!document.querySelector('.product.pro a.button'),
                })"""
            )
            if not fallback_metrics['canvasHidden'] or not fallback_metrics['fallbackVisible']:
                fail('No-WebGL: visueller Fallback wird nicht angezeigt')
            if not fallback_metrics['fallbackCanvasVisible']:
                fail('No-WebGL: Canvas2D-Kopf ist nicht sichtbar')
            if fallback_metrics['motionControlPresent']:
                fail('No-WebGL: unerwünschte Bewegungssteuerung ist vorhanden')
            if fallback_metrics['headOverlayPresent']:
                fail('No-WebGL: sichtbarer Text liegt im Kopfbereich')
            if fallback_metrics['fallbackText']:
                fail(f'No-WebGL: unerwünschter Text liegt über dem Kopf: {fallback_metrics["fallbackText"]!r}')
            try:
                min_x, min_y, max_x, max_y = [
                    int(value) for value in fallback_metrics['headBounds'].split(',')
                ]
            except (TypeError, ValueError):
                fail(f'No-WebGL: keine messbare Kopfprojektion: {fallback_metrics["headBounds"]!r}')
            else:
                head_width = max_x - min_x
                head_height = max_y - min_y
                if head_width < 420 or head_height < 650:
                    fail(
                        'No-WebGL: Kopf ist gegenüber der Edge-Komposition zu klein '
                        f'({head_width}x{head_height}px)'
                    )
            if not fallback_metrics['headModelRequested']:
                fail('No-WebGL: Canvas2D-Fallback verwendet das Kopfmodell nicht')
            if not fallback_metrics['ctaVisible']:
                fail('No-WebGL: Marketing-CTA ist nicht weiter benutzbar')
            if fallback_errors:
                fail(f'No-WebGL: unbehandelter Browser-JS-Fehler: {fallback_errors[0]}')
            fallback_canvas = fallback_page.locator('.head-fallback-canvas')
            fallback_before = hashlib.sha256(fallback_canvas.screenshot()).hexdigest()
            fallback_page.wait_for_timeout(850)
            fallback_after = hashlib.sha256(fallback_canvas.screenshot()).hexdigest()
            if fallback_before == fallback_after:
                fail('No-WebGL: Kopf-/Bodenanimation ist statisch')
            fallback_page.close()

            # Pricing must remain usable even when a browser/proxy serves a stale
            # HTML response for /catalog.json. The embedded catalog is the safe
            # browser-independent fallback and preserves the agreed gross price.
            pricing_page = browser.new_page(
                viewport={'width': 1440, 'height': 1000},
                device_scale_factor=1,
            )
            pricing_page.route(
                '**/catalog.json*',
                lambda route: route.fulfill(
                    status=200,
                    content_type='text/html',
                    body='<!doctype html><title>stale cache</title>',
                ),
            )
            pricing_page.goto(base, wait_until='networkidle')
            pricing_page.wait_for_function(
                "document.querySelector('.product.pro .price')?.textContent.includes('2,99')"
            )
            pricing_page.wait_for_function(
                "document.querySelector('#quantity') && !document.querySelector('#quantity').disabled"
            )
            pricing_page.locator('#plus').click()
            pricing_page.wait_for_function(
                "document.querySelector('#quantity')?.value === '2'"
            )
            pricing_page.close()

            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(
        'MARKETING BROWSER SMOKE OK: real HTTP/CSS/JS + night landscape + '
        f'{engine}: animated WebGL/Canvas2D head + responsive 390/768/1440/1920 + resilient price/catalog/FAQ'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
