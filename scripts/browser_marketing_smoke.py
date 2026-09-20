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

    # Separate lower-scene energy gate. The original parity crop focused on
    # the face and could therefore miss the Firefox regression where the
    # strong animated ground beacons were nearly absent.
    ground_crop = (430, 620, 1010, 900)
    ref_ground = Image.open(reference).convert('RGB').crop(ground_crop)
    cand_ground = Image.open(candidate).convert('RGB').crop(ground_crop)
    ref_ground_bright = bright_count(ref_ground, threshold=105)
    cand_ground_bright = bright_count(cand_ground, threshold=105)
    ground_bright_ratio = cand_ground_bright / max(1, ref_ground_bright)
    return {
        'mae': mae,
        'reference_bright': ref_bright,
        'candidate_bright': cand_bright,
        'bright_ratio': bright_ratio,
        'ground_bright_ratio': ground_bright_ratio,
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
                firefox_env = os.environ.copy()
                firefox_env.setdefault('MOZ_WEBRENDER', '1')
                firefox_env.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
                firefox_headed = os.getenv('PM_FIREFOX_HEADED') == '1'
                browser = pw.firefox.launch(
                    headless=not firefox_headed,
                    env=firefox_env,
                    firefox_user_prefs={
                        'webgl.disabled': False,
                        'webgl.force-enabled': True,
                        'layers.acceleration.force-enabled': True,
                        'gfx.webrender.all': True,
                        'gfx.webrender.software': True,
                    },
                )
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
                        webglInit: one('.head-stage').dataset.webglInit || '',
                        lowerSceneContract: one('.head-stage').dataset.lowerSceneContract || '',
                        eyeContract: one('.head-stage').dataset.eyeContract || '',
                        headBounds: one('.head-stage').dataset.headBounds || '',
                        eyeAnchors: one('.head-stage').dataset.eyeAnchors || '',
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
                if engine == 'firefox' and metrics['headRenderer'] != 'webgl':
                    fail(
                        f'{width}px: Firefox-Test muss den kanonischen WebGL-Pfad '
                        f'validieren, erhalten={metrics["headRenderer"]!r}'
                    )
                if engine in {'chromium', 'firefox'} and metrics['webglInit'] not in {
                    'edge-webgl2',
                    'edge-webgl2-no-msaa',
                    'edge-webgl2-minimal',
                    'edge-three-managed-no-msaa',
                }:
                    fail(
                        f'{engine} {width}px: Browser verwendet nicht die gemeinsame '
                        f'Edge-WebGL-Initialisierung ({metrics["webglInit"]!r})'
                    )
                if metrics['lowerSceneContract'] != 'edge-shared-v1':
                    fail(
                        f'{engine} {width}px: Kopf verwendet nicht den gemeinsamen '
                        f'Edge/Firefox-Szenenvertrag ({metrics["lowerSceneContract"]!r})'
                    )
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
                    if engine == 'firefox':
                        if metrics['headRenderer'] == 'webgl':
                            if metrics['eyeContract'] != 'edge-shared-webgl':
                                fail(
                                    f'Firefox 1440px: Augen verwenden nicht den '
                                    f'Edge-WebGL-Vertrag ({metrics["eyeContract"]!r})'
                                )
                        else:
                            try:
                                bounds = [float(v) for v in metrics['headBounds'].split(',')]
                                eyes = [float(v) for v in metrics['eyeAnchors'].split(',')]
                            except ValueError:
                                fail(f'Firefox 1440px: ungültige Kopf-/Augen-Anker {metrics}')
                            if len(bounds) != 4 or len(eyes) != 4:
                                fail(f'Firefox 1440px: Augen-Anker fehlen {metrics}')
                            min_x, min_y, max_x, max_y = bounds
                            left_x, left_y, right_x, right_y = eyes
                            if not (
                                min_x <= left_x <= max_x and min_x <= right_x <= max_x
                                and min_y <= left_y <= max_y and min_y <= right_y <= max_y
                                and right_x - left_x >= 25
                            ):
                                fail(
                                    f'Firefox 1440px: Augen sitzen außerhalb der Kopfgeometrie '
                                    f'(bounds={bounds}, eyes={eyes})'
                                )
                        frame_stats = page.evaluate(
                            """async () => {
                              const samples = [];
                              await new Promise(resolve => {
                                let last = performance.now();
                                const tick = now => {
                                  samples.push(now - last);
                                  last = now;
                                  if (samples.length >= 48) resolve();
                                  else requestAnimationFrame(tick);
                                };
                                requestAnimationFrame(tick);
                              });
                              const sorted = samples.slice(4).sort((a,b) => a-b);
                              const percentile = p => sorted[
                                Math.min(sorted.length - 1, Math.floor(sorted.length * p))
                              ];
                              return {
                                median: percentile(.5),
                                p95: percentile(.95),
                                max: Math.max(...sorted),
                              };
                            }"""
                        )
                        if metrics['headRenderer'] == 'canvas2d':
                            if (
                                frame_stats['median'] > 35
                                or frame_stats['p95'] > 65
                                or frame_stats['max'] > 140
                            ):
                                fail(
                                    f'Firefox 1440px: Canvas2D-Animation ruckelt '
                                    f'(frame timings={frame_stats})'
                                )
                        else:
                            # GitHub/Xvfb has no physical GPU. Once Firefox is
                            # proven to use the canonical WebGL renderer, absolute
                            # rAF timings here describe the CI software renderer,
                            # not desktop Firefox performance. Keep them as a
                            # diagnostic and fail only on genuine render stalls.
                            print(
                                'FIREFOX WEBGL FRAME DIAGNOSTIC '
                                f'(Xvfb/software): {frame_stats}'
                            )
                            if frame_stats['max'] > 500:
                                fail(
                                    f'Firefox 1440px: WebGL animation stalls '
                                    f'(frame timings={frame_stats})'
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

            # Deterministic initial-state parity: disable motion so Firefox cannot
            # pass merely because a different animation frame happens to look close.
            parity_context = browser.new_context(
                viewport={'width': 1440, 'height': 1000},
                device_scale_factor=1,
                reduced_motion='reduce',
            )
            parity_page = parity_context.new_page()
            parity_page.goto(base, wait_until='networkidle')
            parity_page.wait_for_function(
                "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                timeout=15000,
            )
            parity_page.wait_for_timeout(250)
            parity_path = artifact_dir / f'{engine}-1440-parity.png'
            parity_page.screenshot(path=str(parity_path), full_page=False)
            parity_renderer = parity_page.evaluate(
                "document.querySelector('.head-stage')?.dataset.headRenderer || ''"
            )
            print(f'PARITY {engine}: renderer={parity_renderer}')
            parity_page.close()
            parity_context.close()

            if engine == 'chromium':
                if parity_renderer != 'webgl':
                    fail('Chromium parity reference must use WebGL')
            elif engine == 'firefox':
                if parity_renderer != 'webgl':
                    fail(
                        f'Firefox parity must use the canonical Edge/WebGL renderer, '
                        f'got {parity_renderer!r}'
                    )
                edge_parity = artifact_dir / 'chromium-1440-parity.png'
                if not edge_parity.is_file():
                    fail('Firefox parity: Chromium/Edge reference missing')
                visual = compare_head_render(edge_parity, parity_path)
                if visual['mae'] > 7.0:
                    fail(
                        f'Firefox parity: head differs from Edge '
                        f'(central MAE={visual["mae"]:.2f}, max=7.00)'
                    )
                if not 0.88 <= visual['bright_ratio'] <= 1.12:
                    fail(
                        f'Firefox parity: point energy differs from Edge '
                        f'(ratio={visual["bright_ratio"]:.3f}, allowed 0.88..1.12)'
                    )
                if not 0.72 <= visual['ground_bright_ratio'] <= 1.35:
                    fail(
                        f'Firefox parity: lower-scene light energy differs from Edge '
                        f'(ratio={visual["ground_bright_ratio"]:.3f}, allowed 0.72..1.35)'
                    )

            if engine == 'chromium':
                # Compatibility acceptance: simulate a browser/driver where the
                # canonical antialiased WebGL2 context has no EGL config, but a
                # no-MSAA WebGL2 context is available. The page must retry on a
                # fresh canvas and still use the exact same WebGL scene.
                compat_page = browser.new_page(
                    viewport={'width': 1440, 'height': 1000},
                    device_scale_factor=1,
                )
                compat_page.add_init_script(
                    """(() => {
                      const original = HTMLCanvasElement.prototype.getContext;
                      HTMLCanvasElement.prototype.getContext = function(type, options, ...rest) {
                        if (type === 'webgl2' && options?.antialias === true) {
                          return null;
                        }
                        return original.call(this, type, options, ...rest);
                      };
                    })();"""
                )
                compat_page.goto(base, wait_until='networkidle')
                compat_page.wait_for_function(
                    "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                    timeout=15000,
                )
                compat_result = compat_page.evaluate(
                    """() => {
                      const stage = document.querySelector('.head-stage');
                      return {
                        renderer: stage?.dataset.headRenderer || '',
                        init: stage?.dataset.webglInit || '',
                        attempts: stage?.dataset.webglAttempts || '',
                      };
                    }"""
                )
                if compat_result['renderer'] != 'webgl':
                    fail(f'WebGL compatibility retry fell back to Canvas: {compat_result}')
                if compat_result['init'] != 'edge-webgl2-no-msaa':
                    fail(
                        'WebGL compatibility retry did not select the no-MSAA '
                        f'Edge scene: {compat_result}'
                    )
                if not compat_result['attempts'].startswith(
                    'edge-webgl2,edge-webgl2-no-msaa'
                ):
                    fail(f'WebGL compatibility retry order invalid: {compat_result}')
                compat_page.close()

                # Runtime context-loss acceptance: a browser may start on WebGL
                # and lose the GPU context later. The old WebGL listeners must
                # be torn down before the Canvas emergency renderer takes over.
                context_loss_page = browser.new_page(
                    viewport={'width': 1440, 'height': 1000},
                    device_scale_factor=1,
                )
                context_loss_errors: list[str] = []
                context_loss_page.on(
                    'pageerror',
                    lambda exc: context_loss_errors.append(str(exc)),
                )
                context_loss_page.goto(base, wait_until='networkidle')
                context_loss_page.wait_for_function(
                    "document.querySelector('.head-stage')?.dataset.headRenderer === 'webgl' && "
                    "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                    timeout=15000,
                )
                lost = context_loss_page.evaluate(
                    """() => {
                      const canvas = document.querySelector('#particle-head');
                      const gl = canvas?.getContext('webgl2');
                      const ext = gl?.getExtension('WEBGL_lose_context');
                      if (!ext) return false;
                      ext.loseContext();
                      return true;
                    }"""
                )
                if not lost:
                    fail('WebGL context-loss test: WEBGL_lose_context unavailable')
                context_loss_page.wait_for_function(
                    "document.querySelector('.head-stage')?.dataset.headRenderer === 'canvas2d' && "
                    "document.querySelector('.head-stage')?.dataset.headReady === '1' && "
                    "document.querySelector('.head-fallback')?.dataset.ready === '1'",
                    timeout=15000,
                )
                context_loss_page.wait_for_timeout(250)
                context_loss_state = context_loss_page.evaluate(
                    """() => {
                      const stage = document.querySelector('.head-stage');
                      return {
                        renderer: stage?.dataset.headRenderer || '',
                        webglInit: stage?.dataset.webglInit || '',
                        webglCleanup: stage?.dataset.webglCleanup || '',
                        eyeContract: stage?.dataset.eyeContract || '',
                        fallbackVisible: document.querySelector('.head-fallback')?.hidden === false,
                        webglHidden: document.querySelector('#particle-head')?.hidden === true,
                        canvasCount: document.querySelectorAll('.head-fallback-canvas').length,
                      };
                    }"""
                )
                if context_loss_errors:
                    fail(
                        'WebGL context-loss transition raised browser JS error: '
                        f'{context_loss_errors[0]}'
                    )
                if context_loss_state != {
                    'renderer': 'canvas2d',
                    'webglInit': 'canvas-context-loss',
                    'webglCleanup': '1',
                    'eyeContract': '',
                    'fallbackVisible': True,
                    'webglHidden': True,
                    'canvasCount': 1,
                }:
                    fail(
                        'WebGL context-loss transition did not cleanly hand off '
                        f'to one Canvas renderer: {context_loss_state}'
                    )
                context_loss_page.close()

                # Strong-beacon position parity: the six sampled glowing nodes
                # must land at the same screen coordinates in canonical WebGL
                # and in the forced Canvas fallback, including pointer parallax.
                async_probe_js = """() => {
                  const raw = document.querySelector('.head-stage')?.dataset.beaconProbe || '';
                  return raw ? raw.split(',').map(Number) : [];
                }"""
                beacon_webgl = browser.new_page(
                    viewport={'width': 1440, 'height': 1000},
                    device_scale_factor=1,
                )
                beacon_webgl.goto(base, wait_until='networkidle')
                beacon_webgl.wait_for_function(
                    "document.querySelector('.head-stage')?.dataset.headRenderer === 'webgl' && "
                    "document.querySelector('.head-stage')?.dataset.headReady === '1' && "
                    "document.querySelector('.head-stage')?.dataset.beaconProbe",
                    timeout=15000,
                )
                beacon_webgl.mouse.move(1120, 260)
                beacon_webgl.wait_for_timeout(2200)
                webgl_probe = beacon_webgl.evaluate(async_probe_js)
                webgl_yaw = float(
                    beacon_webgl.evaluate(
                        "document.querySelector('.head-stage')?.dataset.headYaw || '0'"
                    )
                )
                beacon_webgl.close()

                beacon_canvas = browser.new_page(
                    viewport={'width': 1440, 'height': 1000},
                    device_scale_factor=1,
                )
                beacon_canvas.add_init_script(
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
                beacon_canvas.goto(base, wait_until='networkidle')
                beacon_canvas.wait_for_function(
                    "document.querySelector('.head-stage')?.dataset.headRenderer === 'canvas2d' && "
                    "document.querySelector('.head-stage')?.dataset.headReady === '1' && "
                    "document.querySelector('.head-stage')?.dataset.beaconProbe",
                    timeout=15000,
                )
                beacon_canvas.mouse.move(1120, 260)
                beacon_canvas.wait_for_timeout(2200)
                canvas_probe = beacon_canvas.evaluate(async_probe_js)
                canvas_yaw = float(
                    beacon_canvas.evaluate(
                        "document.querySelector('.head-stage')?.dataset.headYaw || '0'"
                    )
                )
                beacon_canvas.close()

                if len(webgl_probe) != 12 or len(canvas_probe) != 12:
                    fail(
                        'Beacon parity: expected six XY coordinate pairs, got '
                        f'WebGL={webgl_probe}, Canvas={canvas_probe}'
                    )
                beacon_deltas = [
                    abs(float(a) - float(b))
                    for a, b in zip(webgl_probe, canvas_probe, strict=True)
                ]
                beacon_max_delta = max(beacon_deltas)
                print(
                    'BEACON POSITION PARITY chromium: '
                    f'max_delta={beacon_max_delta:.1f}px '
                    f'webgl={webgl_probe} canvas={canvas_probe}'
                )
                if beacon_max_delta > 4:
                    fail(
                        'Beacon parity: strong glowing points do not match Edge '
                        f'(max coordinate delta={beacon_max_delta:.1f}px > 4px)'
                    )
                yaw_delta = abs(webgl_yaw - canvas_yaw)
                print(
                    'HEAD YAW PARITY chromium: '
                    f'webgl={webgl_yaw:.4f} canvas={canvas_yaw:.4f} '
                    f'delta={yaw_delta:.4f}'
                )
                if webgl_yaw < .12 or canvas_yaw < .12:
                    fail(
                        'Head motion parity: head did not visibly follow the pointer '
                        f'(WebGL={webgl_yaw:.4f}, Canvas={canvas_yaw:.4f})'
                    )
                if yaw_delta > .035:
                    fail(
                        'Head motion parity: Canvas head response differs from Edge '
                        f'(yaw delta={yaw_delta:.4f} > 0.035)'
                    )

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
                  headRenderer: document.querySelector('.head-stage')?.dataset.headRenderer || '',
                  webglInit: document.querySelector('.head-stage')?.dataset.webglInit || '',
                  canvasDrawMs: parseFloat(
                    document.querySelector('.head-stage')?.dataset.canvasDrawMs || '9999'
                  ),
                  canvasDrawPeakMs: parseFloat(
                    document.querySelector('.head-stage')?.dataset.canvasDrawPeakMs || '9999'
                  ),
                  canvasFrames: parseInt(
                    document.querySelector('.head-stage')?.dataset.canvasFrames || '0', 10
                  ),
                  canvasElapsed: parseFloat(
                    document.querySelector('.head-stage')?.dataset.canvasElapsed || '0'
                  ),
                  headYaw: parseFloat(
                    document.querySelector('.head-stage')?.dataset.headYaw || '0'
                  ),
                  canvasOcclusion: document.querySelector('.head-stage')?.dataset.canvasOcclusion || '',
                  starProbe: document.querySelector('.head-stage')?.dataset.starProbe || '',
                })"""
            )
            print(f'NO-WEBGL CANVAS DIAGNOSTIC {engine}: {fallback_metrics}')
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
            if fallback_metrics['headRenderer'] != 'canvas2d':
                fail(f'No-WebGL: falscher Renderer {fallback_metrics["headRenderer"]!r}')
            if fallback_metrics['webglInit'] != 'canvas-emergency':
                fail(f'No-WebGL: falscher WebGL-Fallbackstatus {fallback_metrics["webglInit"]!r}')
            if fallback_metrics['canvasOcclusion'] != 'head-silhouette-v1':
                fail(
                    'No-WebGL: Kopf-Occlusion fehlt; Sternschnuppen/Lichter können '
                    'durch Gesicht oder Hals scheinen'
                )
            if fallback_metrics['canvasFrames'] < 6:
                fail(
                    f'No-WebGL: zu wenige Canvas-Frames für Performancebewertung '
                    f'({fallback_metrics["canvasFrames"]})'
                )
            if fallback_metrics['canvasDrawMs'] > 55:
                fail(
                    f'No-WebGL: aktuelle Canvas2D-Zeichenzeit zu hoch '
                    f'({fallback_metrics["canvasDrawMs"]:.1f} ms > 55 ms)'
                )
            if fallback_metrics['canvasDrawPeakMs'] > 85:
                fail(
                    f'No-WebGL: Canvas2D-Spitzenlast nach Warm-up zu hoch '
                    f'({fallback_metrics["canvasDrawPeakMs"]:.1f} ms > 85 ms)'
                )

            motion_start = fallback_page.evaluate(
                """() => {
                  const stage = document.querySelector('.head-stage');
                  return {
                    elapsed: parseFloat(stage?.dataset.canvasElapsed || '0'),
                    frames: parseInt(stage?.dataset.canvasFrames || '0', 10),
                  };
                }"""
            )
            fallback_page.mouse.move(1300, 500)
            fallback_page.wait_for_timeout(1200)
            motion_end = fallback_page.evaluate(
                """() => {
                  const stage = document.querySelector('.head-stage');
                  return {
                    elapsed: parseFloat(stage?.dataset.canvasElapsed || '0'),
                    frames: parseInt(stage?.dataset.canvasFrames || '0', 10),
                    yaw: parseFloat(stage?.dataset.headYaw || '0'),
                  };
                }"""
            )
            elapsed_delta = motion_end['elapsed'] - motion_start['elapsed']
            frame_delta = motion_end['frames'] - motion_start['frames']
            print(
                f'NO-WEBGL MOTION DIAGNOSTIC {engine}: '
                f'elapsed_delta={elapsed_delta:.3f}s '
                f'frame_delta={frame_delta} yaw={motion_end["yaw"]:.4f}'
            )
            if not .85 <= elapsed_delta <= 1.50:
                fail(
                    'No-WebGL: Animationszeit läuft nicht in Echtzeit '
                    f'(1.2s wall clock -> {elapsed_delta:.3f}s animation)'
                )
            if frame_delta < 12:
                fail(
                    'No-WebGL: Canvas liefert zu wenige bewegte Frames '
                    f'({frame_delta} Frames in 1.2s)'
                )
            if motion_end['yaw'] < .12:
                fail(
                    'No-WebGL: Kopf reagiert zu schwach auf Mausbewegung '
                    f'(yaw={motion_end["yaw"]:.4f})'
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

            fallback_page.wait_for_function(
                "document.querySelector('.head-stage')?.dataset.starProbe",
                timeout=7000,
            )
            star_pair = None
            # Canvas frames can take longer than one short polling interval on a
            # contended CI runner. Only accept two samples after the same star
            # has demonstrably advanced; identical snapshots are not evidence
            # of a frozen animation and must be retried.
            for _ in range(20):
                first = fallback_page.evaluate(
                    "document.querySelector('.head-stage')?.dataset.starProbe || ''"
                )
                fallback_page.wait_for_timeout(140)
                second = fallback_page.evaluate(
                    "document.querySelector('.head-stage')?.dataset.starProbe || ''"
                )
                if not first or not second:
                    continue
                first_parts = first.split(',')
                second_parts = second.split(',')
                if first_parts[0] != second_parts[0]:
                    continue
                try:
                    first_progress = float(first_parts[4])
                    second_progress = float(second_parts[4])
                except (IndexError, ValueError):
                    continue
                if second_progress <= first_progress:
                    continue
                star_pair = (first, second)
                break
            if not star_pair:
                fail(
                    'No-WebGL: Sternschnuppe hat sich innerhalb des '
                    'Beobachtungsfensters nicht messbar weiterbewegt'
                )
            first_parts = star_pair[0].split(',')
            second_parts = star_pair[1].split(',')
            _, x1, y1, direction1, progress1 = map(float, first_parts)
            _, x2, y2, direction2, progress2 = map(float, second_parts)
            if direction1 != direction2 or progress2 <= progress1:
                fail(f'No-WebGL: ungültige Sternschnuppen-Probe {star_pair}')
            if y2 <= y1:
                fail(
                    f'No-WebGL: Sternschnuppe fliegt im Bildschirm nach oben statt '
                    f'wie Edge nach unten ({y1:.1f} -> {y2:.1f})'
                )
            if direction1 > 0 and x2 <= x1:
                fail(f'No-WebGL: LTR-Sternschnuppe hat falsche X-Richtung {star_pair}')
            if direction1 < 0 and x2 >= x1:
                fail(f'No-WebGL: RTL-Sternschnuppe hat falsche X-Richtung {star_pair}')
            fallback_page.close()

            # Deterministic visual parity for the exact no-WebGL path. Freeze
            # motion in both renders so animation phase cannot hide a geometry,
            # brightness or lower-scene regression.
            fallback_parity_context = browser.new_context(
                viewport={'width': 1440, 'height': 1000},
                device_scale_factor=1,
                reduced_motion='reduce',
            )
            fallback_parity_page = fallback_parity_context.new_page()
            fallback_parity_page.add_init_script(
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
            fallback_parity_page.goto(base, wait_until='networkidle')
            fallback_parity_page.wait_for_function(
                "document.querySelector('.head-stage')?.dataset.headRenderer === 'canvas2d' && "
                "document.querySelector('.head-stage')?.dataset.headReady === '1'",
                timeout=15000,
            )
            fallback_parity_page.wait_for_timeout(250)
            fallback_parity_path = artifact_dir / f'{engine}-1440-no-webgl-parity.png'
            fallback_parity_page.screenshot(
                path=str(fallback_parity_path),
                full_page=False,
            )
            fallback_parity_page.close()
            fallback_parity_context.close()

            edge_parity = artifact_dir / 'chromium-1440-parity.png'
            if not edge_parity.is_file():
                fail('No-WebGL parity: Chromium/Edge reference missing')
            fallback_visual = compare_head_render(edge_parity, fallback_parity_path)
            print(f'NO-WEBGL VISUAL PARITY {engine}: {fallback_visual}')
            if fallback_visual['mae'] > 9.0:
                fail(
                    f'No-WebGL parity: head differs too strongly from Edge '
                    f'(central MAE={fallback_visual["mae"]:.2f}, max=9.00)'
                )
            if not 0.65 <= fallback_visual['bright_ratio'] <= 1.35:
                fail(
                    f'No-WebGL parity: head point energy differs from Edge '
                    f'(ratio={fallback_visual["bright_ratio"]:.3f}, allowed 0.65..1.35)'
                )
            if not 0.65 <= fallback_visual['ground_bright_ratio'] <= 1.45:
                fail(
                    f'No-WebGL parity: lower-scene light energy differs from Edge '
                    f'(ratio={fallback_visual["ground_bright_ratio"]:.3f}, allowed 0.65..1.45)'
                )

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
