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


class Lead(TimeStampedModel):
    STATUS = [
        ('new', 'Neu'),
        ('contacted', 'Kontaktiert'),
        ('qualified', 'Qualifiziert'),
        ('won', 'Gewonnen'),
        ('lost', 'Verloren'),
    ]
    SOURCE = [
        ('website', 'Website'),
        ('free', 'PromptMaster Free'),
        ('checkout', 'Checkout'),
        ('contact', 'Kontaktanfrage'),
        ('manual', 'Manuell'),
        ('other', 'Sonstiges'),
    ]
    KIND = [
        ('company', 'Unternehmen'),
        ('private', 'Privatkunde'),
    ]
    PRIORITY = [
        ('low', 'Niedrig'),
        ('normal', 'Normal'),
        ('high', 'Hoch'),
    ]

    lead_number = models.CharField(max_length=24, unique=True, editable=False)
    kind = models.CharField(max_length=20, choices=KIND, default='company')
    company_name = models.CharField(max_length=200, blank=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=60, blank=True)
    source = models.CharField(max_length=30, choices=SOURCE, default='manual')
    status = models.CharField(max_length=30, choices=STATUS, default='new', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY, default='normal')
    notes = models.TextField(blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='assigned_leads',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='created_leads',
    )
    converted_company = models.ForeignKey(
        'companies.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_leads',
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at'], name='core_lead_status_created_idx'),
            models.Index(fields=['assigned_to', 'status'], name='core_lead_owner_status_idx'),
            models.Index(fields=['deleted_at', '-created_at'], name='core_lead_deleted_created_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.lead_number:
            self.lead_number = f'LD-{str(self.id).split("-")[0].upper()}'
        super().save(*args, **kwargs)

    @property
    def contact_name(self):
        value = f'{self.first_name} {self.last_name}'.strip()
        return value or self.email

    @property
    def assigned_name(self):
        return self.assigned_to.full_name if self.assigned_to_id else 'Nicht zugewiesen'

    @property
    def status_name(self):
        return self.get_status_display()

    @property
    def customer_display(self):
        return self.company_name or self.contact_name

    def __str__(self):
        return f'{self.lead_number} · {self.customer_display}'
