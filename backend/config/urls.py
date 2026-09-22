from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core
from apps.proaccess import views as product_views

urlpatterns = [
    path('', core.home, name='home'),
    path('catalog.json', core.public_catalog, name='public_catalog'),
    path('free/', product_views.free_content, name='free_product'),
    path('free-old/', product_views.free_old_content, name='free_product_old'),
    path('pro-old/', product_views.legacy_content, name='pro_product_old'),
    path('legal/<str:doc_type>/', core.legal_public, name='legal_public'),
    path('health/live/', core.health_live, name='health_live'),
    path('health/ready/', core.health_ready, name='health_ready'),
    path('metrics/internal/', core.metrics_internal, name='metrics_internal'),
    path('auth/', include('apps.accounts.urls')),
    path('pro/', include('apps.proaccess.urls')),
    path('portal/', include('apps.companies.portal_urls')),
    path('ns-admin/prompt-studio/', include('apps.prompts.studio_urls')),
    path('ns-admin/content/', include('apps.contenthub.admin_urls')),
    path('ns-admin/', include('apps.core.admin_urls')),
    path('api/webhooks/mollie/', include('apps.payments.webhook_urls')),
    path('api/v1/ops/', include('apps.ops.api_urls')),
    path('api/v1/prompts/', include('apps.prompts.api_urls')),
    path('api/v1/mcp/', include('apps.mcp_internal.urls')),
    path('api/v1/content/', include('apps.contenthub.api_urls')),
]

# The stock Django admin bypasses parts of PromptMaster's service-layer
# business rules. It is a staging/development fallback only; production uses
# the permission-aware netstyle admin frontend exclusively.
if getattr(settings, 'ENVIRONMENT', 'development') != 'production':
    urlpatterns.append(path('django-admin/', admin.site.urls))
