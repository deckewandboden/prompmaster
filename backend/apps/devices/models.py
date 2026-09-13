from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel
class DeviceRegistration(TimeStampedModel):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='devices'); license=models.ForeignKey('licenses.License',on_delete=models.CASCADE,related_name='devices'); token_hash=models.CharField(max_length=64,unique=True); display_name=models.CharField(max_length=120); os_family=models.CharField(max_length=80,blank=True); browser_family=models.CharField(max_length=80,blank=True); last_seen_at=models.DateTimeField(null=True,blank=True); revoked_at=models.DateTimeField(null=True,blank=True)
    class Meta: indexes=[models.Index(fields=['user','revoked_at'])]
