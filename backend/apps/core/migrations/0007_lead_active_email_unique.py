from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_lead'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='lead',
            constraint=models.UniqueConstraint(
                Lower('email'),
                condition=Q(deleted_at__isnull=True),
                name='uniq_active_lead_email_ci',
            ),
        ),
    ]
