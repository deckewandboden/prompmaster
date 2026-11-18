from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('legal', '0004_legal_translation_submitted_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='legaldocumenttranslation',
            name='source_identity_sha256',
            field=models.CharField(max_length=64, blank=True),
        ),
    ]
