from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class LegalDocument(TimeStampedModel):
    DOC_TYPES = [
        ('terms', 'AGB'),
        ('privacy', 'Datenschutz'),
        ('withdrawal', 'Widerruf'),
        ('license', 'Lizenzbedingungen'),
        ('imprint', 'Impressum'),
        ('accessibility', 'Barrierefreiheit'),
    ]

    doc_type = models.CharField(max_length=30, choices=DOC_TYPES)
    version = models.CharField(max_length=30)
    content = models.TextField()
    valid_from = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['doc_type', 'version'], name='uniq_legal_version'),
            models.UniqueConstraint(fields=['doc_type'], condition=Q(active=True), name='uniq_active_legal_type'),
        ]

    def __str__(self):
        return f'{self.get_doc_type_display()} {self.version}'


class LegalAcceptance(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT)
    accepted_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey('orders.Order', null=True, blank=True, on_delete=models.PROTECT)
    evidence = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'document', 'order'], name='uniq_legal_acceptance'),
            models.UniqueConstraint(
                fields=['user', 'document'],
                condition=Q(order__isnull=True),
                name='uniq_account_legal_acceptance',
            ),
        ]


class RetentionPolicy(TimeStampedModel):
    data_class = models.CharField(max_length=80, unique=True)
    retain_days = models.PositiveIntegerField()
    active = models.BooleanField(default=True)


class DeletionRequest(TimeStampedModel):
    STATUS = [('open', 'Offen'), ('processing', 'In Bearbeitung'), ('completed', 'Abgeschlossen'), ('rejected', 'Abgelehnt')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=STATUS, default='open')
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)


class ConsumerContractDeclaration(TimeStampedModel):
    KIND = [
        ('withdrawal', 'Widerruf'),
        ('cancellation', 'Kündigung'),
    ]
    CANCELLATION_KIND = [
        ('ordinary', 'Ordentliche Kündigung'),
        ('extraordinary', 'Außerordentliche Kündigung'),
    ]
    STATUS = [
        ('received', 'Eingegangen'),
        ('processing', 'In Bearbeitung'),
        ('completed', 'Abgeschlossen'),
        ('rejected', 'Abgelehnt'),
    ]

    kind = models.CharField(max_length=20, choices=KIND)
    cancellation_kind = models.CharField(
        max_length=20,
        choices=CANCELLATION_KIND,
        blank=True,
    )
    name = models.CharField(max_length=240)
    email = models.EmailField()
    contract_reference = models.CharField(max_length=160)
    requested_end_date = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='received')
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmation_sent_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    request_meta = models.JSONField(default=dict)
    internal_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['kind', '-submitted_at']),
            models.Index(fields=['email', '-submitted_at']),
            models.Index(fields=['status', '-submitted_at']),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} · {self.contract_reference} · {self.email}'
