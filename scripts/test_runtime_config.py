"""Regression tests for invalid runtime configurations, without Docker."""
import copy
import unittest

import yaml

from validate_runtime_config import ROOT, validate, validate_legacy_volume_overlay
from validate_env import is_external_s3_repository, is_local_restic_repository, normalize_mail_provider


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

    def test_old_postgres_mount_is_rejected(self):
        self.base['services']['postgres']['volumes'] = ['postgres_data:/var/lib/postgresql/data']
        self.assertTrue(validate(self.base, self.production))

    def test_public_database_is_rejected(self):
        self.base['services']['postgres']['ports'] = ['5432:5432']
        self.assertTrue(validate(self.base, self.production))

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

    def test_production_deploy_tests_disable_only_ssl_redirect_for_test_container(self):
        deploy = (ROOT / 'scripts' / 'deploy.sh').read_text()
        expected = (
            'docker compose "${F[@]}" run --rm \\\n'
            '  -e SECURE_SSL_REDIRECT=0 \\\n'
            '  web python manage.py test'
        )
        self.assertIn(expected, deploy)
        test_block = deploy.split('log "Tests ausführen"', 1)[1].split('log "Pre-Migration-Backup erstellen"', 1)[0]
        self.assertNotIn('SESSION_COOKIE_SECURE=0', test_block)
        self.assertNotIn('CSRF_COOKIE_SECURE=0', test_block)

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
