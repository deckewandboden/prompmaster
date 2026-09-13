#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env'


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f'[FEHLER] {path} fehlt.')
    for line in path.read_text(encoding='utf-8').splitlines():
        raw = line.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def is_placeholder(value: str) -> bool:
    v = (value or '').strip().lower()
    return (
        not v
        or v in {'change_me', 'generate_with_fernet', 'changeme'}
        or 'example.com' in v
        or v.endswith('.invalid')
    )


def check_fernet(value: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(value.encode('ascii'))
        return len(raw) == 32 and len(value) == 44
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--environment', choices=('staging', 'production'), required=True)
    ap.add_argument('--env-file', default=str(ENV_FILE))
    args = ap.parse_args()
    path = Path(args.env_file)
    values = parse_env(path)
    errors: list[str] = []

    expected = args.environment
    if values.get('ENVIRONMENT', '').strip().lower() != expected:
        fail(errors, f'ENVIRONMENT muss {expected!r} sein.')

    domain = values.get('CADDY_DOMAIN', '').strip().lower()
    if expected == 'production' and (is_placeholder(domain) or domain in {'localhost', '127.0.0.1'}):
        fail(errors, 'CADDY_DOMAIN muss für Produktion eine reale Domain sein.')
    if expected == 'staging' and not domain:
        fail(errors, 'CADDY_DOMAIN fehlt.')
    if domain and domain not in {'localhost', '127.0.0.1'} and not re.fullmatch(r'[a-z0-9.-]+', domain):
        fail(errors, 'CADDY_DOMAIN enthält ungültige Zeichen.')

    secret = values.get('DJANGO_SECRET_KEY', '')
    if is_placeholder(secret) or len(secret) < 40:
        fail(errors, 'DJANGO_SECRET_KEY muss mindestens 40 Zeichen lang und kein Platzhalter sein.')
    dbpass = values.get('POSTGRES_PASSWORD', '')
    if is_placeholder(dbpass) or len(dbpass) < 20:
        fail(errors, 'POSTGRES_PASSWORD muss mindestens 20 Zeichen lang und kein Platzhalter sein.')
    if not check_fernet(values.get('APP_ENCRYPTION_KEY', '')):
        fail(errors, 'APP_ENCRYPTION_KEY ist kein gültiger 32-Byte-Fernet-Schlüssel.')

    for flag in ('SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
        if values.get(flag) != '1':
            fail(errors, f'{flag} muss auf 1 stehen.')
    if expected == 'production' and values.get('SECURE_SSL_REDIRECT') != '1':
        fail(errors, 'SECURE_SSL_REDIRECT muss in Produktion 1 sein.')

    allowed = {x.strip().lower() for x in values.get('ALLOWED_HOSTS', '').split(',') if x.strip()}
    if domain and domain not in allowed:
        fail(errors, 'CADDY_DOMAIN muss in ALLOWED_HOSTS enthalten sein.')
    csrf = {x.strip().lower() for x in values.get('CSRF_TRUSTED_ORIGINS', '').split(',') if x.strip()}
    if domain not in {'localhost', '127.0.0.1', ''} and f'https://{domain}' not in csrf:
        fail(errors, 'https://CADDY_DOMAIN muss in CSRF_TRUSTED_ORIGINS enthalten sein.')

    webhook = values.get('MOLLIE_WEBHOOK_BASE', '').rstrip('/')
    if expected == 'production' and webhook != f'https://{domain}':
        fail(errors, 'MOLLIE_WEBHOOK_BASE muss in Produktion exakt https://CADDY_DOMAIN entsprechen.')

    provider = values.get('EMAIL_PROVIDER', '').strip().lower()
    if expected == 'production':
        if provider not in {'graph', 'microsoft_graph'}:
            fail(errors, 'Production EMAIL_PROVIDER muss graph/microsoft_graph sein.')
        for key in ('GRAPH_TENANT_ID', 'GRAPH_CLIENT_ID', 'GRAPH_CLIENT_SECRET', 'GRAPH_SENDER'):
            if is_placeholder(values.get(key, '')):
                fail(errors, f'{key} muss für Microsoft Graph gesetzt sein.')
        mollie = values.get('MOLLIE_API_KEY', '')
        if not mollie.startswith('live_'):
            fail(errors, 'MOLLIE_API_KEY muss in Produktion ein Mollie-Live-Key (live_…) sein.')

        repo = values.get('RESTIC_REPOSITORY', '')
        if is_placeholder(repo) or not (repo.startswith('s3:') or repo.startswith('s3://')):
            fail(errors, 'RESTIC_REPOSITORY muss in Produktion auf externen S3-kompatiblen Storage zeigen.')
        if is_placeholder(values.get('RESTIC_PASSWORD', '')) or len(values.get('RESTIC_PASSWORD', '')) < 20:
            fail(errors, 'RESTIC_PASSWORD muss sicher gesetzt sein.')
        for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
            if is_placeholder(values.get(key, '')):
                fail(errors, f'{key} muss für Production-Backup gesetzt sein.')
        if values.get('INITIAL_ADMIN_PASSWORD', '') not in {'', 'DISABLED'}:
            fail(errors, 'INITIAL_ADMIN_PASSWORD darf nach Bootstrap in Produktion nicht aktiv konfiguriert bleiben.')
    else:
        # Staging must never accidentally use live payments.
        if values.get('MOLLIE_API_KEY', '').startswith('live_'):
            fail(errors, 'Staging darf keinen Mollie-Live-Key verwenden.')
        if provider not in {'smtp', 'mailpit'}:
            fail(errors, 'Staging EMAIL_PROVIDER muss smtp/mailpit sein, damit keine echten Kundenmails versendet werden.')

    if errors:
        for item in errors:
            print(f'[FEHLER] {item}', file=sys.stderr)
        return 1
    print(f'ENV VALIDATION OK ({expected})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
