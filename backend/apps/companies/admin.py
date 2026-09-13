from django.contrib import admin
from .models import Company,Membership,Invitation,PrivateCustomerProfile
admin.site.register(Company)
admin.site.register(Membership)
admin.site.register(Invitation)
admin.site.register(PrivateCustomerProfile)
