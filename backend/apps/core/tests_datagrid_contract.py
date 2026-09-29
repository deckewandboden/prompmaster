from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.companies.models import Company
from apps.licenses.models import License, LicenseAssignment
from .admin_views import _license_admin_queryset
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



class LicenseAdminGridContractTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.company = Company.objects.create(
            customer_number='GRID-LIC-001',
            name='Grid Lizenzkunde',
            email='license-grid@example.test',
            country='DE',
        )
        self.product_a = Product.objects.create(code='GRID-PRO-A', name='A Produkt')
        self.product_z = Product.objects.create(code='GRID-PRO-Z', name='Z Produkt')
        self.anna = User.objects.create_user(
            email='anna@example.test',
            first_name='Anna',
            last_name='Becker',
        )
        self.berta = User.objects.create_user(
            email='berta@example.test',
            first_name='Berta',
            last_name='Zimmer',
        )
        self.historical = User.objects.create_user(
            email='historisch@example.test',
            first_name='Historisch',
            last_name='Alt',
        )
        self.license_anna = License.objects.create(
            license_number='GRID-LIC-A',
            company=self.company,
            product=self.product_z,
            status='active',
        )
        self.license_berta = License.objects.create(
            license_number='GRID-LIC-B',
            company=self.company,
            product=self.product_a,
            status='active',
        )
        self.license_free = License.objects.create(
            license_number='GRID-LIC-FREE',
            company=self.company,
            product=self.product_a,
            status='free',
        )
        LicenseAssignment.objects.create(license=self.license_anna, user=self.anna)
        LicenseAssignment.objects.create(license=self.license_berta, user=self.berta)
        LicenseAssignment.objects.create(
            license=self.license_free,
            user=self.historical,
            ended_at=timezone.now() - timedelta(days=1),
        )

    def grid(self, query=''):
        request = self.factory.get('/ns-admin/licenses/' + query)
        return DataGrid(
            request,
            _license_admin_queryset(License.objects.filter(company=self.company)),
            search_fields=(
                'license_number',
                'product__name',
                'license_holder_name',
                'license_holder_email',
            ),
            sort_fields={
                'number': 'license_number',
                'name': 'license_holder_name',
                'product': 'product__name',
                'expiry': 'valid_until',
                'status': 'status',
            },
            default_sort='license_number',
        ).build()

    def test_current_holder_annotation_ignores_historical_assignments(self):
        rows = {
            row.license_number: row
            for row in _license_admin_queryset(
                License.objects.filter(company=self.company)
            )
        }
        self.assertEqual(rows['GRID-LIC-A'].license_holder_name, 'Anna Becker')
        self.assertEqual(rows['GRID-LIC-A'].license_holder_email, 'anna@example.test')
        self.assertEqual(rows['GRID-LIC-B'].license_holder_name, 'Berta Zimmer')
        self.assertEqual(rows['GRID-LIC-FREE'].license_holder_name, 'Frei')
        self.assertEqual(rows['GRID-LIC-FREE'].license_holder_email, '')

    def test_license_name_and_product_are_server_side_sortable_and_searchable(self):
        by_name = self.grid('?sort=name&dir=asc')
        self.assertEqual(
            [row.license_number for row in by_name.page.object_list],
            ['GRID-LIC-A', 'GRID-LIC-B', 'GRID-LIC-FREE'],
        )
        self.assertEqual(by_name.sort, 'name')

        by_product = self.grid('?sort=product&dir=asc')
        self.assertEqual(by_product.sort, 'product')
        self.assertEqual(
            [row.product.name for row in by_product.page.object_list],
            ['A Produkt', 'A Produkt', 'Z Produkt'],
        )

        searched = self.grid('?q=Anna')
        self.assertEqual(
            [row.license_number for row in searched.page.object_list],
            ['GRID-LIC-A'],
        )

    def test_admin_templates_expose_holder_name_and_separate_detail_email(self):
        from django.conf import settings
        from pathlib import Path

        templates = Path(settings.BASE_DIR) / 'templates' / 'ns_admin'
        company_grid = (templates / 'customer_grid.html').read_text(encoding='utf-8')
        private_grid = (templates / 'private_customer_grid.html').read_text(encoding='utf-8')
        detail = (templates / 'license_detail.html').read_text(encoding='utf-8')

        for source in (company_grid, private_grid):
            self.assertIn("sort_url request 'name'", source)
            self.assertIn("sort_url request 'product'", source)
            self.assertIn('data-label="Name"', source)
            self.assertIn('license_holder_name', source)

        self.assertIn('Zugewiesen an', detail)
        self.assertIn('<span>E-Mail</span>', detail)
        self.assertIn('class="wrap-anywhere"', detail)


    def test_all_admin_datagrid_business_columns_have_sort_contracts(self):
        from django.conf import settings
        from pathlib import Path

        templates = Path(settings.BASE_DIR) / 'templates' / 'ns_admin'
        required = {
            'audit.html': ('time', 'user', 'role', 'action', 'object', 'change'),
            'email_log.html': ('date', 'recipient', 'template', 'subject', 'status'),
            'features.html': ('code', 'name'),
            'legal_deletions.html': ('date', 'email', 'status', 'note'),
            'legal_documents.html': ('type', 'version', 'valid_from', 'active'),
            'legal_retention.html': ('data_class', 'days', 'active'),
            'mollie_events.html': ('date', 'payment', 'status', 'processed', 'retries', 'error'),
            'payments.html': ('date', 'payment', 'order', 'amount', 'status'),
            'support.html': ('date', 'category', 'subject', 'customer', 'status'),
        }
        for template_name, sort_keys in required.items():
            source = (templates / template_name).read_text(encoding='utf-8')
            for sort_key in sort_keys:
                with self.subTest(template=template_name, sort_key=sort_key):
                    self.assertIn(f"sort_url request '{sort_key}'", source)

        ops = (templates / 'ops_grid.html').read_text(encoding='utf-8')
        for sort_key in (
            'status', 'date', 'size', 'reference',
            'finished', 'backup',
            'code', 'severity', 'message', 'active',
        ):
            with self.subTest(template='ops_grid.html', sort_key=sort_key):
                self.assertIn(f"sort_url request '{sort_key}'", ops)

        static_js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
        static_css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'datagrid.css').read_text(encoding='utf-8')
        self.assertIn("data-sort-mode="client"", static_js)
        self.assertIn("content:"⇅"", static_css)
        self.assertIn("data-sort-state="asc"", static_css)
        self.assertIn("data-sort-state="desc"", static_css)
