from django.contrib import admin
from .models import Payment,MollieEvent,Refund
admin.site.register(Payment)
admin.site.register(MollieEvent)
admin.site.register(Refund)
