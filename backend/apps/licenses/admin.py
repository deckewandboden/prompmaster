from django.contrib import admin
from .models import License,LicenseTerm,LicenseAssignment,LicenseReminder
admin.site.register(License)
admin.site.register(LicenseTerm)
admin.site.register(LicenseAssignment)
admin.site.register(LicenseReminder)
