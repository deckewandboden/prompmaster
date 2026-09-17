import json
from types import SimpleNamespace

from django.http import QueryDict

from apps.audit.models import AuditEvent
from apps.companies.models import Company, PrivateCustomerProfile
from apps.licenses.models import License
from apps.orders.models import Order

from .crypto import decrypt, encrypt
from .datagrid import DataGrid


EXPORTS = {
    'customers': {
        'permission': 'customers.read',
        'filename': 'promptmaster-kunden.csv',
        'columns': [('customer_number', 'Kundennummer'), ('name', 'Kunde'), ('email', 'E-Mail'), ('status', 'Status')],
    },
    'private_customers': {
        'permission': 'customers.read',
        'filename': 'promptmaster-privatkunden.csv',
        'columns': [('customer_number', 'Kundennummer'), ('user.full_name', 'Name'), ('user.email', 'E-Mail'), ('country', 'Land')],
    },
    'licenses': {
        'permission': 'licenses.read',
        'filename': 'promptmaster-lizenzen.csv',
        'columns': [('license_number', 'Lizenz-ID'), ('company.name', 'Unternehmen'), ('owner_user.email', 'Privatkunde'), ('product.name', 'Produkt'), ('valid_until', 'Ablauf'), ('status', 'Status')],
    },
    'orders': {
        'permission': 'orders.read',
        'filename': 'promptmaster-bestellungen.csv',
        'columns': [('order_number', 'Bestellung'), ('company.name', 'Unternehmen'), ('private_user.email', 'Privatkunde'), ('gross_total', 'Betrag'), ('status', 'Status'), ('created_at', 'Datum')],
    },
    'audit': {
        'permission': 'audit.read',
        'filename': 'promptmaster-audit.csv',
        'columns': [('created_at', 'Zeit'), ('actor.email', 'Benutzer'), ('actor_role', 'Rolle'), ('action', 'Aktion'), ('object_type', 'Objekttyp'), ('object_id', 'Objekt-ID')],
    },
}

URL_NAME_TO_KIND = {
    'customers': 'customers',
    'private_customers': 'private_customers',
    'licenses': 'licenses',
    'orders': 'orders',
    'audit': 'audit',
}


def capture_query_state(params):
    state = {}
    for key in params.keys():
        if key in {'export', 'page', 'page_size', 'cols'}:
            continue
        if not key.replace('_', '').isalnum():
            continue
        value = params.get(key, '')
        state[key[:60]] = str(value)[:200]
    return encrypt(json.dumps(state, ensure_ascii=False, separators=(',', ':')))


def decode_query_state(value):
    state = json.loads(decrypt(value))
    if not isinstance(state, dict):
        raise ValueError('invalid export query state')
    return {str(key)[:60]: str(item)[:200] for key, item in state.items()}


def _request_for_state(state):
    params = QueryDict('', mutable=True)
    for key, value in state.items():
        params[key] = value
    return SimpleNamespace(GET=params)


def export_queryset(kind, state):
    request = _request_for_state(state)
    if kind == 'customers':
        return DataGrid(
            request,
            Company.objects.all(),
            search_fields=('customer_number', 'name', 'email'),
            sort_fields={'number': 'customer_number', 'name': 'name', 'created': 'created_at', 'status': 'status'},
            default_sort='name',
            filters={'status': 'status', 'country': 'country'},
        ).build().queryset
    if kind == 'private_customers':
        return DataGrid(
            request,
            PrivateCustomerProfile.objects.select_related('user'),
            search_fields=('customer_number', 'user__email', 'user__first_name', 'user__last_name', 'city'),
            sort_fields={'number': 'customer_number', 'name': 'user__last_name', 'email': 'user__email', 'created': 'created_at'},
            default_sort='user__last_name',
            filters={'country': 'country'},
        ).build().queryset
    if kind == 'licenses':
        return DataGrid(
            request,
            License.objects.select_related('company', 'owner_user', 'product'),
            search_fields=('license_number', 'company__name', 'owner_user__email', 'product__name'),
            sort_fields={'number': 'license_number', 'expiry': 'valid_until', 'status': 'status', 'company': 'company__name'},
            default_sort='valid_until',
            filters={'status': 'status', 'product': 'product__code'},
        ).build().queryset
    if kind == 'orders':
        return DataGrid(
            request,
            Order.objects.select_related('company', 'private_user'),
            search_fields=('order_number', 'company__name', 'private_user__email'),
            sort_fields={'number': 'order_number', 'date': 'created_at', 'amount': 'gross_total', 'status': 'status'},
            default_sort='-created_at',
            filters={'status': 'status'},
        ).build().queryset
    if kind == 'audit':
        return DataGrid(
            request,
            AuditEvent.objects.select_related('actor'),
            search_fields=('action', 'object_type', 'object_id', 'actor__email'),
            sort_fields={'time': 'created_at', 'action': 'action'},
            default_sort='-created_at',
            filters={'action': 'action'},
        ).build().queryset
    raise ValueError(f'Unsupported export kind: {kind}')


def csv_value(row, path):
    value = row
    for part in path.split('.'):
        value = getattr(value, part, '')
        if callable(value):
            value = value()
        if value is None:
            return ''
    text = str(value)
    if text.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        text = "'" + text
    return text
