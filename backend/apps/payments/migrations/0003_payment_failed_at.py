from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_normalize_chargeback_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='failed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
