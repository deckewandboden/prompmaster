import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_exportjob_run_token'),
        ('companies', '0003_privatecustomerprofile_phone'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Lead',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('lead_number', models.CharField(editable=False, max_length=24, unique=True)),
                ('kind', models.CharField(choices=[('company', 'Unternehmen'), ('private', 'Privatkunde')], default='company', max_length=20)),
                ('company_name', models.CharField(blank=True, max_length=200)),
                ('first_name', models.CharField(blank=True, max_length=120)),
                ('last_name', models.CharField(blank=True, max_length=120)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(blank=True, max_length=60)),
                ('source', models.CharField(choices=[('website', 'Website'), ('free', 'PromptMaster Free'), ('checkout', 'Checkout'), ('contact', 'Kontaktanfrage'), ('manual', 'Manuell'), ('other', 'Sonstiges')], default='manual', max_length=30)),
                ('status', models.CharField(choices=[('new', 'Neu'), ('contacted', 'Kontaktiert'), ('qualified', 'Qualifiziert'), ('won', 'Gewonnen'), ('lost', 'Verloren')], db_index=True, default='new', max_length=30)),
                ('priority', models.CharField(choices=[('low', 'Niedrig'), ('normal', 'Normal'), ('high', 'Hoch')], default='normal', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('next_action_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('converted_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assigned_leads', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='created_leads', to=settings.AUTH_USER_MODEL)),
                ('converted_company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='source_leads', to='companies.company')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['status', '-created_at'], name='core_lead_status_created_idx'),
                    models.Index(fields=['assigned_to', 'status'], name='core_lead_owner_status_idx'),
                    models.Index(fields=['deleted_at', '-created_at'], name='core_lead_deleted_created_idx'),
                ],
            },
        ),
    ]
