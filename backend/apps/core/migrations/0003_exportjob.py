from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_search_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExportJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('customers', 'Kunden'), ('private_customers', 'Privatkunden'), ('licenses', 'Lizenzen'), ('orders', 'Bestellungen'), ('audit', 'Audit')], max_length=40)),
                ('status', models.CharField(choices=[('queued', 'Warteschlange'), ('running', 'Wird erstellt'), ('ready', 'Bereit'), ('failed', 'Fehlgeschlagen')], default='queued', max_length=20)),
                ('filename', models.CharField(max_length=180)),
                ('query_state_enc', models.TextField()),
                ('file_name', models.CharField(blank=True, max_length=200)),
                ('row_count', models.PositiveIntegerField(default=0)),
                ('error', models.CharField(blank=True, max_length=500)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='export_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['requested_by', '-created_at'], name='core_export_request_2a9bc7_idx'), models.Index(fields=['status', 'expires_at'], name='core_export_status_00eed8_idx')],
            },
        ),
    ]
