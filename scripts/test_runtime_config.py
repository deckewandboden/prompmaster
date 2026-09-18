"""Regression tests for invalid runtime configurations, without Docker."""
import copy
import unittest

import yaml

from validate_runtime_config import ROOT, validate
from validate_env import is_external_s3_repository


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self.base = yaml.safe_load((ROOT / 'compose.yaml').read_text())
        self.production = yaml.safe_load((ROOT / 'compose.production.yaml').read_text())

    def test_current_configuration(self):
        self.assertEqual(validate(self.base, self.production), [])

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

    def test_external_restic_repository_accepts_canonical_tls_forms(self):
        self.assertTrue(is_external_s3_repository('s3:https://s3.example.net/promptmaster'))
        self.assertTrue(is_external_s3_repository('s3:s3.eu-central-1.amazonaws.com/promptmaster'))
        self.assertTrue(is_external_s3_repository('s3:s3.amazonaws.com/promptmaster'))

    def test_external_restic_repository_rejects_noncanonical_or_insecure_forms(self):
        for value in (
            's3://s3.example.net/promptmaster',
            's3:http://s3.example.net/promptmaster',
            's3:https://s3.example.net',
            '/local/repository',
        ):
            with self.subTest(value=value):
                self.assertFalse(is_external_s3_repository(value))

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
