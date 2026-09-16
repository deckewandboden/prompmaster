from django import template

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
    current = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
    candidates = [item.strip() for item in names.split(',') if item.strip()]
    for candidate in candidates:
        if current == candidate or current.startswith(candidate + '_'):
            return 'active'
    return ''


@register.simple_tag
def clear_param_url(request, param):
    q = request.GET.copy()
    q.pop(param, None)
    q['page'] = '1'
    return '?' + q.urlencode() if q else request.path

@register.filter
def human_bytes(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'nicht verfügbar'
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
    for unit in units:
        if abs(number) < 1024 or unit == units[-1]:
            return f'{number:.1f} {unit}' if unit != 'B' else f'{int(number)} B'
        number /= 1024
    return f'{number:.1f} PB'


@register.simple_tag
def pm_has_perm(user, code):
    """Expose PromptMaster's custom role permission check to templates."""
    from apps.core.permissions import has_perm
    return has_perm(user, code)
