from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class AppendOnlyQuerySet(models.QuerySet):
    def delete(self):
        raise RuntimeError('AuditEvent is append-only')

    def update(self, **kwargs):
        raise RuntimeError('AuditEvent is append-only')


class AuditEvent(TimeStampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_role = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    correlation_id = models.CharField(max_length=80, blank=True)
    changes = models.JSONField(default=dict)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['object_type', 'object_id']),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError('AuditEvent is append-only')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError('AuditEvent is append-only')

    def __str__(self):
        return f'{self.created_at} · {self.action} · {self.object_type}:{self.object_id}'
