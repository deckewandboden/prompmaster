from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from .middleware import CorrelationIdMiddleware


class CsvExportAuditMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.staff = User.objects.create_user(
            'csv-audit@example.test',
            'Csv-Audit-Password-42!',
            is_staff=True,
        )

    def middleware(self, content_type='text/csv; charset=utf-8'):
        def response_view(_request):
            response = HttpResponse('a;b\n1;2\n', content_type=content_type)
            response['Content-Disposition'] = 'attachment; filename="customers.csv"'
            return response
        return CorrelationIdMiddleware(response_view)

    def test_successful_staff_admin_csv_export_is_audited_without_query_values(self):
        request = self.factory.get(
            '/ns-admin/customers/?export=csv&status=active&q=Secret Customer&page=2'
        )
        request.user = self.staff
        response = self.middleware()(request)

        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(action='datagrid.csv_export')
        self.assertEqual(event.actor_id, self.staff.id)
        self.assertEqual(event.changes['path'], '/ns-admin/customers/')
        self.assertEqual(event.changes['filter_keys'], ['q', 'status'])
        self.assertIn('customers.csv', event.changes['filename'])
        self.assertNotIn('Secret Customer', str(event.changes))
        self.assertTrue(event.correlation_id)

    def test_non_csv_and_non_admin_responses_are_not_audited(self):
        request = self.factory.get('/ns-admin/customers/?export=csv')
        request.user = self.staff
        self.middleware('text/html; charset=utf-8')(request)
        self.assertFalse(AuditEvent.objects.filter(action='datagrid.csv_export').exists())

        request = self.factory.get('/portal/orders/?export=csv')
        request.user = self.staff
        self.middleware()(request)
        self.assertFalse(AuditEvent.objects.filter(action='datagrid.csv_export').exists())
