"""Regression tests for invalid runtime configurations, without Docker."""
import copy
import unittest

import yaml

from validate_runtime_config import ROOT, validate


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
