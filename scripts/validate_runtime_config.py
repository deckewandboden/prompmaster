#!/usr/bin/env python3
"""Guard full-checkout build inputs and the PostgreSQL/Beat runtime contracts."""
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(compose, production):
    errors = []
    services = compose['services']
    postgres = services['postgres']
    if not postgres.get('image', '').startswith('postgres:18'):
        errors.append('PostgreSQL 18 image required')
    if postgres.get('volumes') != ['postgres_data:/var/lib/postgresql']:
        errors.append('PostgreSQL 18 must reuse postgres_data at /var/lib/postgresql')
    if 'PGDATA' in postgres.get('environment', {}):
        errors.append('PGDATA must use the PostgreSQL 18 image default')
    if postgres.get('ports') or postgres.get('networks') != ['data']:
        errors.append('PostgreSQL must have no published ports and use only data')
    if not compose['networks']['data'].get('internal') or not postgres.get('healthcheck'):
        errors.append('Internal data network and PostgreSQL healthcheck required')
    if services['backup'].get('build') != './backup':
        errors.append('Backup build context must be ./backup')
    monitor = compose.get('networks', {}).get('monitor', {})
    cadvisor = services.get('cadvisor', {})
    if monitor.get('internal') is not True:
        errors.append('Monitoring network must remain internal')
    if cadvisor.get('image') != 'ghcr.io/google/cadvisor:v0.60.5':
        errors.append('cAdvisor image must remain explicitly pinned')
    if cadvisor.get('privileged') is not True:
        errors.append('cAdvisor host trust boundary changed; staging validation and release decision required')
    if cadvisor.get('networks') != ['monitor'] or cadvisor.get('ports'):
        errors.append('cAdvisor must use only internal monitor network and publish no host ports')
    expected_cadvisor_mounts = {
        '/:/rootfs:ro',
        '/var/run:/var/run:ro',
        '/sys:/sys:ro',
        '/var/lib/docker/:/var/lib/docker:ro',
        '/dev/disk/:/dev/disk:ro',
    }
    if set(cadvisor.get('volumes', [])) != expected_cadvisor_mounts:
        errors.append('cAdvisor host mounts must match the documented read-only trust boundary')
    beat = services['beat']
    if '--schedule=/tmp/celerybeat/celerybeat-schedule' not in beat.get('command', []):
        errors.append('Beat must use its explicit schedule directory')
    if '/tmp/celerybeat:mode=1777,size=16m' not in beat.get('tmpfs', []):
        errors.append('Beat requires its bounded writable tmpfs')
    for name in ('web', 'worker', 'beat'):
        override = production['services'][name]
        if override.get('read_only') is not True:
            errors.append(f'{name} production root must remain read-only')
    if 'command' in production['services']['beat']:
        errors.append('Production must retain the explicit Beat schedule command')
    return errors


def main():
    errors = validate(
        yaml.safe_load((ROOT / 'compose.yaml').read_text()),
        yaml.safe_load((ROOT / 'compose.production.yaml').read_text()),
    )
    for name in ('Dockerfile', 'backup.sh', '.dockerignore'):
        path = f'backup/{name}'
        if not (ROOT / path).is_file():
            errors.append(f'Missing backup build input: {path}')
        tracked = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', path], cwd=ROOT,
            capture_output=True,
        )
        if tracked.returncode:
            errors.append(f'Backup build input is not Git-tracked: {path}')
    if errors:
        raise SystemExit('\n'.join(f'RUNTIME CONFIG FAIL: {error}' for error in errors))
    print('RUNTIME CONFIG OK: PostgreSQL 18, tracked backup context, read-only Beat, internal cAdvisor trust boundary')


if __name__ == '__main__':
    main()
