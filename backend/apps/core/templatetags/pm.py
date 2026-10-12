import re

from django import template
from django.utils.translation import gettext as _, gettext

register = template.Library()


@register.filter
def attr(obj, name):
    """Resolve a safe dot-separated attribute path for DataGrid cells."""
    value = obj
    for part in str(name).split('.'):
        if value is None:
            return ''
        value = getattr(value, part, '')
        if callable(value):
            try:
                value = value()
            except TypeError:
                return value
    return value


@register.simple_tag
def url_replace(request, **kwargs):
    q = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == '':
            q.pop(key, None)
        else:
            q[key] = value
    return '?' + q.urlencode() if q else request.path


@register.simple_tag
def sort_url(request, key, current_sort, current_dir):
    q = request.GET.copy()
    q['sort'] = key
    q['dir'] = 'desc' if current_sort == key and current_dir == 'asc' else 'asc'
    q['page'] = '1'
    return '?' + q.urlencode()


@register.simple_tag
def clear_sort_url(request):
    q = request.GET.copy()
    q.pop('sort', None)
    q.pop('dir', None)
    q['page'] = '1'
    return '?' + q.urlencode() if q else request.path


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key, '')
    except Exception:
        return ''


@register.simple_tag
def col_visible(request, key):
    selected = request.GET.getlist('cols')
    return not selected or key in selected


@register.simple_tag
def filter_display(request, param, choices):
    current = request.GET.get(param, '')
    for value, label in choices:
        if str(value) == str(current):
            return str(label)
    return current


@register.simple_tag
def nav_class(request, names):
    match = getattr(request, 'resolver_match', None)
    current = getattr(match, 'url_name', '') or ''
    namespace = getattr(match, 'namespace', '') or ''
    app_name = getattr(match, 'app_name', '') or ''
    candidates = [item.strip() for item in names.split(',') if item.strip()]

    def normalized(value):
        return str(value).strip().lower().replace('-', '_')

    current_n = normalized(current)
    namespace_n = normalized(namespace)
    app_name_n = normalized(app_name)
    for candidate in candidates:
        candidate_n = normalized(candidate)
        if (
            current_n == candidate_n
            or current_n.startswith(candidate_n + '_')
            or namespace_n == candidate_n
            or namespace_n.startswith(candidate_n + '_')
            or app_name_n == candidate_n
            or app_name_n.startswith(candidate_n + '_')
        ):
            return 'active'
    return ''


@register.simple_tag
def clear_param_url(request, param):
    q = request.GET.copy()
    q.pop(param, None)
    q['page'] = '1'
    return '?' + q.urlencode() if q else request.path


