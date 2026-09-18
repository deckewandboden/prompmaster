import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SystemSetting(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict)
    description = models.CharField(max_length=240, blank=True)

    def __str__(self):
        return self.key


class ExportJob(TimeStampedModel):
    STATUS = [
        ('queued', 'Warteschlange'),
        ('running', 'Wird erstellt'),
        ('ready', 'Bereit'),
        ('failed', 'Fehlgeschlagen'),
    ]
    KIND = [
        ('customers', 'Kunden'),
        ('private_customers', 'Privatkunden'),
        ('licenses', 'Lizenzen'),
        ('orders', 'Bestellungen'),
        ('audit', 'Audit'),
    ]

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='export_jobs',
    )
    kind = models.CharField(max_length=40, choices=KIND)
    status = models.CharField(max_length=20, choices=STATUS, default='queued')
    filename = models.CharField(max_length=180)
    query_state_enc = models.TextField()
    file_name = models.CharField(max_length=200, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    run_token = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        # Keep names pinned to the schema introduced by 0004_exportjob.  Explicit
        # names prevent Django-version-dependent auto-name drift from creating
        # no-op RenameIndex migrations on clean installations.
        indexes = [
            models.Index(
                fields=['requested_by', '-created_at'],
                name='core_export_request_2a9bc7_idx',
            ),
            models.Index(
                fields=['status', 'expires_at'],
                name='core_export_status_00eed8_idx',
            ),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} · {self.status} · {self.requested_by}'
