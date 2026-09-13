from django.db import models

from apps.core.models import TimeStampedModel


class FAQEntry(TimeStampedModel):
    AUDIENCE = [
        ('public', 'Öffentlich'),
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('customer', 'Kundenportal'),
    ]

    key = models.SlugField(max_length=120, unique=True)
    question = models.CharField(max_length=300)
    answer = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE, default='public')
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['audience', 'sort_order', 'question']
        indexes = [models.Index(fields=['audience', 'active', 'sort_order'])]

    def __str__(self):
        return self.question
