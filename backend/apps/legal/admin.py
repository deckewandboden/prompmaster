from django.contrib import admin
from .models import ConsumerContractDeclaration, LegalDocument, LegalAcceptance, RetentionPolicy, DeletionRequest
admin.site.register(LegalDocument)
admin.site.register(LegalAcceptance)
admin.site.register(RetentionPolicy)
admin.site.register(DeletionRequest)

admin.site.register(ConsumerContractDeclaration)
