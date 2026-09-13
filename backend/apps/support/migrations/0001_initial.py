import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
class Migration(migrations.Migration):
 initial=True; dependencies=[('companies','0001_initial'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
 operations=[migrations.CreateModel(name='SupportRequest',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),('category',models.CharField(choices=[('license','Lizenz'),('payment','Zahlung'),('user','Benutzer'),('device','Gerät'),('technical','Technisches Problem'),('privacy','Datenschutz'),('other','Sonstiges')],max_length=40)),('subject',models.CharField(max_length=180)),('message',models.TextField()),('status',models.CharField(choices=[('new','Neu'),('in_progress','In Bearbeitung'),('closed','Abgeschlossen')],default='new',max_length=30)),('company',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,to='companies.company')),('user',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL))])]
