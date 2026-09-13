import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ops', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='BeatHeartbeat',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(default='default', max_length=80, unique=True)),
                ('last_seen_at', models.DateTimeField()),
                ('hostname', models.CharField(blank=True, max_length=200)),
            ],
        ),
    ]
