#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / 'marketing'

required = [
    'index.html', 'package.json', 'package-lock.json', 'vite.marketing.config.js',
    'src/main.js', 'src/content.js', 'src/head.js', 'src/head-canvas2d.js', 'src/style.css', 'src/immersive.css',
    'public/models/head.glb', 'public/models/night-landscape.png',
    'public/brand/design-reference.jpeg', 'public/brand/promptmaster-logo-clean.svg', 'public/integration-patch.js',
    'dist/index.html', 'dist/integration-patch.js', 'dist/models/head.glb',
]
missing = [name for name in required if not (MARKETING / name).exists()]
if missing:
    raise SystemExit('MARKETING VALIDATION FAIL: missing ' + ', '.join(missing))

catalog = json.loads((MARKETING / 'public/catalog.json').read_text(encoding='utf-8'))
if catalog.get('priceBasis') != 'gross' or catalog.get('market') != 'DE':
    raise SystemExit('MARKETING VALIDATION FAIL: static fallback catalog contract drift')
pro = next((p for p in catalog.get('products', []) if p.get('id') == 'PROMPTMASTER_PRO'), None)
if not pro or pro.get('monthlyGrossCents') != 299 or pro.get('termMonths') != 12:
    raise SystemExit('MARKETING VALIDATION FAIL: fallback Pro price drift')

source = (MARKETING / 'src/content.js').read_text(encoding='utf-8')
index = (MARKETING / 'index.html').read_text(encoding='utf-8')
patch = (MARKETING / 'public/integration-patch.js').read_text(encoding='utf-8')
immersive_css = (MARKETING / 'src/immersive.css').read_text(encoding='utf-8')
if "url('/brand/promptmaster-logo-clean.svg')" not in immersive_css:
    raise SystemExit('MARKETING VALIDATION FAIL: active header still uses screenshot-cropped logo')
if "background-image:url('/brand/design-reference.jpeg')" in immersive_css:
    raise SystemExit('MARKETING VALIDATION FAIL: screenshot-cropped logo regression returned')
marketing_logo = (MARKETING / 'public/brand/promptmaster-logo-clean.svg').read_text(encoding='utf-8')
for marker in ('viewBox="0 3 315 59"', 'width="315" height="62"', 'data:image/png;base64,'):
    if marker not in marketing_logo:
        raise SystemExit(f'MARKETING VALIDATION FAIL: approved cropped PromptMaster artwork missing {marker}')
pro_apps_match = re.search(r"const proApps=\[(.*?)\];", source, re.S)
if not pro_apps_match:
    raise SystemExit('MARKETING VALIDATION FAIL: Pro application catalog missing')
pro_apps = re.findall(r"'([^']+)'", pro_apps_match.group(1))
if len(pro_apps) != 28:
    raise SystemExit(f'MARKETING VALIDATION FAIL: expected 28 additional Pro apps, got {len(pro_apps)}')
for marker in ('Erweiterter Copilot-Katalog', 'Laufende Weiterentwicklungen inklusive'):
    if marker not in index:
        raise SystemExit(f'MARKETING VALIDATION FAIL: recovered V15 hero marker missing: {marker}')
if '/catalog.json' not in patch or 'proApplicationNames' not in patch:
    raise SystemExit('MARKETING VALIDATION FAIL: live catalog integration bridge missing')

head = (MARKETING / 'src/head.js').read_text(encoding='utf-8')
head_fallback = (MARKETING / 'src/head-canvas2d.js').read_text(encoding='utf-8')
for forbidden in ('pm-headtrack', 'getUserMedia', 'enumerateDevices'):
    if forbidden in head or forbidden in head_fallback:
        raise SystemExit(f'MARKETING VALIDATION FAIL: removed camera tracking remains: {forbidden}')
for needle in ("initCanvasHead", "getContext('2d'", '/models/head.glb'):
    if needle not in head + head_fallback:
        raise SystemExit(f'MARKETING VALIDATION FAIL: cross-browser head fallback missing {needle}')

