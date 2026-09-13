#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / 'marketing'

required = [
    'index.html', 'package.json', 'package-lock.json', 'vite.marketing.config.js',
    'src/main.js', 'src/content.js', 'src/head.js', 'src/style.css', 'src/immersive.css',
    'public/models/head.glb', 'public/models/night-landscape.png',
    'public/brand/design-reference.jpeg', 'public/integration-patch.js',
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
if '28 zusätzliche Microsoft-Anwendungen' not in source:
    raise SystemExit('MARKETING VALIDATION FAIL: current 34-app/28-additional catalog text missing')
if '28 weitere Anwendungen' not in index:
    raise SystemExit('MARKETING VALIDATION FAIL: Pro hero count not synchronized')
if '/catalog.json' not in patch or 'proApplicationNames' not in patch:
    raise SystemExit('MARKETING VALIDATION FAIL: live catalog integration bridge missing')

caddy = (ROOT / 'Caddyfile').read_text(encoding='utf-8')
for needle in ('/srv/marketing', 'handle /catalog.json', '/auth/*', '/pro/*', '/portal/*', '/ns-admin/*'):
    if needle not in caddy:
        raise SystemExit(f'MARKETING VALIDATION FAIL: Caddy integration missing {needle}')
compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
if 'dockerfile: Dockerfile.caddy' not in compose:
    raise SystemExit('MARKETING VALIDATION FAIL: Caddy is not built from Dockerfile.caddy')
dockerfile = (ROOT / 'Dockerfile.caddy').read_text(encoding='utf-8')
for needle in ('COPY marketing/package.json marketing/package-lock.json', 'npm ci', 'npm run build', 'COPY --from=marketing-build /src/dist /srv/marketing'):
    if needle not in dockerfile:
        raise SystemExit(f'MARKETING VALIDATION FAIL: Dockerfile.caddy missing {needle}')

print('MARKETING VALIDATION OK: source, deploy artifact, 34-app bridge, Caddy routing')
