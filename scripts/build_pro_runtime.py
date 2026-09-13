#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'product' / 'golden_masters' / 'promptmaster_pro.html'
BRIDGE = ROOT / 'product' / 'runtime' / 'pro_server_bridge.js'
OUTPUT = ROOT / 'backend' / 'private_assets' / 'promptmaster_pro_runtime.html'
GOLDEN_SHA256 = 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> bytes:
    golden = GOLDEN.read_bytes()
    if sha(golden) != GOLDEN_SHA256:
        raise SystemExit('Refusing runtime build: Pro Golden Master hash mismatch.')
    html = golden.decode('utf-8')
    bridge = BRIDGE.read_text(encoding='utf-8')
    if '__PM_CSRF_TOKEN__' not in bridge:
        raise SystemExit('Runtime bridge is missing CSRF placeholder.')
    marker = '</body></html>'
    if html.count(marker) != 1:
        raise SystemExit('Unexpected Pro Golden Master closing markup.')
    runtime = html.replace(marker, f'<script>\n{bridge}\n</script>{marker}')
    return runtime.encode('utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Fail if committed runtime differs from deterministic rebuild.')
    args = parser.parse_args()
    data = build()
    digest = sha(data)
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != data:
            raise SystemExit('PRO RUNTIME CHECK FAILED: rebuild differs from committed runtime asset.')
        print(f'PRO RUNTIME OK: {digest}')
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    print(f'PRO RUNTIME BUILT: {OUTPUT} SHA256={digest}')


if __name__ == '__main__':
    main()
