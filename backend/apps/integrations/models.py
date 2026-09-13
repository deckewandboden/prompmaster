from django.db import models
from apps.core.models import TimeStampedModel
class IntegrationSecret(TimeStampedModel):
    code=models.CharField(max_length=80,unique=True); encrypted_value=models.TextField(); active=models.BooleanField(default=True)
class ServiceAccount(TimeStampedModel):
    name=models.CharField(max_length=120,unique=True); token_hash=models.CharField(max_length=64,unique=True); scopes=models.JSONField(default=list); active=models.BooleanField(default=True); expires_at=models.DateTimeField(null=True,blank=True); last_used_at=models.DateTimeField(null=True,blank=True)
