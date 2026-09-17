import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import QueryDict
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Permission, Role, User, UserRole
from apps.companies.models import Company

from .export_views import export_download, export_status
from .exporting import capture_query_state
from .middleware import LargeExportMiddleware
from .models import ExportJob
from .tasks import cleanup_expired_exports, dispatch_pending_exports, generate_grid_export


TEST_KEY = Fernet.generate_key().decode()


class BackgroundExportTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.owner = User.objects.create_superuser('export-owner@example.test', 'Secure-Test-Password-42!')
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.settings_override = override_settings(
            APP_ENCRYPTION_KEY=TEST_KEY,
            EXPORT_ROOT=self.tempdir.name,
            EXPORT_SYNC_LIMIT=1,
            EXPORT_TTL_HOURS=24,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        Company.objects.create(customer_number='EXP-0001', name='Alpha', email='alpha@example.test')
        Company.objects.create(customer_number='EXP-0002', name='=2+2', email='formula@example.test')

    def _export_job(self, **overrides):
        values = {
            'requested_by': self.owner,
            'kind': 'customers',
            'filename': 'promptmaster-kunden.csv',
            'query_state_enc': capture_query_state(QueryDict('')),
            'expires_at': timezone.now() + timedelta(hours=1),
        }
        values.update(overrides)
        return ExportJob.objects.create(**values)

    def test_large_csv_request_is_queued_before_view_and_filter_state_is_encrypted(self):
        request = self.factory.get('/ns-admin/customers/?export=csv&q=Alpha')
        request.user = self.owner
        request.resolver_match = SimpleNamespace(url_name='customers')
        request.session = {}
        request._messages = FallbackStorage(request)
        view = Mock()
        middleware = LargeExportMiddleware(view)
        with patch('apps.core.tasks.generate_grid_export.delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = middleware(request)
        self.assertEqual(response.status_code, 302)
        view.assert_not_called()
        job = ExportJob.objects.get()
        self.assertNotIn('Alpha', job.query_state_enc)
        self.assertEqual(job.kind, 'customers')
        delay.assert_called_once_with(str(job.id))

    def test_worker_generates_csv_and_neutralises_formula_cells(self):
        job = self._export_job()
        result = generate_grid_export.run(str(job.id))
        self.assertEqual(result['status'], 'ready')
        job.refresh_from_db()
        self.assertEqual(job.status, 'ready')
        self.assertIsNone(job.run_token)
        self.assertEqual(job.row_count, 2)
        path = Path(self.tempdir.name) / job.file_name
        self.assertTrue(path.is_file())
        content = path.read_text(encoding='utf-8-sig')
        self.assertIn("'=2+2", content)

    def test_fresh_running_job_is_not_generated_twice(self):
        job = self._export_job(status='running', run_token=uuid.uuid4())
        result = generate_grid_export.run(str(job.id))
        self.assertEqual(result['status'], 'already_running')
        self.assertFalse((Path(self.tempdir.name) / f'{job.id}.csv').exists())

    def test_dispatcher_recovers_queued_jobs(self):
        job = self._export_job()
        with patch('apps.core.tasks.generate_grid_export.delay') as delay:
            dispatched = dispatch_pending_exports.run()
        self.assertEqual(dispatched, 1)
        delay.assert_called_once_with(str(job.id))

    def test_dispatcher_revokes_stale_worker_lease_before_retry(self):
        old_token = uuid.uuid4()
        job = self._export_job(status='running', run_token=old_token)
        ExportJob.objects.filter(pk=job.pk).update(
            updated_at=timezone.now() - timedelta(minutes=11)
        )
        with patch('apps.core.tasks.generate_grid_export.delay') as delay:
            dispatched = dispatch_pending_exports.run()
        self.assertEqual(dispatched, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')
        self.assertIsNone(job.run_token)
        delay.assert_called_once_with(str(job.id))

    def test_superseded_worker_cannot_publish_or_overwrite_export(self):
        job = self._export_job()
        company = Company.objects.order_by('customer_number').first()

        class LeaseStealingQueryset:
            def iterator(self, chunk_size):
                ExportJob.objects.filter(pk=job.pk).update(
                    run_token=uuid.uuid4(),
                    updated_at=timezone.now(),
                )
                yield company

        with patch('apps.core.tasks.export_queryset', return_value=LeaseStealingQueryset()):
            result = generate_grid_export.run(str(job.id))
        self.assertEqual(result['status'], 'superseded')
        self.assertFalse((Path(self.tempdir.name) / f'{job.id}.csv').exists())
        self.assertFalse(list(Path(self.tempdir.name).glob(f'{job.id}.*.tmp')))

    def test_expired_export_file_temp_files_and_job_are_removed(self):
        path = Path(self.tempdir.name) / 'expired.csv'
        temporary = Path(self.tempdir.name) / 'placeholder.tmp'
        path.write_text('old', encoding='utf-8')
        job = self._export_job(
            file_name=path.name,
            status='ready',
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        temporary = Path(self.tempdir.name) / f'{job.id}.deadbeef.tmp'
        temporary.write_text('partial', encoding='utf-8')
        self.assertEqual(cleanup_expired_exports.run(), 1)
        self.assertFalse(path.exists())
        self.assertFalse(temporary.exists())
        self.assertFalse(ExportJob.objects.filter(pk=job.pk).exists())

    def test_other_staff_user_cannot_read_or_download_someone_elses_export(self):
        permission = Permission.objects.create(code='customers.read', name='Kunden lesen')
        role = Role.objects.create(code='export-reader', name='Export Reader')
        role.permissions.add(permission)
        other = User.objects.create_user(
            'other-export@example.test',
            'Secure-Test-Password-42!',
            is_staff=True,
        )
        UserRole.objects.create(user=other, role=role)
        job = self._export_job(status='ready', file_name='owned.csv')
        (Path(self.tempdir.name) / job.file_name).write_text('secret', encoding='utf-8')
        request = self.factory.get(f'/ns-admin/exports/{job.pk}/')
        request.user = other
        with self.assertRaises(PermissionDenied):
            export_status(request, job.pk)
        with self.assertRaises(PermissionDenied):
            export_download(request, job.pk)

    def test_owner_download_is_private_and_no_store(self):
        job = self._export_job(status='ready', file_name='ready.csv', row_count=2)
        (Path(self.tempdir.name) / job.file_name).write_text('a;b\n1;2\n', encoding='utf-8')
        request = self.factory.get(f'/ns-admin/exports/{job.pk}/download/')
        request.user = self.owner
        response = export_download(request, job.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        response.close()
