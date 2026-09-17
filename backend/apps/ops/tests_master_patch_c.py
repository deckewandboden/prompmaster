import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from .models import BackupRecord, RestoreTest
from .tasks import _backup_state, _restore_state


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
