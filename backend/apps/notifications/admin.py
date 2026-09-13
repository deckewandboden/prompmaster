from django.contrib import admin
from .models import EmailTemplate,EmailMessage
admin.site.register(EmailTemplate)
admin.site.register(EmailMessage)
