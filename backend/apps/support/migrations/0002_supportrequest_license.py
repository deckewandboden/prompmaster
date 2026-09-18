from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('licenses', '0002_licenseterm'),
        ('support', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportrequest',
            name='license',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='support_requests',
                to='licenses.license',
            ),
        ),
    ]
