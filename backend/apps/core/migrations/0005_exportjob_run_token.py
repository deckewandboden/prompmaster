from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_exportjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportjob',
            name='run_token',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
    ]
