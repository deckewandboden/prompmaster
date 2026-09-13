from .models import SystemSetting


def get_setting(key, default=None):
    row = SystemSetting.objects.filter(key=key).first()
    if not row:
        return default
    return row.value


def set_setting(key, value, description=''):
    row, _ = SystemSetting.objects.update_or_create(
        key=key,
        defaults={'value': value, 'description': description},
    )
    return row
