import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('licenses', '0002_licenseterm'),
        ('catalog', '0001_initial'),
        ('companies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='LicenseUpgradeRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending','Offen'),('approved','Genehmigt'),('rejected','Abgelehnt'),('cancelled','Storniert')], default='pending', max_length=20)),
                ('note', models.TextField(blank=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_license', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='upgrade_requests', to='licenses.license')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='license_upgrade_requests', to='companies.company')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='upgrade_requests', to='catalog.product')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='resolved_license_upgrade_requests', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='license_upgrade_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='licenseupgraderequest',
            constraint=models.UniqueConstraint(condition=Q(status='pending'), fields=('user','product'), name='uniq_pending_upgrade_user_product'),
        ),
        migrations.AddIndex(
            model_name='licenseupgraderequest',
            index=models.Index(fields=['company','status','-created_at'], name='licenses_up_company_4031bd_idx'),
        ),
    ]
