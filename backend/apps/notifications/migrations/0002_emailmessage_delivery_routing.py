from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailmessage',
            name='provider_used',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='emailmessage',
            name='delivery_attempts',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
