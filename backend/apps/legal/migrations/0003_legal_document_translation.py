import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('legal', '0002_consumer_declarations'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalDocumentTranslation',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4,
                                        editable=False, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('language', models.CharField(max_length=5, choices=[
                    ('en', 'English'), ('es', 'Español'), ('pt', 'Português'),
                    ('tr', 'Türkçe'), ('ru', 'Русский'), ('pl', 'Polski'),
                    ('fr', 'Français'), ('it', 'Italiano'), ('nl', 'Nederlands'),
                ])),
                ('content', models.TextField()),
                ('status', models.CharField(max_length=12, default='draft', choices=[
                    ('draft', 'Entwurf'), ('review', 'Fachliche Prüfung'),
                    ('approved', 'Freigegeben'),
                ])),
                ('approval_reference', models.CharField(max_length=240, blank=True)),
                ('approved_at', models.DateTimeField(null=True, blank=True)),
                ('source_sha256', models.CharField(max_length=64, blank=True)),
                ('content_sha256', models.CharField(max_length=64, blank=True)),
                ('approved_by', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    null=True, blank=True, related_name='legal_translation_approvals',
                )),
                ('document', models.ForeignKey(
                    to='legal.legaldocument', on_delete=django.db.models.deletion.PROTECT,
                    related_name='translations',
                )),
            ],
            options={
                'permissions': [
                    ('approve_legal_translation', 'Can approve reviewed legal translations'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='legaldocumenttranslation',
            constraint=models.UniqueConstraint(
                fields=('document', 'language'),
                name='uniq_legal_translation_document_language',
            ),
        ),
    ]
