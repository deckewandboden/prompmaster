import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_support_reply_template(apps, schema_editor):
    EmailTemplate = apps.get_model('notifications', 'EmailTemplate')
    EmailTemplate.objects.get_or_create(
        code='support_reply',
        defaults={
            'subject': 'Antwort auf Ihre PromptMaster-Anfrage: {subject}',
            'body_text': (
                'Guten Tag,\n\n'
                'wir haben auf Ihre PromptMaster-Anfrage „{subject}“ geantwortet:\n\n'
                '{message}\n\n'
                'Vorgang: {reference}\n\n'
                'Viele Grüße\nIhr PromptMaster-Support'
            ),
            'active': True,
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notifications', '0001_initial'),
        ('support', '0002_supportrequest_license'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('direction', models.CharField(choices=[('customer', 'Kunde'), ('staff', 'netstyle')], max_length=20)),
                ('body', models.TextField()),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='support_messages_authored', to=settings.AUTH_USER_MODEL)),
                ('email_message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='support_messages', to='notifications.emailmessage')),
                ('support_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='support.supportrequest')),
            ],
            options={
                'ordering': ('created_at', 'id'),
            },
        ),
        migrations.RunPython(seed_support_reply_template, noop_reverse),
    ]
