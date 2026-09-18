from pathlib import Path
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development').strip().lower()
DEBUG = ENVIRONMENT == 'development'
TESTING = 'test' in sys.argv
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'unsafe-development-only')

ALLOWED_HOSTS = [x.strip() for x in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if x.strip()]
CADDY_DOMAIN = os.getenv('CADDY_DOMAIN', '').strip()
APP_VERSION = os.getenv('APP_VERSION', 'development')
GIT_SHA = os.getenv('GIT_SHA', '')
DEPLOYED_AT = os.getenv('DEPLOYED_AT', '')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core',
    'apps.accounts',
    'apps.companies',
    'apps.catalog',
    'apps.orders',
    'apps.payments',
    'apps.licenses',
    'apps.devices',
    'apps.notifications',
    'apps.support',
    'apps.legal',
    'apps.audit',
    'apps.integrations',
    'apps.ops',
    'apps.proaccess',
    'apps.prompts',
    'apps.mcp_internal',
    'apps.contenthub',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.TwoFactorEnforcementMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.CorrelationIdMiddleware',
    'apps.core.middleware.LargeExportMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.navigation',
            ]
        },
    }
]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'promptmaster'),
        'USER': os.getenv('POSTGRES_USER', 'promptmaster'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'HOST': os.getenv('POSTGRES_HOST', 'postgres'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
    }
}

AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage' if TESTING else 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/auth/login/'

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', '1') == '1'
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', '28800'))  # 8 hours
SESSION_IDLE_TIMEOUT = int(os.getenv('SESSION_IDLE_TIMEOUT', '1800'))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', '1') == '1'
CSRF_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', '1') == '1' and ENVIRONMENT == 'production'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000 if ENVIRONMENT == 'production' else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENVIRONMENT == 'production'
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

EXPORT_ROOT = os.getenv('EXPORT_ROOT', '/app/exports')
EXPORT_SYNC_LIMIT = int(os.getenv('EXPORT_SYNC_LIMIT', '5000'))
EXPORT_TTL_HOURS = int(os.getenv('EXPORT_TTL_HOURS', '24'))

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL', 'redis://redis:6379/0'),
        'OPTIONS': {'socket_connect_timeout': 3, 'socket_timeout': 3},
    }
}
CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULE = {
    'license-state-sync': {'task': 'apps.notifications.tasks.sync_license_states', 'schedule': 300.0},
    'license-reminders': {'task': 'apps.notifications.tasks.schedule_license_reminders', 'schedule': 3600.0},
    'email-queue-recovery': {'task': 'apps.notifications.tasks.dispatch_queued_emails', 'schedule': 300.0},
    'ops-alerts': {'task': 'apps.ops.tasks.refresh_alerts', 'schedule': 300.0},
    'worker-heartbeat': {'task': 'apps.ops.tasks.worker_heartbeat', 'schedule': 60.0},
    'beat-heartbeat': {'task': 'apps.ops.tasks.beat_heartbeat', 'schedule': 60.0},
    'retention': {'task': 'apps.legal.tasks.apply_retention', 'schedule': 86400.0},
    'prompt-quality': {'task': 'apps.prompts.tasks.refresh_prompt_quality', 'schedule': 21600.0},
    'export-dispatch': {'task': 'apps.core.tasks.dispatch_pending_exports', 'schedule': 300.0},
    'export-cleanup': {'task': 'apps.core.tasks.cleanup_expired_exports', 'schedule': 3600.0},
}

EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'smtp')
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('SMTP_HOST', 'mailpit')
EMAIL_PORT = int(os.getenv('SMTP_PORT', '1025'))
EMAIL_USE_TLS = os.getenv('SMTP_USE_TLS', '0') == '1'
DEFAULT_FROM_EMAIL = os.getenv('EMAIL_FROM', 'promptmaster@netstyle.de')
EMAIL_TIMEOUT = 20

APP_ENCRYPTION_KEY = os.getenv('APP_ENCRYPTION_KEY', '')
MOLLIE_API_KEY = os.getenv('MOLLIE_API_KEY', '')
MOLLIE_PROFILE_ID = os.getenv('MOLLIE_PROFILE_ID', '')
PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
FREE_GOLDEN_MASTER_PATH = os.getenv('FREE_GOLDEN_MASTER_PATH', str(BASE_DIR / 'private_assets' / 'promptmaster_free_reference.html'))
FREE_GOLDEN_MASTER_SHA256 = os.getenv('FREE_GOLDEN_MASTER_SHA256', 'aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8')
PRO_GOLDEN_MASTER_PATH = os.getenv('PRO_GOLDEN_MASTER_PATH', str(BASE_DIR / 'private_assets' / 'promptmaster_pro.html'))
PRO_GOLDEN_MASTER_SHA256 = os.getenv('PRO_GOLDEN_MASTER_SHA256', 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf')
PRO_RUNTIME_PATH = os.getenv('PRO_RUNTIME_PATH', str(BASE_DIR / 'private_assets' / 'promptmaster_pro_runtime.html'))
PRO_RUNTIME_SHA256 = os.getenv('PRO_RUNTIME_SHA256', '29da4bb38b121ef585d07711e4e30966f1ae37089ffc01be048de7a2e821ebba')

GRAPH_TENANT_ID = os.getenv('GRAPH_TENANT_ID', '')
GRAPH_CLIENT_ID = os.getenv('GRAPH_CLIENT_ID', '')
GRAPH_CLIENT_SECRET = os.getenv('GRAPH_CLIENT_SECRET', '')
GRAPH_SENDER = os.getenv('GRAPH_SENDER', '')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'apps.core.middleware.JsonLogFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
}
