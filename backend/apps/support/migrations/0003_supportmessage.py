import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


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
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'sender_type',
                    models.CharField(
                        choices=[
                            ('customer', 'Kunde'),
                            ('staff', 'netstyle Support'),
                            ('system', 'System'),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    'visibility',
                    models.CharField(
                        choices=[
                            ('customer', 'Für Kunden sichtbar'),
                            ('internal', 'Interne Notiz'),
                        ],
                        default='customer',
                        max_length=20,
                    ),
                ),
                ('body', models.TextField()),
                (
                    'author_user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='support_messages_authored',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'notification_email',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='support_messages',
                        to='notifications.emailmessage',
                    ),
                ),
                (
                    'support_request',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='messages',
                        to='support.supportrequest',
                    ),
                ),
            ],
            options={
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='supportmessage',
            index=models.Index(
                fields=['support_request', 'created_at'],
                name='support_msg_req_created_idx',
            ),
        ),
    ]
