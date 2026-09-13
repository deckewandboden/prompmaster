from django.contrib import admin
from .models import IntegrationSecret,ServiceAccount
admin.site.register(IntegrationSecret)
admin.site.register(ServiceAccount)
