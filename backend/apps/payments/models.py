from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    STATUS = [
        ('created', 'Erstellt'),
        ('open', 'Offen'),
        ('pending', 'Ausstehend'),
        ('authorized', 'Autorisiert'),
        ('paid', 'Bezahlt'),
        ('failed', 'Fehlgeschlagen'),
        ('canceled', 'Storniert'),
        ('expired', 'Abgelaufen'),
        ('refunded_partial', 'Teilweise erstattet'),
        ('refunded_full', 'Vollständig erstattet'),
        ('chargeback', 'Chargeback'),
        ('chargeback_reversed', 'Chargeback zurückgenommen'),
        ('unknown', 'Unbekannt'),
    ]

    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='payments')
    provider = models.CharField(max_length=30, default='mollie')
    provider_payment_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=40, choices=STATUS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    method = models.CharField(max_length=50, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    processed_paid = models.BooleanField(default=False)
    last_provider_payload = models.JSONField(default=dict)

    def save(self, *args, **kwargs):
        # Keep the first known failure point as immutable history. The webhook
        # state machine also sets this field, but model-level protection covers
        # administrative and maintenance saves that bypass that path.
        if self.status in {'failed', 'canceled', 'expired'} and self.failed_at is None:
            self.failed_at = timezone.now()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'failed_at'}
        super().save(*args, **kwargs)

    def __str__(self):
        return self.provider_payment_id


class MollieEvent(TimeStampedModel):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='events')
    provider_status = models.CharField(max_length=40)
    event_key = models.CharField(max_length=180, unique=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.event_key


class Refund(TimeStampedModel):
    STATUS = [('created', 'Erstellt'), ('submitted', 'Übermittelt'), ('succeeded', 'Erfolgreich'), ('failed', 'Fehlgeschlagen')]

    # The V1 policy is one pro-rata termination/refund per paid term. A
    # OneToOne relation prevents duplicate logical refund requests under races.
    # Provider retries are retained separately in RefundAttempt.
    term = models.OneToOneField('licenses.LicenseTerm', on_delete=models.PROTECT, related_name='refund')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    provider_refund_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_days = models.PositiveIntegerField()
    status = models.CharField(max_length=30, choices=STATUS, default='created')
    reason = models.TextField(blank=True)

    def __str__(self):
        return f'{self.term} · {self.amount} {self.payment.currency}'


class RefundAttempt(TimeStampedModel):
    """Immutable-ish provider submission history for one logical refund.

    A deterministic provider rejection may be retried with a new quote and a
    new attempt key. An ambiguous network/server outcome must reuse the same
    idempotency key until its outcome is known, preventing a double refund.
    """

    STATUS = [
        ('submitted', 'Übermittelt'),
        ('ambiguous', 'Ausgang unklar'),
        ('succeeded', 'Erfolgreich'),
        ('failed', 'Fehlgeschlagen'),
    ]

    refund = models.ForeignKey(Refund, on_delete=models.PROTECT, related_name='attempts')
    number = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=180, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider_refund_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS, default='submitted')
    error_class = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['refund', 'number'],
                name='uniq_refund_attempt_number',
            ),
        ]
        indexes = [
            models.Index(fields=['refund', '-number']),
            models.Index(fields=['status', 'submitted_at']),
        ]

    def __str__(self):
        return f'{self.refund_id} · Versuch {self.number} · {self.status}'
