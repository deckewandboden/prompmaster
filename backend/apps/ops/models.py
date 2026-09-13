from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class SystemAlert(TimeStampedModel):
    SEVERITY = [('warning', 'Warnung'), ('critical', 'Kritisch')]

    code = models.CharField(max_length=100)
    severity = models.CharField(max_length=20, choices=SEVERITY)
    message = models.CharField(max_length=500)
    active = models.BooleanField(default=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code'], condition=Q(active=True), name='uniq_active_system_alert')
        ]
        indexes = [models.Index(fields=['active', 'severity', 'created_at'])]

    def __str__(self):
        return f'{self.severity}: {self.code}'


class BackupRecord(TimeStampedModel):
    status = models.CharField(max_length=30)
    provider_ref = models.CharField(max_length=200, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-finished_at', '-created_at']


class RestoreTest(TimeStampedModel):
    status = models.CharField(max_length=30)
    backup_ref = models.CharField(max_length=200)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ['-started_at']


class WorkerHeartbeat(TimeStampedModel):
    """Last successfully executed heartbeat by a Celery worker."""
    name = models.CharField(max_length=80, unique=True, default='default')
    last_seen_at = models.DateTimeField()
    hostname = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f'{self.name} · {self.last_seen_at}'


class BeatHeartbeat(TimeStampedModel):
    """Last heartbeat task dispatched by Celery Beat and executed by a worker."""
    name = models.CharField(max_length=80, unique=True, default='default')
    last_seen_at = models.DateTimeField()
    hostname = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f'{self.name} · {self.last_seen_at}'


class TaskFailure(TimeStampedModel):
    task_id = models.CharField(max_length=100, unique=True)
    task_name = models.CharField(max_length=200)
    error = models.CharField(max_length=1000)
    failed_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-failed_at']
        indexes = [models.Index(fields=['resolved_at', 'failed_at'])]

    def __str__(self):
        return f'{self.task_name} · {self.task_id}'
