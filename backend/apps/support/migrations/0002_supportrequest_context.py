from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportrequest',
            name='context',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
