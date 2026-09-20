#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.getenv('PM_LOAD_BASE_URL', 'https://localhost').rstrip('/')
WORKERS = int(os.getenv('PM_LOAD_WORKERS', '32'))
REQUESTS = int(os.getenv('PM_LOAD_REQUESTS', '640'))
TIMEOUT = float(os.getenv('PM_LOAD_TIMEOUT', '12'))
PATHS = ('/', '/health/live/', '/health/ready/', '/catalog.json', '/auth/login/')
SSL_CONTEXT = ssl._create_unverified_context() if BASE.startswith('https://localhost') else None


def fetch(path):
    started = time.perf_counter()
    request = urllib.request.Request(
        BASE + path,
        headers={'User-Agent': 'PromptMaster-Release-Load-Smoke/1.0', 'Accept': '*/*'},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=SSL_CONTEXT) as response:
            body = response.read(2_500_000)
            status = response.status
    except Exception as exc:
        return path, None, time.perf_counter() - started, f'{type(exc).__name__}: {exc}'
    return path, status, time.perf_counter() - started, body


def validate_once(path):
    path, status, elapsed, result = fetch(path)
    if status != 200:
        raise SystemExit(f'LOAD PREFLIGHT FAIL: {path} returned {status}: {result!r}')
    if path == '/catalog.json':
        payload = json.loads(result.decode('utf-8'))
        products = {
            item.get('id'): item
            for item in payload.get('products', [])
            if isinstance(item, dict) and item.get('id')
        }
        pro = products.get('PROMPTMASTER_PRO') or {}
        names = payload.get('proApplicationNames') or []
        contract_ok = (
            payload.get('currency') == 'EUR'
            and payload.get('priceBasis') == 'gross'
            and payload.get('taxBasisPoints') == 1900
            and payload.get('market') == 'DE'
            and payload.get('maxQuantity') == 500
            and payload.get('checkoutEnabled') is True
            and payload.get('loginEnabled') is True
            and payload.get('proApplicationCount') == 34
            and len(names) == 34
            and len(set(names)) == 34
            and pro.get('monthlyGrossCents') == 299
            and pro.get('annualGrossCents') == 3588
            and pro.get('termMonths') == 12
            and pro.get('active') is True
            and pro.get('purchasable') is True
        )
        if not contract_ok:
            raise SystemExit(f'LOAD PREFLIGHT FAIL: catalog contract drift: {payload}')
    return elapsed


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main():
    if WORKERS < 1 or REQUESTS < len(PATHS):
        raise SystemExit('LOAD SMOKE FAIL: invalid workers/request count')
    for path in PATHS:
        validate_once(path)

    durations = []
    failures = []
    statuses = {}
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(fetch, PATHS[i % len(PATHS)]) for i in range(REQUESTS)]
        for future in as_completed(futures):
            path, status, elapsed, result = future.result()
            durations.append(elapsed)
            statuses[(path, status)] = statuses.get((path, status), 0) + 1
            if status != 200:
                failures.append((path, status, result if isinstance(result, str) else repr(result[:180])))

    wall = time.perf_counter() - started
    if failures:
        raise SystemExit(
            f'LOAD SMOKE FAIL: {len(failures)}/{REQUESTS} requests failed: {failures[:12]}'
        )

    for path in PATHS:
        validate_once(path)

    print(
        'HTTP LOAD SMOKE OK: '
        f'{REQUESTS} requests, {WORKERS} workers, {REQUESTS / max(wall, .001):.1f} req/s, '
        f'p50={percentile(durations,.50):.3f}s '
        f'p95={percentile(durations,.95):.3f}s '
        f'p99={percentile(durations,.99):.3f}s '
        f'max={max(durations):.3f}s mean={statistics.fmean(durations):.3f}s '
        f'statuses={statuses}'
    )


if __name__ == '__main__':
    main()
