"""Regression tests for invalid runtime configurations, without Docker."""
import base64
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from validate_runtime_config import ROOT, validate, validate_legacy_volume_overlay
from validate_env import is_external_s3_repository, is_local_restic_repository, main as validate_env_main, normalize_mail_provider


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self.base = yaml.safe_load((ROOT / 'compose.yaml').read_text())
        self.production = yaml.safe_load((ROOT / 'compose.production.yaml').read_text())

    def test_current_configuration(self):
        self.assertEqual(validate(self.base, self.production), [])

    def test_promptfinisher_infrastructure_rebrand_preserves_legacy_volumes(self):
        self.assertEqual(self.base['name'], 'promptfinisher')
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
            with self.subTest(volume=key):
                self.assertEqual(self.base['volumes'][key]['name'], physical_name)

    def test_promptfinisher_legacy_volume_overlay_is_external_and_complete(self):
        self.assertEqual(validate_legacy_volume_overlay(), [])
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        self.assertIn('if [[ -f "$LAST_SUCCESS_FILE" ]]', deploy)
        self.assertIn('F+=(-f compose.legacy-volumes.yaml)', deploy)

    def test_promptfinisher_backup_transition_keeps_legacy_restore_fallback(self):
        backup = (ROOT / 'backup' / 'backup.sh').read_text()
        self.assertIn('primary_backup_tag="promptfinisher-db"', backup)
        self.assertIn('legacy_backup_tag="promptmaster-db"', backup)
        self.assertIn('restic backup "$dump" --tag "$primary_backup_tag"', backup)
        self.assertIn('restic restore latest --tag "$legacy_backup_tag"', backup)
        self.assertIn('promptfinisher-${ts}.dump', backup)

    def test_redis_runtime_uses_hardened_patched_image(self):
        redis = self.base['services']['redis']
        self.assertEqual(redis['image'], 'promptfinisher-redis:7-alpine-hardened')
        self.assertEqual(
            redis['build'],
            {'context': '.', 'dockerfile': 'Dockerfile.redis'},
        )
        dockerfile = (ROOT / 'Dockerfile.redis').read_text()
        self.assertIn('FROM redis:7-alpine', dockerfile)
        self.assertIn('apk upgrade --no-cache', dockerfile)

    def test_postgres_runtime_uses_hardened_gosu_free_image(self):
        postgres = self.base['services']['postgres']
        self.assertEqual(postgres['image'], 'promptfinisher-postgres:18-alpine-hardened')
        self.assertEqual(
            postgres['build'],
            {'context': '.', 'dockerfile': 'Dockerfile.postgres'},
        )
        dockerfile = (ROOT / 'Dockerfile.postgres').read_text()
        self.assertIn('apk add --no-cache su-exec', dockerfile)
        self.assertIn('exec su-exec postgres', dockerfile)
        self.assertIn('rm -f /usr/local/bin/gosu', dockerfile)

    def test_old_postgres_mount_is_rejected(self):
        self.base['services']['postgres']['volumes'] = ['postgres_data:/var/lib/postgresql/data']
        self.assertTrue(validate(self.base, self.production))

    def test_public_database_is_rejected(self):
        self.base['services']['postgres']['ports'] = ['5432:5432']
        self.assertTrue(validate(self.base, self.production))

    def test_prometheus_runtime_is_security_accepted_version(self):
        self.assertEqual(
            self.base['services']['prometheus']['image'],
            'prom/prometheus:v3.15.0',
        )

    def test_public_monitoring_network_is_rejected(self):
        self.base['networks']['monitor']['internal'] = False
        self.assertTrue(validate(self.base, self.production))

    def test_cadvisor_public_port_is_rejected(self):
        self.base['services']['cadvisor']['ports'] = ['8080:8080']
        self.assertTrue(validate(self.base, self.production))

    def test_cadvisor_unpinned_image_is_rejected(self):
        self.base['services']['cadvisor']['image'] = 'ghcr.io/google/cadvisor:latest'
        self.assertTrue(validate(self.base, self.production))

    def test_cadvisor_mount_write_access_is_rejected(self):
        self.base['services']['cadvisor']['volumes'][0] = '/:/rootfs'
        self.assertTrue(validate(self.base, self.production))

    def test_mail_provider_normalization(self):
        self.assertEqual(normalize_mail_provider('smtp'), 'smtp1')
        self.assertEqual(normalize_mail_provider('mailpit'), 'smtp1')
        self.assertEqual(normalize_mail_provider('smtp1'), 'smtp1')
        self.assertEqual(normalize_mail_provider('microsoft_graph'), 'graph')
        self.assertEqual(normalize_mail_provider('graph'), 'graph')

    def test_local_restic_repository_accepts_only_builtin_volume(self):
        self.assertTrue(is_local_restic_repository('/repository'))
        self.assertFalse(is_local_restic_repository('/tmp/repository'))
        self.assertFalse(is_local_restic_repository('s3:https://s3.example.net/promptfinisher'))

    def test_external_restic_repository_accepts_canonical_tls_forms(self):
        self.assertTrue(is_external_s3_repository('s3:https://s3.example.net/promptfinisher'))
        self.assertTrue(is_external_s3_repository('s3:s3.eu-central-1.amazonaws.com/promptfinisher'))
        self.assertTrue(is_external_s3_repository('s3:s3.amazonaws.com/promptfinisher'))

    def test_external_restic_repository_rejects_noncanonical_or_insecure_forms(self):
        for value in (
            's3://s3.example.net/promptfinisher',
            's3:http://s3.example.net/promptfinisher',
            's3:https://s3.example.net',
            '/local/repository',
        ):
            with self.subTest(value=value):
                self.assertFalse(is_external_s3_repository(value))

    def _production_env_text(self, *, mollie='', repository='/repository', aws_key='', aws_secret='', region=''):
        fernet = base64.urlsafe_b64encode(b'x' * 32).decode('ascii')
        return '\n'.join([
            'ENVIRONMENT=production',
            'CADDY_DOMAIN=promptfinisher.test.net',
            'DJANGO_SECRET_KEY=' + ('s' * 48),
            'POSTGRES_PASSWORD=' + ('p' * 24),
            'APP_ENCRYPTION_KEY=' + fernet,
            'SESSION_COOKIE_SECURE=1',
            'CSRF_COOKIE_SECURE=1',
            'SECURE_SSL_REDIRECT=1',
            'ALLOWED_HOSTS=promptfinisher.test.net',
            'CSRF_TRUSTED_ORIGINS=https://promptfinisher.test.net',
            'NETSTYLE_VAT_ID=DE815319970',
            'EMAIL_PROVIDER=smtp1',
            'MOLLIE_API_KEY=' + mollie,
            'RESTIC_REPOSITORY=' + repository,
            'RESTIC_PASSWORD=' + ('r' * 24),
            'AWS_ACCESS_KEY_ID=' + aws_key,
            'AWS_SECRET_ACCESS_KEY=' + aws_secret,
            'AWS_DEFAULT_REGION=' + region,
            'INITIAL_ADMIN_PASSWORD=DISABLED',
        ]) + '\n'

    def _run_env_validator(self, text, *, require_go_live=False):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=True) as handle:
            handle.write(text)
            handle.flush()
            argv = ['validate_env.py', '--environment', 'production', '--env-file', handle.name]
            if require_go_live:
                argv.append('--require-go-live')
            with patch.object(sys, 'argv', argv):
                return validate_env_main()

    def test_standard_production_validation_keeps_go_live_dependencies_as_warnings(self):
        self.assertEqual(self._run_env_validator(self._production_env_text()), 0)

    def test_strict_go_live_validation_rejects_local_only_backup(self):
        self.assertEqual(self._run_env_validator(self._production_env_text(), require_go_live=True), 1)

    def test_strict_go_live_validation_accepts_external_tls_s3_without_forcing_env_mollie_secret(self):
        text = self._production_env_text(
            repository='s3:https://s3.test.net/promptfinisher',
            aws_key='AKIA_PROMPTFINISHER_TEST',
            aws_secret='external-backup-secret-value',
            region='eu-central-1',
        )
        self.assertEqual(self._run_env_validator(text, require_go_live=True), 0)

    def test_production_deploy_tests_disable_only_ssl_redirect_for_test_container(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        expected = (
            'run_with_heartbeat "Django-Testlauf" \\\n'
            '  docker compose "${F[@]}" run --rm \\\n'
            '    -e SECURE_SSL_REDIRECT=0 \\\n'
            '    web python manage.py test'
        )
        self.assertIn(expected, deploy)
        test_block = deploy.split('log "Tests ausführen"', 1)[1].split('log "Pre-Migration-Backup erstellen"', 1)[0]
        self.assertNotIn('SESSION_COOKIE_SECURE=0', test_block)
        self.assertNotIn('CSRF_COOKIE_SECURE=0', test_block)

    def test_production_deploy_reports_heartbeat_during_long_django_tests(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        self.assertIn('run_with_heartbeat(){', deploy)
        self.assertIn('PM_DEPLOY_HEARTBEAT_SECONDS:-30', deploy)
        self.assertIn('run_with_heartbeat "Django-Testlauf"', deploy)
        self.assertIn('web python manage.py test', deploy)
        self.assertIn('return "$status"', deploy)

    def test_infra_rebrand_cutover_is_fail_closed_and_preserves_volumes(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        self.assertIn('LEGACY_COMPOSE_PROJECT="promptmaster"', deploy)
        self.assertIn('CURRENT_COMPOSE_PROJECT="promptfinisher"', deploy)
        self.assertIn('Legacy-Cutover-Backup OK', deploy)
        self.assertIn('docker compose -p "$LEGACY_COMPOSE_PROJECT" "${F[@]}" down --remove-orphans', deploy)
        self.assertNotIn('down --remove-orphans -v', deploy)
        self.assertNotIn('down -v', deploy)
        self.assertIn('Legacy-PostgreSQL läuft weiterhin; Volume-Doppelzugriff verhindert.', deploy)

        cutover = deploy.index('migrate_legacy_compose_project_if_needed')
        data_start = deploy.index('log "Datenservices starten"')
        self.assertLess(cutover, data_start)

    def test_infra_rebrand_rollback_requires_new_stack_stop_without_volumes(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        self.assertIn('CUTOVER_PERFORMED=1', deploy)
        self.assertIn('Vor einem Code-Rollback MUSS zuerst der neue PROMPTFINISHER-Stack', deploy)
        self.assertIn('down --remove-orphans', deploy)
        self.assertIn('Niemals -v/--volumes verwenden.', deploy)

    def test_infra_rebrand_refuses_mixed_legacy_and_new_compose_projects(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        self.assertIn('Gemischter Compose-Zustand erkannt', deploy)
        self.assertIn('label=com.docker.compose.project=${LEGACY_COMPOSE_PROJECT}', deploy)
        self.assertIn('label=com.docker.compose.project=${CURRENT_COMPOSE_PROJECT}', deploy)

    def test_external_caddy_keeps_only_required_proxy_header_overrides(self):
        source = (ROOT / 'Caddyfile.external').read_text()
        self.assertNotIn('header_up X-Forwarded-Host', source)
        self.assertIn('header_up X-Forwarded-Proto https', source)
        self.assertIn('header_up X-Forwarded-For {client_ip}', source)

    def test_ops_runtime_reads_promptfinisher_backup_status_path(self):
        for rel in ('backend/apps/ops/tasks.py', 'backend/apps/ops/api.py'):
            with self.subTest(path=rel):
                source = (ROOT / rel).read_text()
                self.assertIn('/var/run/promptfinisher-backup', source)
                self.assertNotIn('/var/run/promptmaster-backup', source)

    def test_missing_beat_writable_path_is_rejected(self):
        self.base['services']['beat']['tmpfs'] = []
        self.assertTrue(validate(self.base, self.production))

    def test_default_beat_schedule_is_rejected(self):
        self.base['services']['beat']['command'] = ['celery', '-A', 'config', 'beat']
        self.assertTrue(validate(self.base, self.production))

    def test_writable_production_roots_are_rejected(self):
        for name in ('web', 'worker', 'beat'):
            with self.subTest(service=name):
                production = copy.deepcopy(self.production)
                production['services'][name]['read_only'] = False
                self.assertTrue(validate(self.base, production))


if __name__ == '__main__':
    unittest.main()
