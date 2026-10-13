#!/usr/bin/env python3
"""Positive and negative tests; all Docker/Git commands are mocked."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import staging_readiness as gate

SHA = 'a42e69f2dac0991bc01f93700174e48e05af9de3'


class StagingGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'scripts').mkdir()
        for name in ('compose.yaml', 'compose.staging.yaml', 'scripts/validate_env.py'):
            (self.root / name).touch()
        self.env = {
            'ENVIRONMENT': 'staging', 'CADDY_DOMAIN': 'staging.local',
            'EMAIL_PROVIDER': 'smtp', 'SMTP_HOST': 'mailpit', 'SMTP_PORT': '1025',
            'SMTP_USE_TLS': '0', 'SMTP_USER': '', 'SMTP_PASSWORD': '',
            'MOLLIE_API_KEY': '', 'PM_EXTERNAL_CADDY_NETWORK': '',
            'GRAPH_CLIENT_ID': '', 'GRAPH_CLIENT_SECRET': '', 'GRAPH_TENANT_ID': '',
            'RESTIC_REPOSITORY': '/repository',
            'AWS_ACCESS_KEY_ID': '', 'AWS_SECRET_ACCESS_KEY': '',
        }
        self.write_env()
        self.sha = SHA
        self.git_status = ''
        self.docker_context = 'unix:///var/run/docker.sock'
        self.volume_names = ''
        self.project_names = ''
        self.ss_ports = ''
        self.docker_ports = ''
        self.compose = {
            'name': 'promptfinisher',
            'services': {name: {} for name in gate.REQUIRED},
            'volumes': {'postgres': {'name': 'promptmaster_postgres_data'}},
            'networks': {'edge': {}},
        }
        self.compose['services']['caddy']['ports'] = [{'published': '80', 'target': 80}]
        self.compose['services']['mailpit']['ports'] = [{'published': '8025', 'target': 8025}]
        self.calls = []

    def write_env(self):
        p = self.root / '.env'
        p.write_text(''.join(k + '=' + v + '\n' for k, v in self.env.items()))
        p.chmod(0o600)

    def fake(self, args, cwd=None):
        self.calls.append(tuple(args))
        val = ''
        if args[:3] == ['git', 'rev-parse', 'HEAD']:
            val = self.sha
        elif args[:3] == ['git', 'rev-parse', '--show-toplevel']:
            val = str(self.root)
        elif args[:2] == ['git', 'status']:
            val = self.git_status
        elif args[:3] == ['docker', 'context', 'inspect']:
            val = json.dumps([{'Endpoints': {'docker': {'Host': self.docker_context}}}])
        elif args[:2] == ['docker', 'compose']:
            val = json.dumps(self.compose)
        elif args[:3] == ['docker', 'volume', 'ls']:
            val = self.volume_names
        elif args[:3] == ['docker', 'ps', '-a']:
            val = self.project_names
        elif args[:2] == ['docker', 'ps']:
            val = self.docker_ports
        elif args[:2] == ['ss', '-H']:
            val = self.ss_ports
        elif args[-2:] != ['--environment', 'staging']:
            raise AssertionError('Unexpected command ' + str(args))
        return CompletedProcess(args, 0, val + '\n', '')

    def check(self, expected):
        with (patch.object(gate, 'call', side_effect=self.fake),
              patch.object(gate.shutil, 'which', return_value='/mock'),
              patch.dict(os.environ, {'DOCKER_HOST': '', 'DOCKER_CONTEXT': '',
                                      'PM_EXTERNAL_CADDY_NETWORK': ''}),
              contextlib.redirect_stdout(io.StringIO()) as captured):
            status = gate.main([str(self.root), '--expected-sha', SHA])
        self.assertEqual(status, expected, captured.getvalue())
        self.assertIn('NO_CHANGES_MADE=YES', captured.getvalue())
        for cmd in self.calls:
            self.assertNotIn(cmd[1] if len(cmd) > 1 and cmd[1] in ('up', 'down', 'rm', 'build', 'checkout') else '', ('up', 'down', 'rm', 'build', 'checkout'))
        return captured.getvalue()

    def test_fresh_host_passes(self):
        self.assertIn('PRECHECK_PASS', self.check(0))

    def test_release_sha_mismatch_blocks(self):
        self.sha = 'b' * 40
        self.check(1)

    def test_dirty_checkout_blocks(self):
        self.git_status = ' M backend/config/settings.py'
        self.check(1)

    def test_existing_production_volume_blocks(self):
        self.volume_names = 'promptmaster_postgres_data'
        self.check(1)

    def test_existing_production_project_blocks(self):
        self.project_names = 'promptmaster'
        self.check(1)

    def test_existing_port_blocks(self):
        self.ss_ports = 'LISTEN 0 128 0.0.0.0:80 0.0.0.0:*'
        self.check(1)

    def test_existing_docker_nat_port_blocks(self):
        self.docker_ports = '127.0.0.1:8025->8025/tcp'
        self.check(1)

    def test_external_network_blocks(self):
        self.compose['networks']['edge']['external'] = True
        self.check(1)

    def test_external_volume_blocks(self):
        self.compose['volumes']['postgres']['external'] = True
        self.check(1)

    def test_remote_context_blocks(self):
        self.docker_context = 'ssh://remote'
        self.check(1)

    def test_live_mollie_blocks(self):
        self.env['MOLLIE_API_KEY'] = 'live_unsafe'
        self.write_env()
        self.check(1)

    def test_real_smtp_blocks(self):
        self.env['SMTP_HOST'] = 'smtp.example.org'
        self.write_env()
        self.check(1)

    def test_real_backup_blocks(self):
        self.env['RESTIC_REPOSITORY'] = 's3:https://example.com/production'
        self.write_env()
        self.check(1)

    def test_world_readable_env_blocks(self):
        (self.root / '.env').chmod(0o644)
        self.check(1)

    def test_unexpected_external_caddy_blocks(self):
        self.env['PM_EXTERNAL_CADDY_NETWORK'] = 'public_proxy'
        self.write_env()
        self.check(1)

    def test_ports_support_ipv4_ipv6_and_compose(self):
        self.assertEqual(gate.listen_ports('LISTEN 0 128 [::]:443 [::]:*'), {443})
        self.assertEqual(gate.docker_ports('[::]:443->443/tcp'), {443})
        self.assertEqual(gate.compose_ports({'a': {'ports': ['127.0.0.1:18080:80', '443:443']}}), {18080, 443})


if __name__ == '__main__':
    unittest.main(verbosity=2)
