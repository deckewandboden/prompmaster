from django.contrib import admin
from .models import Product,ProductPrice,Feature,ProductEntitlement,TaxRule
admin.site.register(Product)
admin.site.register(ProductPrice)
admin.site.register(Feature)
admin.site.register(ProductEntitlement)
admin.site.register(TaxRule)
