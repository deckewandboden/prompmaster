#!/usr/bin/env python3
"""Create/repair a staging .env without ever overwriting real configured secrets.

Only cryptographic values and safe staging defaults are generated. Production
provider credentials are never invented. Generated bootstrap credentials are
written once to .bootstrap-credentials with mode 0600.
"""
from __future__ import annotations

import base64
import os
import secrets
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / '.env'
EXAMPLE = ROOT / '.env.example'
CREDS = ROOT / '.bootstrap-credentials'


def parse(text: str) -> tuple[list[str], dict[str, str]]:
    lines = text.splitlines()
    values: dict[str, str] = {}
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        values[key.strip()] = value.strip()
    return lines, values


def serialise(template_lines: list[str], values: dict[str, str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in template_lines:
        raw = line.strip()
        if raw and not raw.startswith('#') and '=' in raw:
            key = raw.split('=', 1)[0].strip()
            if key in values:
                out.append(f'{key}={values[key]}')
                seen.add(key)
                continue
        out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f'{key}={value}')
    return '\n'.join(out).rstrip() + '\n'


def placeholder(value: str, *needles: str) -> bool:
    value = (value or '').strip()
    return not value or value in needles or 'example.com' in value


def hostname_default() -> str:
    supplied = os.environ.get('PM_DOMAIN', '').strip()
    if supplied:
        return supplied
    fqdn = socket.getfqdn().strip().lower()
    if fqdn and fqdn not in {'localhost', 'localhost.localdomain'} and '.' in fqdn:
        return fqdn
    return 'localhost'


if not ENV.exists():
    ENV.write_text(EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')

template_lines, defaults = parse(EXAMPLE.read_text(encoding='utf-8'))
_, current = parse(ENV.read_text(encoding='utf-8'))
values = defaults | current

generated: dict[str, str] = {}

domain = values.get('CADDY_DOMAIN', '')
if placeholder(domain):
    domain = hostname_default()
    values['CADDY_DOMAIN'] = domain

if placeholder(values.get('DJANGO_SECRET_KEY', ''), 'CHANGE_ME'):
    values['DJANGO_SECRET_KEY'] = secrets.token_urlsafe(64)
if placeholder(values.get('POSTGRES_PASSWORD', ''), 'CHANGE_ME'):
    values['POSTGRES_PASSWORD'] = secrets.token_urlsafe(32)
if placeholder(values.get('APP_ENCRYPTION_KEY', ''), 'GENERATE_WITH_FERNET'):
    values['APP_ENCRYPTION_KEY'] = base64.urlsafe_b64encode(os.urandom(32)).decode('ascii')
if placeholder(values.get('RESTIC_PASSWORD', ''), 'CHANGE_ME'):
    values['RESTIC_PASSWORD'] = secrets.token_urlsafe(32)

# A fresh staging installation must be able to exercise backup + restore even
# before external object-storage credentials exist. Use a Docker named volume
# as a local restic repository only for staging placeholders. Production env
# validation still requires an external S3-compatible repository and keys.
if values.get('ENVIRONMENT', '').strip().lower() == 'staging':
    repo = values.get('RESTIC_REPOSITORY', '')
    access_key = values.get('AWS_ACCESS_KEY_ID', '')
    secret_key = values.get('AWS_SECRET_ACCESS_KEY', '')
    if placeholder(repo) or placeholder(access_key, 'CHANGE_ME') or placeholder(secret_key, 'CHANGE_ME'):
        values['RESTIC_REPOSITORY'] = '/repository'

admin_email = values.get('INITIAL_ADMIN_EMAIL', '')
if placeholder(admin_email) or admin_email == 'admin@example.com':
    values['INITIAL_ADMIN_EMAIL'] = os.environ.get('PM_ADMIN_EMAIL', '').strip() or (
        f'admin@{domain}' if domain != 'localhost' else 'admin@local.invalid'
    )
if placeholder(values.get('INITIAL_ADMIN_PASSWORD', ''), 'CHANGE_ME'):
    generated['INITIAL_ADMIN_PASSWORD'] = secrets.token_urlsafe(20)
    values['INITIAL_ADMIN_PASSWORD'] = generated['INITIAL_ADMIN_PASSWORD']

# Keep dependent URL/security host settings aligned with the generated password/domain.
values['DATABASE_URL'] = (
    f"postgresql://{values.get('POSTGRES_USER', 'promptmaster')}:"
    f"{values['POSTGRES_PASSWORD']}@postgres:5432/{values.get('POSTGRES_DB', 'promptmaster')}"
)
values['ALLOWED_HOSTS'] = f'{domain},localhost,127.0.0.1'
values['CSRF_TRUSTED_ORIGINS'] = f'https://{domain}' if domain != 'localhost' else 'https://localhost,http://localhost'

ENV.write_text(serialise(template_lines, values), encoding='utf-8')
os.chmod(ENV, 0o600)

if generated:
    with CREDS.open('a', encoding='utf-8') as handle:
        for key, value in generated.items():
            handle.write(f'{key}={value}\n')
    os.chmod(CREDS, 0o600)

print(f'Environment prepared for {domain}.')
if values.get('RESTIC_REPOSITORY') == '/repository':
    print('Staging backup repository: local persistent Docker volume (/repository).')
if generated:
    print(f'Initial bootstrap credential written to {CREDS.name} (0600).')