# The scheduler persists canonical German text for auditing and API clients.
# Translate only known scheduler-owned alert messages at presentation time;
# custom alerts, changed payloads and unknown codes remain untouched.
_OPS_ALERT_RULES = (
    (re.compile("disk\\.(?:critical|warning)"), re.compile("Disk (?P<value>\\d+(?:\\.\\d+)?)% belegt"), "Disk {value}% belegt"),
    (re.compile("ram\\.(?:critical|warning)"), re.compile("RAM (?P<value>\\d+(?:\\.\\d+)?)% belegt"), "RAM {value}% belegt"),
    (re.compile("cpu\\.warning"), re.compile("CPU 10-Minuten-Mittel (?P<value>\\d+(?:\\.\\d+)?)%"), "CPU 10-Minuten-Mittel {value}%"),
    (re.compile("backup\\.unavailable"), re.compile("Kein auswertbarer Backupstatus verfügbar"), "Kein auswertbarer Backupstatus verfügbar"),
    (re.compile("backup\\.failed"), re.compile("Letztes Backup meldet Status (?P<value>[^\\r\\n<>]{1,60})"), "Letztes Backup meldet Status {value}"),
    (re.compile("backup\\.(?:critical|warning)"), re.compile("Backup ist (?P<value>\\d+(?:\\.\\d+)?) Stunden alt"), "Backup ist {value} Stunden alt"),
    (re.compile("restore\\.unavailable"), re.compile("Restore-Statusdatei ist nicht auswertbar"), "Restore-Statusdatei ist nicht auswertbar"),
    (re.compile("restore\\.missing"), re.compile("Noch kein Restore-Test protokolliert"), "Noch kein Restore-Test protokolliert"),
    (re.compile("restore\\.failed"), re.compile("Letzter Restore-Test war nicht erfolgreich"), "Letzter Restore-Test war nicht erfolgreich"),
    (re.compile("restore\\.old"), re.compile("Letzter Restore-Test ist (?P<value>\\d+) Tage alt"), "Letzter Restore-Test ist {value} Tage alt"),
    (re.compile("service\\.[A-Za-z0-9_.-]+\\.down"), re.compile("Monitoring-Ziel (?P<value>[A-Za-z0-9_.-]+) ist nicht erreichbar"), "Monitoring-Ziel {value} ist nicht erreichbar"),
    (re.compile("service\\.[A-Za-z0-9_.-]+\\.unknown"), re.compile("Monitoring-Ziel (?P<value>[A-Za-z0-9_.-]+) liefert keinen Status"), "Monitoring-Ziel {value} liefert keinen Status"),
    (re.compile("service\\.caddy\\.down"), re.compile("Caddy Healthcheck ist nicht erreichbar"), "Caddy Healthcheck ist nicht erreichbar"),
    (re.compile("worker\\.ping"), re.compile("Kein Celery Worker beantwortet den aktiven Ping"), "Kein Celery Worker beantwortet den aktiven Ping"),
    (re.compile("beat\\.heartbeat"), re.compile("Celery Beat-Heartbeat älter als (?P<value>\\d+) Minuten"), "Celery Beat-Heartbeat älter als {value} Minuten"),
    (re.compile("queue\\.unavailable"), re.compile("Celery Queue-Tiefe kann nicht gelesen werden"), "Celery Queue-Tiefe kann nicht gelesen werden"),
    (re.compile("queue\\.backlog"), re.compile("Celery Queue enthält (?P<value>\\d+) wartende Jobs"), "Celery Queue enthält {value} wartende Jobs"),
    (re.compile("task\\.failures"), re.compile("(?P<value>\\d+) fehlgeschlagene Hintergrundjobs in 24 Stunden"), "{value} fehlgeschlagene Hintergrundjobs in 24 Stunden"),
    (re.compile("mail\\.failures"), re.compile("(?P<value>\\d+) E-Mail-Fehler in 24 Stunden"), "{value} E-Mail-Fehler in 24 Stunden"),
    (re.compile("mollie\\.failures"), re.compile("(?P<value>\\d+) Mollie-Verarbeitungsfehler in 24 Stunden"), "{value} Mollie-Verarbeitungsfehler in 24 Stunden"),
)


@register.filter
def ops_alert_display(alert):
    """Localize known operational alerts without changing their persisted meaning."""
    code = str(getattr(alert, 'code', '') or '')
    message = str(getattr(alert, 'message', '') or '')
    for code_pattern, message_pattern, msgid in _OPS_ALERT_RULES:
        if not code_pattern.fullmatch(code):
            continue
        match = message_pattern.fullmatch(message)
        if match is None:
            continue
        params = match.groupdict()
        if code.startswith('service.') and params.get('value'):
            # Never display a different monitoring target than the stored alert code.
            target = code[len('service.'):].rsplit('.', 1)[0]
            if params['value'] != target:
                continue
        if code == 'backup.failed' and params.get('value'):
            params['value'] = gettext(params['value'])
        try:
            return gettext(msgid).format_map(params)
        except (ValueError, KeyError, IndexError):
            return message
    return message

@register.filter
def human_bytes(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _('nicht verfügbar')
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    for unit in units:
        if abs(number) < 1024 or unit == units[-1]:
            return f'{number:.1f} {unit}' if unit != 'B' else f'{int(number)} B'
        number /= 1024
    return f'{number:.1f} PB'


@register.simple_tag
def user_has_perm(user, code):
    from apps.core.permissions import has_perm

    return bool(user and getattr(user, 'is_authenticated', False) and has_perm(user, code))
