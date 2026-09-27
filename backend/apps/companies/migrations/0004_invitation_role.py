from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0003_privatecustomerprofile_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Firmenadministrator'),
                    ('member', 'Mitarbeiter'),
                ],
                default='member',
                max_length=20,
            ),
        ),
    ]
