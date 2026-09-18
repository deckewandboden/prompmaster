from django.test import RequestFactory, TestCase

from apps.companies.models import Company
from .datagrid import DataGrid


class DataGridContractTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        for idx in range(75):
            Company.objects.create(
                customer_number=f'GRID-{idx:03d}',
                name=f'Grid Kunde {idx:03d}',
                email=f'grid-{idx:03d}@example.test',
                country='DE',
                status='active' if idx % 2 == 0 else 'inactive',
            )

    def build(self, query=''):
        request = self.factory.get('/ns-admin/customers/' + query)
        return DataGrid(
            request,
            Company.objects.all(),
            search_fields=('customer_number', 'name', 'email'),
            sort_fields={'number': 'customer_number', 'name': 'name'},
            default_sort='name',
            filters={'status': 'status'},
        ).build()

    def test_default_page_size_is_50_with_deterministic_server_pagination(self):
        grid = self.build()
        self.assertEqual(grid.page_size, 50)
        self.assertEqual(len(grid.page.object_list), 50)
        self.assertEqual(grid.page.paginator.count, 75)
        self.assertEqual(grid.page.start_index(), 1)
        self.assertEqual(grid.page.end_index(), 50)

    def test_allowed_page_sizes_and_invalid_fallback(self):
        for size in (25, 50, 100, 250):
            with self.subTest(size=size):
                self.assertEqual(self.build(f'?page_size={size}').page_size, size)
        self.assertEqual(self.build('?page_size=9999').page_size, 50)

    def test_search_filter_sort_and_page_are_url_driven_and_whitelisted(self):
        grid = self.build('?q=Grid&status=active&sort=number&dir=desc&page=2&page_size=25')
        self.assertEqual(grid.query, 'Grid')
        self.assertEqual(grid.filters, {'status': 'active'})
        self.assertEqual(grid.sort, 'number')
        self.assertEqual(grid.direction, 'desc')
        self.assertEqual(grid.page.number, 2)
        self.assertEqual(grid.page_size, 25)
        self.assertTrue(grid.has_state)

        invalid_sort = self.build('?sort=not-a-real-field')
        self.assertEqual(invalid_sort.sort, '')
        self.assertEqual(invalid_sort.direction, 'asc')

    def test_search_with_no_results_is_distinct_from_empty_unfiltered_grid(self):
        no_result = self.build('?q=does-not-exist')
        self.assertEqual(no_result.page.paginator.count, 0)
        self.assertTrue(no_result.has_state)

        Company.objects.all().delete()
        empty = self.build()
        self.assertEqual(empty.page.paginator.count, 0)
        self.assertFalse(empty.has_state)
