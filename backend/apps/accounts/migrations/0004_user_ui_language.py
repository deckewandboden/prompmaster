from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_totp_replay_protection'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ui_language',
            field=models.CharField(default='de', max_length=10),
        ),
    ]
