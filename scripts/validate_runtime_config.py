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
    redis = services['redis']
    if postgres.get('image') != 'promptfinisher-postgres:18-alpine-hardened':
        errors.append('Hardened PostgreSQL 18 image required')
    if postgres.get('build') != {'context': '.', 'dockerfile': 'Dockerfile.postgres'}:
        errors.append('PostgreSQL must build from tracked Dockerfile.postgres')
    if postgres.get('volumes') != ['postgres_data:/var/lib/postgresql']:
        errors.append('PostgreSQL 18 must reuse postgres_data at /var/lib/postgresql')
    if 'PGDATA' in postgres.get('environment', {}):
        errors.append('PGDATA must use the PostgreSQL 18 image default')
    if postgres.get('ports') or postgres.get('networks') != ['data']:
        errors.append('PostgreSQL must have no published ports and use only data')
    if not compose['networks']['data'].get('internal') or not postgres.get('healthcheck'):
        errors.append('Internal data network and PostgreSQL healthcheck required')
    if redis.get('image') != 'promptfinisher-redis:7-alpine-hardened':
        errors.append('Hardened Redis 7 image required')
    if redis.get('build') != {'context': '.', 'dockerfile': 'Dockerfile.redis'}:
        errors.append('Redis must build from tracked Dockerfile.redis')
    if redis.get('ports') or redis.get('networks') != ['data']:
        errors.append('Redis must have no published ports and use only data')
    if services['backup'].get('build') != './backup':
        errors.append('Backup build context must be ./backup')
    if services.get('prometheus', {}).get('image') != 'prom/prometheus:v3.15.0':
        errors.append('Prometheus must remain pinned to the security-accepted v3.15.0 image')
    node_exporter = services.get('node-exporter', {})
    if node_exporter.get('image') != 'promptfinisher-node-exporter:1.12.1-hardened':
        errors.append('Hardened node_exporter 1.12.1 image required')
    if node_exporter.get('build') != {'context': '.', 'dockerfile': 'Dockerfile.node-exporter'}:
        errors.append('node_exporter must build from tracked Dockerfile.node-exporter')
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


def validate_legacy_volume_overlay():
    errors = []
    overlay = yaml.safe_load((ROOT / 'compose.legacy-volumes.yaml').read_text())
    volumes = overlay.get('volumes', {})
    expected = {
        'postgres_data': 'promptmaster_postgres_data',
        'redis_data': 'promptmaster_redis_data',
        'static_data': 'promptmaster_static_data',
        'caddy_data': 'promptmaster_caddy_data',
        'caddy_config': 'promptmaster_caddy_config',
        'prometheus_data': 'promptmaster_prometheus_data',
        'backup_status': 'promptmaster_backup_status',
        'backup_repository': 'promptmaster_backup_repository',
        'export_data': 'promptmaster_export_data',
    }
    for key, physical_name in expected.items():
        config = volumes.get(key, {})
        if config.get('external') is not True:
            errors.append(f'{key} must be external in legacy volume overlay')
        if config.get('name') != physical_name:
            errors.append(f'{key} must retain physical volume {physical_name}')
    return errors


def main():
    errors = validate(
        yaml.safe_load((ROOT / 'compose.yaml').read_text()),
        yaml.safe_load((ROOT / 'compose.production.yaml').read_text()),
    )
    errors.extend(validate_legacy_volume_overlay())
    for runtime_file in ('Dockerfile.postgres', 'Dockerfile.redis', 'Dockerfile.node-exporter'):
        runtime_path = ROOT / runtime_file
        if not runtime_path.is_file():
            errors.append(f'Missing hardened runtime build input: {runtime_file}')
            continue
        tracked = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', runtime_file], cwd=ROOT,
            capture_output=True,
        )
        if tracked.returncode:
            errors.append(f'Hardened runtime Dockerfile is not Git-tracked: {runtime_file}')

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
