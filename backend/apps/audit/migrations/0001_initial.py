import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
class Migration(migrations.Migration):
 initial=True; dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
 operations=[migrations.CreateModel(name='AuditEvent',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),('actor_role',models.CharField(blank=True,max_length=120)),('action',models.CharField(max_length=120)),('object_type',models.CharField(max_length=120)),('object_id',models.CharField(max_length=64)),('ip',models.GenericIPAddressField(blank=True,null=True)),('user_agent',models.CharField(blank=True,max_length=300)),('correlation_id',models.CharField(blank=True,max_length=80)),('changes',models.JSONField(default=dict)),('actor',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL))],options={'ordering':['-created_at'],'indexes':[models.Index(fields=['action','created_at'],name='audit_a_action_idx'),models.Index(fields=['object_type','object_id'],name='audit_a_object_idx')]})]
