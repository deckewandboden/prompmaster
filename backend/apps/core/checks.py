from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def promptmaster_configuration_checks(app_configs, **kwargs):
    issues = []
    if settings.ENVIRONMENT in {'staging', 'production'}:
        if settings.SECRET_KEY == 'unsafe-development-only' or len(settings.SECRET_KEY) < 40:
            issues.append(Error('DJANGO_SECRET_KEY ist nicht sicher konfiguriert.', id='promptmaster.E001'))
        if not settings.APP_ENCRYPTION_KEY:
            issues.append(Error('APP_ENCRYPTION_KEY fehlt.', id='promptmaster.E002'))
        if not settings.ALLOWED_HOSTS:
            issues.append(Error('ALLOWED_HOSTS ist leer.', id='promptmaster.E003'))
    if settings.ENVIRONMENT == 'production':
        if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
            issues.append(Error('Secure Cookies müssen in Produktion aktiv sein.', id='promptmaster.E004'))
        if settings.EMAIL_PROVIDER.lower() not in {'graph', 'microsoft_graph'}:
            issues.append(Warning('Produktiv ist Microsoft Graph als Mailprovider vorgesehen.', id='promptmaster.W001'))
    return issues
