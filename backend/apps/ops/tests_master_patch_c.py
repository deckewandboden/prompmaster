import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from .models import BackupRecord, RestoreTest
from .tasks import DEFAULT_THRESHOLDS, _backup_state, _restore_state, _thresholds


class OpsStatusFailSafeTests(TestCase):
    def test_backup_valid_json_with_invalid_size_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'last-backup.json'
            path.write_text(
                json.dumps({
                    'timestamp': '20260917T180000Z',
                    'status': 'ok',
                    'size_bytes': {'not': 'an integer'},
                }),
                encoding='utf-8',
            )
            with patch('apps.ops.tasks.BACKUP_STATUS', path):
                self.assertIsNone(_backup_state())
        self.assertEqual(BackupRecord.objects.count(), 0)

    def test_backup_oversized_bigint_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'last-backup.json'
            path.write_text(
                json.dumps({
                    'timestamp': '20260917T180000Z',
                    'status': 'ok',
                    'size_bytes': 2**80,
                }),
                encoding='utf-8',
            )
            with patch('apps.ops.tasks.BACKUP_STATUS', path):
                self.assertIsNone(_backup_state())
        self.assertEqual(BackupRecord.objects.count(), 0)

    def test_backup_non_object_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'last-backup.json'
            path.write_text('["valid", "json", "wrong-shape"]', encoding='utf-8')
            with patch('apps.ops.tasks.BACKUP_STATUS', path):
                self.assertIsNone(_backup_state())
        self.assertEqual(BackupRecord.objects.count(), 0)

    def test_restore_non_object_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'last-restore.json'
            path.write_text('42', encoding='utf-8')
            with patch('apps.ops.tasks.RESTORE_STATUS', path):
                self.assertIsNone(_restore_state())
        self.assertEqual(RestoreTest.objects.count(), 0)

    def test_malformed_threshold_settings_fall_back_per_key(self):
        raw = {
            'disk_warning': {'bad': 'shape'},
            'disk_critical': '95',
            'ram_warning': True,
            'queue_warning': -1,
            'backup_warning_hours': 12,
        }
        with patch('apps.ops.tasks.get_setting', return_value=raw):
            thresholds = _thresholds()

        self.assertEqual(set(thresholds), set(DEFAULT_THRESHOLDS))
        self.assertEqual(thresholds['disk_warning'], DEFAULT_THRESHOLDS['disk_warning'])
        self.assertEqual(thresholds['disk_critical'], 95)
        self.assertEqual(thresholds['ram_warning'], DEFAULT_THRESHOLDS['ram_warning'])
        self.assertEqual(thresholds['queue_warning'], DEFAULT_THRESHOLDS['queue_warning'])
        self.assertEqual(thresholds['backup_warning_hours'], 12)

    def test_non_mapping_threshold_settings_use_complete_defaults(self):
        with patch('apps.ops.tasks.get_setting', return_value=['bad', 'shape']):
            self.assertEqual(_thresholds(), DEFAULT_THRESHOLDS)
