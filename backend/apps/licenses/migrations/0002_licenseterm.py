import uuid
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q

class Migration(migrations.Migration):
 dependencies=[('licenses','0001_initial'),('orders','0001_initial')]
 operations=[migrations.CreateModel(name='LicenseTerm',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True,db_index=True)),('updated_at',models.DateTimeField(auto_now=True)),('valid_from',models.DateTimeField()),('valid_until',models.DateTimeField()),('paid_gross_amount',models.DecimalField(decimal_places=2,max_digits=10)),('status',models.CharField(choices=[('active','Aktiv'),('refunded','Refundiert')],default='active',max_length=20)),('refunded_at',models.DateTimeField(blank=True,null=True)),('license',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='terms',to='licenses.license')),('order_item',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='license_terms',to='orders.orderitem'))],options={'ordering':['valid_from'],'constraints':[models.CheckConstraint(condition=Q(valid_until__gt=models.F('valid_from')),name='term_end_after_start'),models.CheckConstraint(condition=Q(paid_gross_amount__gte=0),name='term_paid_nonnegative')]})]
