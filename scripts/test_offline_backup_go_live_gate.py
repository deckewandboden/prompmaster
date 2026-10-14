#!/usr/bin/env python3
"""Offsite acceptance positive/negative tests without production/Docker effects."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_backup_go_live_gate as gate

SHA = 'a' * 64
NOW = datetime(2026, 10, 14, 14, tzinfo=timezone.utc)


class OfflineBackupGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report = Path(self.tmp.name) / 'report.json'
        self.env_file = Path(self.tmp.name) / '.env'
        self.env_file.write_text('RESTIC_REPOSITORY=/repository\n')
        self.data = {
            'result': 'PASS', 'scope': gate.SCOPE, 'archive_sha256': SHA,
            'original_git_head': 'b' * 40, 'tables_count': 43,
            'migrations_count': 74, 'host': 'separate-recovery-host',
            'checked_at_utc': (NOW - timedelta(hours=2)).isoformat(),
            'limitations': 'No full application startup, payment, visual or legal acceptance',
        }
        self.write()

    def write(self):
        self.report.write_text(json.dumps(self.data))
        self.report.chmod(0o600)

    def check(self):
        return gate.verify(self.report, SHA, now=NOW, production_hostname='prod')

    def test_valid_recent_independent_restore_passes(self):
        self.assertEqual(self.check()['sha256'], SHA)

    def test_no_report_blocks(self):
        self.report.unlink()
        with self.assertRaises(ValueError): self.check()

    def test_world_readable_blocks(self):
        self.report.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '0600'): self.check()

    def test_symlink_blocks(self):
        target = Path(self.tmp.name) / 'real.json'
        self.report.rename(target)
        self.report.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Symlink'): self.check()

    def test_bad_checksum_blocks(self):
        self.data['archive_sha256'] = 'c' * 64
        self.write()
        with self.assertRaisesRegex(ValueError, 'Archiv-Prüfsummen'): self.check()

    def test_forged_result_blocks(self):
        self.data['result'] = 'FAIL'
        self.write()
        with self.assertRaisesRegex(ValueError, 'bestandener'): self.check()

    def test_insufficient_scope_blocks(self):
        self.data['scope'] = 'archive_only'
        self.write()
        with self.assertRaisesRegex(ValueError, 'bestandener'): self.check()

    def test_missing_limits_blocks(self):
        self.data['limitations'] = ''
        self.write()
        with self.assertRaisesRegex(ValueError, 'Abnahmegrenzen'): self.check()

    def test_future_report_blocks(self):
        self.data['checked_at_utc'] = (NOW + timedelta(days=1)).isoformat()
        self.write()
        with self.assertRaisesRegex(ValueError, 'Zukunft'): self.check()

    def test_stale_report_blocks(self):
        self.data['checked_at_utc'] = (NOW - timedelta(days=5)).isoformat()
        self.write()
        with self.assertRaisesRegex(ValueError, 'veraltet'): self.check()

    def test_production_host_blocks(self):
        self.data['host'] = 'prod'
        self.write()
        with self.assertRaisesRegex(ValueError, 'Produktionshost'): self.check()

    def test_zero_migrations_blocks(self):
        self.data['migrations_count'] = 0
        self.write()
        with self.assertRaisesRegex(ValueError, 'migrations_count'): self.check()

    def test_boolean_instead_of_integer_blocks(self):
        self.data['tables_count'] = True
        self.write()
        with self.assertRaisesRegex(ValueError, 'tables_count'): self.check()

    def test_nontimezone_date_blocks(self):
        self.data['checked_at_utc'] = '2026-10-14T12:00:00'
        self.write()
        with self.assertRaisesRegex(ValueError, 'UTC'): self.check()

    def test_s3_env_cannot_use_manual_offline_exception(self):
        self.env_file.write_text('RESTIC_REPOSITORY=s3:https://example.net/bucket\n')
        opts = {
            'PM_OFFSITE_STORAGE_CONFIRMED': 'YES',
            'PM_OFFSITE_DISK_ENCRYPTED': 'YES',
            'PM_OFFSITE_RISK_ACCEPTANCE': gate.EXPLICIT,
        }
        with patch.dict(os.environ, opts), patch.object(gate, 'verify', side_effect=AssertionError('should not run')):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(gate.main(['--report', str(self.report), '--archive-sha256', SHA, '--env-file', str(self.env_file)]), 2)

    def test_requires_all_explicit_manual_attestations(self):
        opts = {
            'PM_OFFSITE_STORAGE_CONFIRMED': 'YES',
            'PM_OFFSITE_DISK_ENCRYPTED': 'YES',
            'PM_OFFSITE_RISK_ACCEPTANCE': gate.EXPLICIT,
        }
        with patch.dict(os.environ, opts), patch.object(gate, 'verify', return_value={'sha256': SHA, 'host': 'offline'}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main(['--report', str(self.report), '--archive-sha256', SHA, '--env-file', str(self.env_file)]), 0)
            for key in opts:
                with self.subTest(key=key):
                    with patch.dict(os.environ, {key: ''}):
                        with contextlib.redirect_stderr(io.StringIO()):
                            self.assertEqual(gate.main(['--report', str(self.report), '--archive-sha256', SHA, '--env-file', str(self.env_file)]), 2)


if __name__ == '__main__':
    unittest.main()
