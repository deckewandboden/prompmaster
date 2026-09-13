import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
class Migration(migrations.Migration):
 initial=True; dependencies=[('licenses','0002_licenseterm'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
 operations=[migrations.CreateModel(name='DeviceRegistration',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),('token_hash',models.CharField(max_length=64,unique=True)),('display_name',models.CharField(max_length=120)),('os_family',models.CharField(blank=True,max_length=80)),('browser_family',models.CharField(blank=True,max_length=80)),('last_seen_at',models.DateTimeField(blank=True,null=True)),('revoked_at',models.DateTimeField(blank=True,null=True)),('license',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='devices',to='licenses.license')),('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='devices',to=settings.AUTH_USER_MODEL))],options={'indexes':[models.Index(fields=['user','revoked_at'],name='devices_d_user_idx')]})]
