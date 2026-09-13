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
    STATUS = [('new', 'Neu'), ('in_progress', 'In Bearbeitung'), ('closed', 'Abgeschlossen')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey('companies.Company', null=True, blank=True, on_delete=models.PROTECT)
    category = models.CharField(max_length=40, choices=CATEGORY)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS, default='new')

    def __str__(self):
        return f'{self.get_category_display()} · {self.subject}'
