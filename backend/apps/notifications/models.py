from django.db import models
from apps.core.models import TimeStampedModel
class EmailTemplate(TimeStampedModel):
    code=models.CharField(max_length=80,unique=True); subject=models.CharField(max_length=200); body_text=models.TextField(); active=models.BooleanField(default=True)
class EmailMessage(TimeStampedModel):
    template=models.ForeignKey(EmailTemplate,null=True,blank=True,on_delete=models.SET_NULL); recipient=models.EmailField(); subject=models.CharField(max_length=200); status=models.CharField(max_length=30,default='queued'); queued_at=models.DateTimeField(auto_now_add=True); sent_at=models.DateTimeField(null=True,blank=True); provider_reference=models.CharField(max_length=160,blank=True); error=models.CharField(max_length=500,blank=True); retry_count=models.PositiveSmallIntegerField(default=0); context=models.JSONField(default=dict)
