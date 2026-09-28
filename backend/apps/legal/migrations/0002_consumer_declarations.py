import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('legal', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='legaldocument',
            name='doc_type',
            field=models.CharField(
                choices=[
                    ('terms', 'AGB'),
                    ('privacy', 'Datenschutz'),
                    ('withdrawal', 'Widerruf'),
                    ('license', 'Lizenzbedingungen'),
                    ('imprint', 'Impressum'),
                    ('accessibility', 'Barrierefreiheit'),
                ],
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name='ConsumerContractDeclaration',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('withdrawal', 'Widerruf'), ('cancellation', 'Kündigung')], max_length=20)),
                ('cancellation_kind', models.CharField(blank=True, choices=[('ordinary', 'Ordentliche Kündigung'), ('extraordinary', 'Außerordentliche Kündigung')], max_length=20)),
                ('name', models.CharField(max_length=240)),
                ('email', models.EmailField(max_length=254)),
                ('contract_reference', models.CharField(max_length=160)),
                ('requested_end_date', models.DateField(blank=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('received', 'Eingegangen'), ('processing', 'In Bearbeitung'), ('completed', 'Abgeschlossen'), ('rejected', 'Abgelehnt')], default='received', max_length=20)),
                ('submitted_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('confirmation_sent_at', models.DateTimeField(blank=True, null=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('request_meta', models.JSONField(default=dict)),
                ('internal_notes', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['-submitted_at'],
            },
        ),
        migrations.AddIndex(
            model_name='consumercontractdeclaration',
            index=models.Index(fields=['kind', '-submitted_at'], name='legal_decl_kind_sub_idx'),
        ),
        migrations.AddIndex(
            model_name='consumercontractdeclaration',
            index=models.Index(fields=['email', '-submitted_at'], name='legal_decl_email_sub_idx'),
        ),
        migrations.AddIndex(
            model_name='consumercontractdeclaration',
            index=models.Index(fields=['status', '-submitted_at'], name='legal_decl_status_sub_idx'),
        ),
    ]
