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


class LegalDocumentTranslation(TimeStampedModel):
    """Reviewed rendering of an exact German LegalDocument version.

    This never replaces the canonical German source or LegalAcceptance link.
    Publishing also requires a separate, default-off application feature gate.
    """

    LANGUAGES = [
        ('en', 'English'), ('es', 'Español'), ('pt', 'Português'),
        ('tr', 'Türkçe'), ('ru', 'Русский'), ('pl', 'Polski'),
        ('fr', 'Français'), ('it', 'Italiano'), ('nl', 'Nederlands'),
    ]
    STATUSES = [
        ('draft', 'Entwurf'),
        ('review', 'Fachliche Prüfung'),
        ('approved', 'Freigegeben'),
    ]
    document = models.ForeignKey(
        LegalDocument, on_delete=models.PROTECT, related_name='translations',
    )
    language = models.CharField(max_length=5, choices=LANGUAGES)
    content = models.TextField()
    status = models.CharField(max_length=12, choices=STATUSES, default='draft')
    approval_reference = models.CharField(max_length=240, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='legal_translation_submissions',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='legal_translation_approvals',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    source_sha256 = models.CharField(max_length=64, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'language'],
                name='uniq_legal_translation_document_language',
            ),
        ]
        permissions = [
            ('approve_legal_translation', 'Can approve reviewed legal translations'),
        ]

    @staticmethod
    def fingerprint(text):
        import hashlib
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _current_source_fingerprint(self):
        # Do not trust a cached foreign-key object after the original has
        # changed in the database since the previous legal review.
        original = LegalDocument.objects.values_list('content', flat=True).get(
            pk=self.document_id,
        )
        return self.fingerprint(original)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.language == 'de':
            raise ValidationError({'language': 'The original German text belongs to LegalDocument.'})
        if not self.content or not self.content.strip():
            raise ValidationError({'content': 'A legal translation cannot be empty.'})
        if self.status in ('review', 'approved'):
            # A review binds BOTH the original German source and the translated
            # body. An edited source/text must go through a new review cycle.
            if (self.source_sha256 != self._current_source_fingerprint()
                    or self.content_sha256 != self.fingerprint(self.content)):
                raise ValidationError('The reviewed translation or original source changed.')
        if self.status == 'approved':
            if not self.approved_at or not self.approved_by_id or not self.approval_reference.strip():
                raise ValidationError('Approval requires a reviewer, timestamp and legal sign-off reference.')

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        previous = type(self).objects.filter(pk=self.pk).values(
            'status', 'document_id', 'language', 'content', 'approval_reference',
            'approved_by_id', 'approved_at', 'source_sha256', 'content_sha256',
            'submitted_by_id',
        ).first()
        # Approval is a privileged state transition, not an assignable field.
        # Require the persisted row to be under review and the permission-
        # checked approve() method to have initiated this exact save.
        # This also rejects approval from a stale review object if another
        # administrator has meanwhile returned the row to draft.
        if self.status == 'approved' and (
            not previous or (
                previous['status'] != 'approved' and (
                    previous['status'] != 'review'
                    or not getattr(self, '_approval_via_reviewer_method', False)
                )
            )
        ):
            raise ValidationError('Legal approval must use the authorized review workflow.')
        if previous and previous['status'] == 'approved':
            immutable = (
                'status', 'document_id', 'language', 'content', 'approval_reference',
                'approved_by_id', 'approved_at', 'source_sha256', 'content_sha256',
            'submitted_by_id',
            )
            if any(previous[field] != getattr(self, field) for field in immutable):
                raise ValidationError('Approved legal translations are immutable.')
        if previous and previous['status'] == 'review':
            # It is never permissible to approve text that changed AFTER the
            # reviewer received it. Return an unchanged review to draft first.
            frozen = ('document_id', 'language', 'content')
            if any(previous[field] != getattr(self, field) for field in frozen):
                raise ValidationError('Review content is frozen; return to draft before editing.')
            if self.status == 'draft':
                self.source_sha256 = ''
                self.content_sha256 = ''
            elif self.submitted_by_id != previous['submitted_by_id']:
                raise ValidationError('The submitting reviewer is immutable during review.')
            elif (self.source_sha256 != previous['source_sha256']
                    or self.content_sha256 != previous['content_sha256']):
                raise ValidationError('The review fingerprint cannot be replaced.')
        if self.status == 'review' and (not previous or previous['status'] == 'draft'):
            # Capture source + translation exactly when entering review.
            self.source_sha256 = self._current_source_fingerprint()
            self.content_sha256 = self.fingerprint(self.content)
        self.full_clean()
        super().save(*args, **kwargs)

    def approve(self, *, reviewer, reference):
        from django.core.exceptions import ValidationError
        from django.utils import timezone

        if self.status != 'review':
            raise ValidationError('Only a reviewed legal translation can be approved.')
        from apps.core.permissions import has_perm as role_has_perm
        if not reviewer or not reviewer.is_active or not (
            reviewer.has_perm('legal.approve_legal_translation')
            or role_has_perm(reviewer, 'legal.approve')
        ):
            raise ValidationError('The reviewer lacks legal approval permission.')
        if self.submitted_by_id and self.submitted_by_id == reviewer.pk:
            raise ValidationError('A legal reviewer cannot approve their own submission.')
        if not reference or not reference.strip():
            raise ValidationError('An independently verified legal approval reference is required.')
        self.approved_by = reviewer
        self.approved_at = timezone.now()
        self.approval_reference = reference.strip()
        # Do not recompute fingerprints here: they must match the text that
        # was frozen at submission for legal review, not today's current text.
        self.status = 'approved'
        self._approval_via_reviewer_method = True
        try:
            self.save()
        finally:
            self._approval_via_reviewer_method = False

    def is_publishable(self):
        return bool(
            self.status == 'approved'
            and self.approved_at
            and self.approved_by_id
            and self.approval_reference.strip()
            and self.content.strip()
            and self.source_sha256 == self._current_source_fingerprint()
            and self.content_sha256 == self.fingerprint(self.content)
        )

    def __str__(self):
        return f'{self.document} · {self.language} · {self.status}'


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
            models.Index(fields=['kind', '-submitted_at'], name='legal_decl_kind_sub_idx'),
            models.Index(fields=['email', '-submitted_at'], name='legal_decl_email_sub_idx'),
            models.Index(fields=['status', '-submitted_at'], name='legal_decl_status_sub_idx'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} · {self.contract_reference} · {self.email}'
