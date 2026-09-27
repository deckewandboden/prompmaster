from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0002_rename_companies_c_name_idx_companies_c_name_2d8260_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='privatecustomerprofile',
            name='phone',
            field=models.CharField(blank=True, max_length=60),
        ),
    ]
