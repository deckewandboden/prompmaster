import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='FAQEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.SlugField(max_length=120, unique=True)),
                ('question', models.CharField(max_length=300)),
                ('answer', models.TextField()),
                ('audience', models.CharField(choices=[('public','Öffentlich'),('free','Free'),('pro','Pro'),('customer','Kundenportal')], default='public', max_length=20)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['audience', 'sort_order', 'question']},
        ),
        migrations.AddIndex(
            model_name='faqentry',
            index=models.Index(fields=['audience', 'active', 'sort_order'], name='contenthub_f_audienc_46b102_idx'),
        ),
    ]
