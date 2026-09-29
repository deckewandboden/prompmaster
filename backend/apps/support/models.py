from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class SupportRequest(TimeStampedModel):
    CATEGORY = [
        ('license', 'Lizenz'),
        ('payment', 'Zahlung'),
        ('user', 'Benutzer'),
        ('device', 'Gerät'),
        ('technical', 'Technisches Problem'),
        ('privacy', 'Datenschutz'),
        ('other', 'Sonstiges'),
    ]
    STATUS = [
        ('new', 'Neu'),
        ('in_progress', 'In Bearbeitung'),
        ('closed', 'Abgeschlossen'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey(
        'companies.Company',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    license = models.ForeignKey(
        'licenses.License',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='support_requests',
    )
    category = models.CharField(max_length=40, choices=CATEGORY)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS, default='new')

    def __str__(self):
        return f'{self.get_category_display()} · {self.subject}'


class SupportMessage(TimeStampedModel):
    SENDER = [
        ('customer', 'Kunde'),
        ('staff', 'netstyle Support'),
        ('system', 'System'),
    ]
    VISIBILITY = [
        ('customer', 'Für Kunden sichtbar'),
        ('internal', 'Interne Notiz'),
    ]

    support_request = models.ForeignKey(
        SupportRequest,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='support_messages_authored',
    )
    sender_type = models.CharField(max_length=20, choices=SENDER)
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY,
        default='customer',
    )
    body = models.TextField()
    notification_email = models.ForeignKey(
        'notifications.EmailMessage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='support_messages',
    )

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(
                fields=['support_request', 'created_at'],
                name='support_msg_req_created_idx',
            ),
        ]

    @property
    def author_display(self):
        if self.author_user_id:
            return self.author_user.full_name
        return self.get_sender_type_display()

    def __str__(self):
        return f'{self.support_request.subject} · {self.get_sender_type_display()}'
