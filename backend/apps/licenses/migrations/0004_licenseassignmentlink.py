import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('licenses', '0003_licenseupgraderequest'),
        ('companies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='LicenseAssignmentLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='license_assignment_links', to='companies.company')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_license_assignment_links', to=settings.AUTH_USER_MODEL)),
                ('license', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignment_links', to='licenses.license')),
                ('target_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='license_assignment_links', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name='licenseassignmentlink',
            index=models.Index(fields=['company','target_user','expires_at'], name='licenses_li_company_ec3db4_idx'),
        ),
        migrations.AddConstraint(
            model_name='licenseassignmentlink',
            constraint=models.UniqueConstraint(condition=Q(revoked_at__isnull=True, used_at__isnull=True), fields=('license','target_user'), name='uniq_open_assignment_link_license_user'),
        ),
    ]
