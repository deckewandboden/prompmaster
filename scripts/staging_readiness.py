#!/usr/bin/env python3
"""Read-only, fail-closed staging preflight; intended only for a separate Docker host.

This program never invokes a mutating Git or Docker command. It does not deploy.
It may run only against a clean checkout and the LOCAL Docker daemon.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONFLICT_PROJECTS = {'promptmaster', 'promptfinisher'}
REQUIRED = {'web', 'worker', 'beat', 'postgres', 'redis', 'caddy', 'backup', 'mailpit'}


def call(args, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                              timeout=35, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def output(args, failures, label, cwd=None):
    result = call(args, cwd)
    if result is None or result.returncode:
        failures.append(label)
        return None
    return result.stdout


def listen_ports(text):
    result = set()
    for line in text.splitlines():
        cols = line.split()
        if len(cols) >= 4:
            match = re.search(r':(\d+)$', cols[3])
            if match:
                result.add(int(match.group(1)))
    return result


def docker_ports(text):
    return {int(x) for x in re.findall(r':(\d+)->\d+(?:/tcp|/udp)?', text)}


def compose_ports(services):
    found = set()
    for service in services.values():
        for port in service.get('ports') or []:
            if isinstance(port, dict):
                number = port.get('published')
            elif isinstance(port, str) and ':' in port:
                number = port.rsplit(':', 2)[-2]
            else:
                raise ValueError('Dynamic host port')
            if not str(number).isdecimal() or not (1 <= int(number) <= 65535):
                raise ValueError('Invalid host port')
            found.add(int(number))
    return found


def env_config(root, failures):
    file = root / '.env'
    if file.is_symlink() or not file.is_file():
        failures.append('Separate reguläre Staging-.env fehlt')
        return
    if file.stat().st_mode & 0o077:
        failures.append('.env darf ausschließlich durch Eigentümer lesbar sein (0600)')
    try:
        values = {}
        for line in file.read_text(encoding='utf-8').splitlines():
            raw = line.strip()
            if raw and not raw.startswith('#') and '=' in raw:
                key, value = raw.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except (OSError, UnicodeError):
        failures.append('.env nicht lesbar')
        return
    checks = [
        (values.get('ENVIRONMENT') == 'staging', 'ENVIRONMENT muss staging sein'),
        (values.get('CADDY_DOMAIN', '') != '', 'CADDY_DOMAIN fehlt'),
        (values.get('EMAIL_PROVIDER', '').lower() in {'smtp', 'mailpit'}, 'Nur Mailpit als Mailprovider'),
        (values.get('SMTP_HOST', '').lower() == 'mailpit', 'SMTP_HOST muss mailpit sein'),
        (values.get('SMTP_PORT') == '1025', 'SMTP_PORT muss 1025 sein'),
        (values.get('SMTP_USE_TLS') == '0', 'Keine echte SMTP-TLS-Verbindung'),
        (not values.get('SMTP_USER') and not values.get('SMTP_PASSWORD'), 'Keine SMTP-Zugangsdaten'),
        (not any(values.get(k) for k in ('GRAPH_CLIENT_ID', 'GRAPH_TENANT_ID', 'GRAPH_CLIENT_SECRET')), 'Keine Graph-Verbindung'),
        (not values.get('MOLLIE_API_KEY', '').startswith('live_'), 'Kein Mollie-Live-Key'),
        (not values.get('PM_EXTERNAL_CADDY_NETWORK') and not os.getenv('PM_EXTERNAL_CADDY_NETWORK'), 'Kein externes Caddy-Netz'),
        (values.get('RESTIC_REPOSITORY') == '/repository', 'Nur lokales isoliertes Restic-Repository'),
        (not values.get('AWS_ACCESS_KEY_ID') and not values.get('AWS_SECRET_ACCESS_KEY'), 'Keine S3-Produktionsschlüssel'),
    ]
    for ok, message in checks:
        if not ok:
            failures.append(message)
    if not (root / 'scripts/validate_env.py').is_file():
        failures.append('Projekt-Validator fehlt')
    else:
        output([sys.executable, 'scripts/validate_env.py', '--environment', 'staging'],
               failures, 'Projekteigene Staging-Environment-Prüfung FAIL', root)


def check(root, expected_sha):
    failures, passed = [], []
    # An isolated stack may coexist with an unrelated local Compose project,
    # but only with an explicitly unique project name and exact resource checks.
    isolated = os.environ.get('PM_STAGING_PROJECT', '')
    if isolated:
        if not re.fullmatch(r'pfpr73[a-z0-9]{8,20}', isolated):
            failures.append('PM_STAGING_PROJECT hat keinen zulaessigen eindeutigen QA-Namen')
            return failures, passed
        if os.environ.get('COMPOSE_PROJECT_NAME'):
            failures.append('COMPOSE_PROJECT_NAME darf isoliertes PM_STAGING_PROJECT nicht ueberschreiben')
            return failures, passed
    for path in ('compose.yaml', 'compose.staging.yaml', 'scripts/validate_env.py'):
        file = root / path
        if file.is_symlink() or not file.is_file():
            failures.append('Repository-Datei fehlt oder ist Symlink: ' + path)
    head = output(['git', 'rev-parse', 'HEAD'], failures, 'Git-HEAD unlesbar', root)
    if head is not None:
        if head.strip() != expected_sha:
            failures.append('Falsche Release-SHA')
        else:
            passed.append('RELEASE_SHA=PASS')
    top = output(['git', 'rev-parse', '--show-toplevel'], failures, 'Git-Root unlesbar', root)
    if top is not None and Path(top.strip()).resolve() != root:
        failures.append('Git-Checkout liegt nicht im übergebenen Root')
    dirty = output(['git', 'status', '--porcelain', '--untracked-files=no'],
                   failures, 'Git-Status unlesbar', root)
    if dirty is not None and dirty.strip():
        failures.append('Getrackter Quellcode lokal geändert')
    env_config(root, failures)
    if os.getenv('DOCKER_HOST') or os.getenv('DOCKER_CONTEXT'):
        failures.append('DOCKER_HOST/DOCKER_CONTEXT: kein Fremd-Daemon erlaubt')
        return failures, passed
    context = output(['docker', 'context', 'inspect'], failures, 'Docker-Kontext unlesbar')
    if context is None:
        return failures, passed
    try:
        record = json.loads(context)
        if len(record) != 1 or record[0]['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
            failures.append('Docker-Kontext ist nicht der lokale System-Daemon')
            return failures, passed
    except (KeyError, ValueError, TypeError):
        failures.append('Docker-Kontext ungültig')
        return failures, passed
    config = output(['docker', 'compose', '-f', 'compose.yaml', '-f',
                     'compose.staging.yaml', 'config', '--format', 'json'],
                    failures, 'Compose-Konfiguration unlesbar', root)
    if config is not None:
        try:
            obj = json.loads(config)
            if obj['name'] != (isolated or 'promptfinisher'):
                failures.append('Unerwarteter Compose-Projektname')
            services, volumes = obj['services'], obj['volumes']
            if not REQUIRED <= set(services):
                failures.append('Staging-Pflichtservices fehlen')
            if any(v.get('external') for v in volumes.values()):
                failures.append('Externes Docker-Volume in Staging verboten')
            if any(v.get('external') for v in obj.get('networks', {}).values()):
                failures.append('Externes Docker-Netz in Staging verboten')
            volume_names = {v.get('name') or f"{obj['name']}_{k}" for k, v in volumes.items()}
            requested_ports = compose_ports(services)
            if isolated:
                # Merely changing Compose's project name is insufficient when
                # the base file pins legacy *physical* volume names and images.
                if not volume_names or any(not n.startswith(isolated + '_') for n in volume_names):
                    failures.append('Isolierte Volumes haben fremde oder feste physische Namen')
                image_services = ('postgres', 'redis', 'prometheus', 'node-exporter',
                                  'cadvisor', 'postgres-exporter')
                if any(not (services.get(s, {}).get('image') or '').startswith(isolated + '-')
                       for s in image_services):
                    failures.append('Isolierte Image-Tags sind unvollstaendig')
                for service in services.values():
                    for port in service.get('ports') or []:
                        if not isinstance(port, dict) or port.get('host_ip') != '127.0.0.1':
                            failures.append('Isoliertes Staging veroeffentlicht Ports ausserhalb 127.0.0.1')
                            break
        except (ValueError, TypeError, KeyError):
            failures.append('Compose JSON oder veröffentlichte Ports ungültig')
        else:
            existing = output(['docker', 'volume', 'ls', '--format', '{{.Name}}'],
                              failures, 'Docker-Volumes nicht lesbar')
            if existing is not None and volume_names & set(existing.splitlines()):
                failures.append('Vorhandene physische Docker-Volumes würden wiederverwendet')
            projects = output(['docker', 'ps', '-a', '--format',
                               '{{.Label "com.docker.compose.project"}}'],
                              failures, 'Container-Inventar nicht lesbar')
            if projects is not None:
                project_set = set(projects.splitlines())
                if isolated:
                    if isolated in project_set:
                        failures.append('Der ausgewaehlte isolierte QA-Projektname existiert bereits')
                elif CONFLICT_PROJECTS & project_set:
                    failures.append('Bereits laufendes/angelegtes Produktiv-/Staging-Projekt erkannt')
            if requested_ports:
                listeners = output(['ss', '-H', '-ltn'], failures, 'Host-Ports unlesbar')
                published = output(['docker', 'ps', '--format', '{{.Ports}}'],
                                   failures, 'Docker-Portbelegung unlesbar')
                if listeners is not None and published is not None:
                    busy = requested_ports & (listen_ports(listeners) | docker_ports(published))
                    if busy:
                        failures.append('Host-Ports bereits belegt: ' + ','.join(map(str, sorted(busy))))
            passed.append('COMPOSE_ISOLATION_CHECKED')
    return failures, passed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--expected-sha', required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[0-9a-f]{40}', args.expected_sha):
        parser.error('--expected-sha must contain the exact lowercase 40-character Git SHA')
    if args.checkout.is_symlink() or not args.checkout.is_dir():
        print('STAGING_READINESS=BLOCKED; INVALID_CHECKOUT; NO_CHANGES_MADE=YES')
        return 2
    if any(not shutil.which(x) for x in ('git', 'docker', 'ss')):
        print('STAGING_READINESS=BLOCKED; MISSING_DEPENDENCIES; NO_CHANGES_MADE=YES')
        return 2
    failures, passed = check(args.checkout.resolve(), args.expected_sha)
    for entry in passed:
        print('PASS ' + entry)
    for entry in failures:
        print('BLOCKER ' + entry)
    print(('STAGING_READINESS=BLOCKED' if failures else 'STAGING_READINESS=PRECHECK_PASS') +
          '; NO_CHANGES_MADE=YES')
    print('Preflight alone does not approve production, languages, legal texts, payment or UI.')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