caddy = (ROOT / 'Caddyfile').read_text(encoding='utf-8')
external_caddy = (ROOT / 'Caddyfile.external').read_text(encoding='utf-8')
overlay = (ROOT / 'compose.external-caddy.yaml').read_text(encoding='utf-8')
for needle in ('/srv/marketing', 'handle /catalog.json', '/auth/*', '/pro/*', '/portal/*', '/ns-admin/*'):
    if needle not in caddy:
        raise SystemExit(f'MARKETING VALIDATION FAIL: Caddy integration missing {needle}')

compatibility_redirects = (
    ('handle /login* {', 'redir * /auth/login/{?query} 302'),
    ('handle /checkout* {', 'redir * /portal/licenses/buy/{?query} 302'),
    ('handle /app/pro* {', 'redir * /pro/{?query} 302'),
    ('handle /portal {', 'redir * /portal/dashboard/{?query} 302'),
    ('handle /portal/ {', 'redir * /portal/dashboard/{?query} 302'),
    ('handle /datenschutz* {', 'redir * /legal/privacy/{?query} 302'),
    ('handle /agb* {', 'redir * /legal/terms/{?query} 302'),
    ('handle /lizenzbedingungen* {', 'redir * /legal/license/{?query} 302'),
    ('handle /widerruf* {', 'redir * /legal/withdrawal/{?query} 302'),
)
for route, redirect in compatibility_redirects:
    if route not in caddy or redirect not in caddy:
        raise SystemExit(
            f'MARKETING VALIDATION FAIL: compatibility redirect contract missing: '
            f'{route} -> {redirect}'
        )

for ambiguous in (
    'redir /auth/login/ 302',
    'redir /portal/licenses/buy/ 302',
    'redir /pro/ 302',
    'redir /portal/dashboard/ 302',
):
    if ambiguous in caddy:
        raise SystemExit(
            f'MARKETING VALIDATION FAIL: ambiguous Caddy redirect syntax remains: {ambiguous}'
        )

for config_text, label in ((caddy, 'Caddyfile'), (external_caddy, 'Caddyfile.external')):
    for needle in ('@sensitive_source', '/.env', '/.git/*', '/Dockerfile', '/compose.yaml', 'respond 404'):
        if needle not in config_text:
            raise SystemExit(f'MARKETING VALIDATION FAIL: {label} sensitive-path guard missing {needle}')
for needle in ('http://{$CADDY_DOMAIN}', 'promptmaster-web-internal:8000', 'trusted_proxies static private_ranges', 'trusted_proxies_strict', 'header_up X-Forwarded-Proto https', 'header_up X-Forwarded-For {client_ip}'):
    if needle not in external_caddy:
        raise SystemExit(f'MARKETING VALIDATION FAIL: external Caddy bridge missing {needle}')
if 'reverse_proxy web:8000' in external_caddy:
    raise SystemExit('MARKETING VALIDATION FAIL: external Caddy bridge retains ambiguous web upstream')
for needle in ('ports: !override []', 'Caddyfile.external:/etc/caddy/Caddyfile:ro', 'promptmaster-web-internal', 'promptmaster-caddy-edge', 'PM_EXTERNAL_CADDY_NETWORK'):
    if needle not in overlay:
        raise SystemExit(f'MARKETING VALIDATION FAIL: external Caddy compose overlay missing {needle}')

compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
if 'dockerfile: Dockerfile.caddy' not in compose:
    raise SystemExit('MARKETING VALIDATION FAIL: Caddy is not built from Dockerfile.caddy')
dockerfile = (ROOT / 'Dockerfile.caddy').read_text(encoding='utf-8')
for needle in ('COPY marketing/package.json marketing/package-lock.json', 'npm ci', 'npm run build', 'COPY --from=marketing-build /src/dist /srv/marketing'):
    if needle not in dockerfile:
        raise SystemExit(f'MARKETING VALIDATION FAIL: Dockerfile.caddy missing {needle}')

print('MARKETING VALIDATION OK: source, deploy artifact, 34-app bridge, Caddy routing + external-proxy deployment contract')
