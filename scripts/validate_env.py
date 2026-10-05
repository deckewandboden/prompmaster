#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

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


def normalize_mail_provider(value: str) -> str:
    provider = (value or '').strip().lower()
    if provider in {'smtp', 'mailpit'}:
        return 'smtp1'
    if provider == 'microsoft_graph':
        return 'graph'
    return provider


def check_fernet(value: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(value.encode('ascii'))
        return len(raw) == 32 and len(value) == 44
    except Exception:
        return False


def is_local_restic_repository(value: str) -> bool:
    """Accept the built-in persistent Docker volume used by the backup service."""
    return (value or '').strip() == '/repository'


def is_external_s3_repository(value: str) -> bool:
    """Accept only canonical TLS-protected restic S3 repository forms."""
    repo = (value or '').strip()
    if repo.startswith('s3:https://'):
        parsed = urlsplit(repo[3:])
        return bool(
            parsed.scheme == 'https'
            and parsed.hostname
            and parsed.path
            and parsed.path != '/'
        )
    return bool(
        re.fullmatch(
            r's3:s3(?:\.[a-z0-9-]+)?\.amazonaws\.com/.+',
            repo,
            flags=re.I,
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--environment', choices=('staging', 'production'), required=True)
    ap.add_argument('--env-file', default=str(ENV_FILE))
    ap.add_argument(
        '--require-go-live',
        action='store_true',
        help='Production only: treat missing live payments and off-host backup as hard go-live failures.',
    )
    args = ap.parse_args()
    path = Path(args.env_file)
    values = parse_env(path)
    errors: list[str] = []
    warnings: list[str] = []

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

    provider_raw = values.get('EMAIL_PROVIDER', '').strip().lower()
    provider = normalize_mail_provider(provider_raw)
    if expected == 'production':
        vat_id = values.get('NETSTYLE_VAT_ID', '').replace(' ', '').upper()
        if not re.fullmatch(r'DE\d{9}', vat_id):
            fail(
                errors,
                'NETSTYLE_VAT_ID muss für das produktive Impressum intern bestätigt '
                'und im Format DE123456789 gesetzt sein.',
            )
        if provider not in {'smtp1', 'graph'}:
            fail(
                errors,
                'Production EMAIL_PROVIDER muss smtp/smtp1 oder graph/microsoft_graph sein. '
                'Weitere Laufzeit-Fallbacks werden verschlüsselt über die Admin-Einstellungen verwaltet.',
            )
        if provider in {'graph', 'smtp1'}:
            # Provider-specific transport, identity and secrets may intentionally
            # live in the encrypted runtime settings rather than .env. This static
            # validator checks only the allowed baseline provider selector.
            # deploy.sh performs the authoritative database-backed
            # validate_mail_runtime gate after the data services are available.
            pass
        mollie = values.get('MOLLIE_API_KEY', '').strip()
        if mollie and not mollie.startswith('live_'):
            fail(errors, 'Wenn MOLLIE_API_KEY gesetzt ist, muss er in Produktion ein Mollie-Live-Key (live_…) sein.')
        elif not mollie:
            message = 'MOLLIE_API_KEY ist nicht gesetzt; Mollie-Zahlungen sind bis zur Provider-Konfiguration nicht verfügbar.'
            if args.require_go_live:
                fail(errors, message)
            else:
                warnings.append(message)

        repo = values.get('RESTIC_REPOSITORY', '').strip()
        if is_placeholder(repo):
            fail(
                errors,
                'RESTIC_REPOSITORY muss gesetzt sein: lokal /repository oder externes TLS-S3 '
                '(s3:https://host/bucket bzw. s3:s3.<region>.amazonaws.com/bucket).',
            )
        elif is_local_restic_repository(repo):
            message = (
                'RESTIC_REPOSITORY=/repository verwendet nur das persistente lokale Docker-Volume; '
                'ein externes Off-Host-Backup bleibt ein separates Go-Live-/Disaster-Recovery-Gate.'
            )
            if args.require_go_live:
                fail(errors, message)
            else:
                warnings.append(message)
        elif is_external_s3_repository(repo):
            for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
                if is_placeholder(values.get(key, '')):
                    fail(errors, f'{key} muss für ein externes S3-Production-Backup gesetzt sein.')
            if args.require_go_live:
                region = values.get('AWS_DEFAULT_REGION', '').strip() or values.get('S3_REGION', '').strip()
                if is_placeholder(region):
                    fail(errors, 'AWS_DEFAULT_REGION oder S3_REGION muss für das externe Production-Backup gesetzt sein.')
        else:
            fail(
                errors,
                'RESTIC_REPOSITORY muss /repository oder ein kanonisches TLS-S3-Ziel sein '
                '(s3:https://host/bucket oder s3:s3.<region>.amazonaws.com/bucket).',
            )
        if is_placeholder(values.get('RESTIC_PASSWORD', '')) or len(values.get('RESTIC_PASSWORD', '')) < 20:
            fail(errors, 'RESTIC_PASSWORD muss sicher gesetzt sein.')
        if values.get('INITIAL_ADMIN_PASSWORD', '') not in {'', 'DISABLED'}:
            fail(errors, 'INITIAL_ADMIN_PASSWORD darf nach Bootstrap in Produktion nicht aktiv konfiguriert bleiben.')
    else:
        # Staging must never accidentally use live payments.
        if values.get('MOLLIE_API_KEY', '').startswith('live_'):
            fail(errors, 'Staging darf keinen Mollie-Live-Key verwenden.')
        if provider_raw not in {'smtp', 'mailpit'}:
            fail(errors, 'Staging EMAIL_PROVIDER muss smtp/mailpit sein, damit keine echten Kundenmails versendet werden.')
        admin_password = values.get('INITIAL_ADMIN_PASSWORD', '')
        if is_placeholder(admin_password) or len(admin_password) < 12:
            fail(errors, 'INITIAL_ADMIN_PASSWORD muss im Staging mindestens 12 Zeichen lang und kein Platzhalter sein.')

    if args.require_go_live and expected != 'production':
        fail(errors, '--require-go-live darf nur zusammen mit --environment production verwendet werden.')

    if errors:
        for item in errors:
            print(f'[FEHLER] {item}', file=sys.stderr)
        return 1
    for item in warnings:
        print(f'[WARNUNG] {item}')
    print(f'ENV VALIDATION OK ({expected})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
