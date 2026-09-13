from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class License(TimeStampedModel):
    STATUS = [
        ('active', 'Aktiv'),
        ('free', 'Frei'),
        ('expired', 'Abgelaufen'),
        ('blocked', 'Gesperrt'),
        ('payment_review', 'Zahlung prüfen'),
        ('refunded', 'Refundiert'),
    ]

    license_number = models.CharField(max_length=40, unique=True, blank=True)
    company = models.ForeignKey(
        'companies.Company',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='licenses',
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='owned_licenses',
    )
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='licenses')
    status = models.CharField(max_length=30, choices=STATUS, default='free')
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'valid_until']),
            models.Index(fields=['company', 'product']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(Q(company__isnull=False, owner_user__isnull=True) | Q(company__isnull=True, owner_user__isnull=False)),
                name='license_exactly_one_owner_type',
            ),
            models.CheckConstraint(
                condition=Q(valid_from__isnull=True, valid_until__isnull=True) | Q(valid_from__isnull=False, valid_until__gt=models.F('valid_from')),
                name='license_valid_window',
            ),
        ]

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.license_number:
            self.license_number = f'PM-{self.id.hex.upper()}'
            super().save(update_fields=['license_number'])

    def __str__(self):
        return self.license_number or str(self.pk)


class LicenseTerm(TimeStampedModel):
    STATUS = [('active', 'Aktiv'), ('refunded', 'Refundiert')]

    license = models.ForeignKey(License, on_delete=models.PROTECT, related_name='terms')
    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.PROTECT, related_name='license_terms')
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    paid_gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default='active')
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['valid_from']
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__gt=models.F('valid_from')),
                name='term_end_after_start',
            ),
            models.CheckConstraint(
                condition=Q(paid_gross_amount__gte=0),
                name='term_paid_nonnegative',
            ),
        ]

    def __str__(self):
        return f'{self.license} · {self.valid_from:%Y-%m-%d} – {self.valid_until:%Y-%m-%d}'


class LicenseAssignment(TimeStampedModel):
    license = models.ForeignKey(License, on_delete=models.PROTECT, related_name='assignments')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='license_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['license'],
                condition=Q(ended_at__isnull=True),
                name='one_active_assignment_per_license',
            )
        ]
        indexes = [models.Index(fields=['user', 'ended_at'])]

    def __str__(self):
        return f'{self.license} → {self.user}'


class LicenseReminder(TimeStampedModel):
    KIND = [('t60', 'T-60'), ('t30', 'T-30'), ('t0', 'Abgelaufen')]
    STATUS = [('pending', 'Ausstehend'), ('queued', 'In Warteschlange'), ('sent', 'Gesendet'), ('error', 'Fehler')]

    license = models.ForeignKey(License, on_delete=models.CASCADE, related_name='reminders')
    kind = models.CharField(max_length=10, choices=KIND)
    target_valid_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['license', 'kind', 'target_valid_until'],
                name='uniq_license_reminder_expiry',
            )
        ]

    def __str__(self):
        return f'{self.license} · {self.kind} · {self.target_valid_until:%Y-%m-%d}'


class LicenseUpgradeRequest(TimeStampedModel):
    STATUS = [
        ('pending', 'Offen'),
        ('approved', 'Genehmigt'),
        ('rejected', 'Abgelehnt'),
        ('cancelled', 'Storniert'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='license_upgrade_requests',
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='license_upgrade_requests',
    )
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='upgrade_requests')
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='resolved_license_upgrade_requests',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    assigned_license = models.ForeignKey(
        License,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='upgrade_requests',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'],
                condition=Q(status='pending'),
                name='uniq_pending_upgrade_user_product',
            ),
        ]
        indexes = [models.Index(fields=['company', 'status', '-created_at'])]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} · {self.product} · {self.status}'


class LicenseAssignmentLink(TimeStampedModel):
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='license_assignment_links',
    )
    license = models.ForeignKey(License, on_delete=models.PROTECT, related_name='assignment_links')
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='license_assignment_links',
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_license_assignment_links',
    )

    class Meta:
        indexes = [models.Index(fields=['company', 'target_user', 'expires_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['license', 'target_user'],
                condition=Q(used_at__isnull=True, revoked_at__isnull=True),
                name='uniq_open_assignment_link_license_user',
            ),
        ]

    def is_valid(self, now=None):
        now = now or timezone.now()
        return self.used_at is None and self.revoked_at is None and self.expires_at > now

    def __str__(self):
        return f'{self.license} → {self.target_user}'
