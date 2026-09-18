import csv
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import StreamingHttpResponse


@dataclass
class GridResult:
    page: object
    query: str
    sort: str
    direction: str
    page_size: int
    filters: dict
    has_state: bool
    queryset: object

    @property
    def navigation(self):
        """Return an elided, template-friendly numbered page navigation."""
        values = self.page.paginator.get_elided_page_range(
            self.page.number,
            on_each_side=2,
            on_ends=1,
        )
        return [
            {
                'label': str(value),
                'number': value if isinstance(value, int) else None,
                'current': value == self.page.number,
            }
            for value in values
        ]


class DataGrid:
    allowed_page_sizes = (25, 50, 100, 250)

    def __init__(
        self,
        request,
        queryset,
        *,
        search_fields=(),
        sort_fields=None,
        default_sort='-created_at',
        filters=None,
    ):
        self.request = request
        self.qs = queryset
        self.search_fields = tuple(search_fields)
        self.sort_fields = sort_fields or {}
        self.default_sort = default_sort
        self.filter_defs = filters or {}

    def _filtered_queryset(self):
        params = self.request.GET
        query = params.get('q', '').strip()[:200]
        queryset = self.qs
        if query and self.search_fields:
            expression = Q()
            for field in self.search_fields:
                expression |= Q(**{f'{field}__icontains': query})
            queryset = queryset.filter(expression)

        active_filters = {}
        for param, field in self.filter_defs.items():
            value = params.get(param, '').strip()[:100]
            if value:
                queryset = queryset.filter(**{field: value})
                active_filters[param] = value

        raw_sort = params.get('sort', '')
        direction = 'desc' if params.get('dir') == 'desc' else 'asc'
        if raw_sort in self.sort_fields:
            field = self.sort_fields[raw_sort]
            ordering = ('-' if direction == 'desc' else '') + field
        else:
            ordering = self.default_sort
            raw_sort = ''
            direction = 'desc' if self.default_sort.startswith('-') else 'asc'
        # UUID is a deterministic tie-breaker so page boundaries don't shuffle
        # while several rows share the same business sort key.
        tie_breaker = '-id' if ordering.startswith('-') else 'id'
        # Search/filter joins can duplicate base rows (for example an order
        # with several payments). DataGrids represent business objects, never
        # raw join rows, so deduplicate before pagination.
        queryset = queryset.order_by(ordering, tie_breaker).distinct()
        return queryset, query, active_filters, raw_sort, direction

    def build(self):
        queryset, query, active_filters, raw_sort, direction = self._filtered_queryset()
        try:
            page_size = int(self.request.GET.get('page_size', 50))
        except (TypeError, ValueError):
            page_size = 50
        if page_size not in self.allowed_page_sizes:
            page_size = 50

        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(self.request.GET.get('page', 1))
        has_state = bool(
            query
            or active_filters
            or raw_sort
            or page_size != 50
            or str(self.request.GET.get('page', '1')) not in ('', '1')
            or bool(self.request.GET.getlist('cols'))
        )
        return GridResult(
            page=page,
            query=query,
            sort=raw_sort,
            direction=direction,
            page_size=page_size,
            filters=active_filters,
            has_state=has_state,
            queryset=queryset,
        )


class Echo:
    def write(self, value):
        return value


def csv_response(queryset, columns, filename, max_rows=100000):
    """Stream a filtered/sorted DataGrid queryset as UTF-8 CSV.

    columns is an iterable of (attribute_path, label). Dot-separated paths are
    traversed safely. Export is deliberately bounded to avoid an accidental
    unbounded process on a web worker; larger analytical exports belong in a
    background job.
    """

    def value_for(row, path):
        value = row
        for part in path.split('.'):
            value = getattr(value, part, '')
            if callable(value):
                value = value()
            if value is None:
                return ''
        text = str(value)
        # Spreadsheet programs may execute values beginning with formula
        # prefixes. Exported customer-controlled data is neutralised without
        # changing what a human sees in the cell.
        if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
            text = "'" + text
        return text

    writer = csv.writer(Echo(), delimiter=';', quoting=csv.QUOTE_MINIMAL)

    def rows():
        yield '\ufeff' + writer.writerow([label for _, label in columns])
        for row in queryset[:max_rows].iterator(chunk_size=1000):
            yield writer.writerow([value_for(row, path) for path, _ in columns])

    response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
