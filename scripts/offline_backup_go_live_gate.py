#!/usr/bin/env python3
"""Fail-closed one-time offsite backup exception for production release.

This is a documented manual risk acceptance, not continuous off-host backup.
An archive copy alone NEVER qualifies without a separate real restore report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

SCOPE = 'isolated_postgresql_restore_and_archive_manifest'
SHA256 = re.compile(r'^[0-9a-f]{64}$')
GITSHA = re.compile(r'^[0-9a-f]{40}$')
EXPLICIT = 'ACCEPT_MANUAL_OFFSITE_BACKUP_RISK_FOR_THIS_RELEASE'


def verify(report_path: Path, claimed_sha: str, *, now: datetime | None = None,
           max_age_hours: int = 72, production_hostname: str | None = None) -> dict:
    if not report_path.is_absolute():
        raise ValueError('Restore-Evidenzpfad muss absolut sein')
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError('Restore-Evidenz fehlt oder ist Symlink')
    meta = report_path.stat()
    if meta.st_size > 32768 or meta.st_size < 20:
        raise ValueError('Restore-Evidenzgröße ungültig')
    if stat.S_IMODE(meta.st_mode) != 0o600:
        raise ValueError('Restore-Evidenz muss Modus 0600 haben')
    if hasattr(os, 'geteuid') and meta.st_uid != os.geteuid():
        raise ValueError('Restore-Evidenz muss dem ausführenden Benutzer gehören')
    if not SHA256.fullmatch(claimed_sha):
        raise ValueError('Externe Windows-Archiv-Prüfsumme fehlt oder ist ungültig')
    payload = json.loads(report_path.read_text('utf-8'))
    if not isinstance(payload, dict) or payload.get('result') != 'PASS' or payload.get('scope') != SCOPE:
        raise ValueError('Kein bestandener isolierter Archiv-/Datenbankrestore')
    if payload.get('archive_sha256') != claimed_sha:
        raise ValueError('Unterschiedliche Archiv-Prüfsummen')
    if not GITSHA.fullmatch(str(payload.get('original_git_head', ''))):
        raise ValueError('Git-Baseline im gesicherten Archiv ungültig')
    for key in ('tables_count', 'migrations_count'):
        if type(payload.get(key)) is not int or payload[key] < 1:
            raise ValueError(f'Wiederherstellungsbefund {key} fehlt')
    if payload.get('limitations') != 'No full application startup, payment, visual or legal acceptance':
        raise ValueError('Abnahmegrenzen müssen vollständig dokumentiert sein')
    checked = datetime.fromisoformat(str(payload.get('checked_at_utc', '')))
    if checked.tzinfo is None or checked.utcoffset() != timedelta(0):
        raise ValueError('Restore-Zeitpunkt muss UTC mit Zeitzone sein')
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('Ungültige aktuelle Zeit')
    age = current.astimezone(timezone.utc) - checked.astimezone(timezone.utc)
    if age < timedelta(minutes=-5) or age > timedelta(hours=max_age_hours):
        raise ValueError('Restore-Evidenz ist veraltet oder liegt in der Zukunft')
    host = payload.get('host')
    if not isinstance(host, str) or not host.strip() or len(host) > 255:
        raise ValueError('Unabhängiger Recovery-Host nicht belegt')
    if host.lower().strip() == (production_hostname or socket.gethostname()).lower().strip():
        raise ValueError('Restore lief scheinbar auf dem Produktionshost')
    return {'sha256': claimed_sha, 'host': host, 'checked_at_utc': checked.isoformat()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--archive-sha256', required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        for env, expected in (
            ('PM_OFFSITE_STORAGE_CONFIRMED', 'YES'),
            ('PM_OFFSITE_DISK_ENCRYPTED', 'YES'),
            ('PM_OFFSITE_RISK_ACCEPTANCE', EXPLICIT),
        ):
            if os.environ.get(env) != expected:
                raise ValueError(f'{env}: explizite bewusste Freigabe fehlt')
        # Match the production validator's last assignment wins semantics.
        values = {}
        for line in args.env_file.read_text(encoding='utf-8').splitlines():
            raw = line.strip()
            if raw and not raw.startswith('#') and '=' in raw:
                key, value = raw.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        if values.get('RESTIC_REPOSITORY') != '/repository':
            raise ValueError('Offline-Ausnahme verlangt bestehendes lokales Restic-Repository')
        result = verify(args.report, args.archive_sha256)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f'OFFSITE_EXCEPTION=BLOCKED: {exc}', file=sys.stderr)
        return 2
    print('OFFSITE_EXCEPTION=PASS_WITH_DOCUMENTED_MANUAL_RISK')
    print('OFFSITE_ARCHIVE_SHA256=' + result['sha256'])
    print('INDEPENDENT_RESTORE_HOST=' + result['host'])
    print('NO_AUTOMATED_OFFHOST_REPLICATION=YES')
    print('FULL_APPLICATION_RESTORE_NOT_PROVEN=YES')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
