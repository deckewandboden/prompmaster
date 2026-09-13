from django.urls import path
from . import api

app_name = 'ops_api'
urlpatterns = [
    path('health', api.health, name='health'),
    path('system', api.system, name='system'),
    path('storage', api.storage, name='storage'),
    path('database', api.database, name='database'),
    path('services', api.services, name='services'),
    path('backups', api.backups, name='backups'),
    path('integrations', api.integrations, name='integrations'),
    path('maintenance-snapshot', api.maintenance_snapshot, name='maintenance_snapshot'),
]
