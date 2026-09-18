from django.conf import settings
from django.db import models, transaction
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Order(TimeStampedModel):
    STATUS = [
        ('draft', 'Entwurf'),
        ('payment_open', 'Zahlung offen'),
        ('paid', 'Bezahlt'),
        ('failed', 'Fehlgeschlagen'),
        ('canceled', 'Storniert'),
    ]

    order_number = models.CharField(max_length=40, unique=True)
    company = models.ForeignKey(
        'companies.Company',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    private_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='private_orders',
    )
    status = models.CharField(max_length=30, choices=STATUS, default='draft')
    currency = models.CharField(max_length=3, default='EUR')
    gross_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing_snapshot = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=80, unique=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at'])]
        constraints = [
            models.CheckConstraint(
                condition=(Q(company__isnull=False, private_user__isnull=True) | Q(company__isnull=True, private_user__isnull=False)),
                name='order_exactly_one_customer',
            ),
            models.CheckConstraint(condition=Q(gross_total__gte=0), name='order_gross_nonnegative'),
            models.CheckConstraint(condition=Q(tax_total__gte=0), name='order_tax_nonnegative'),
        ]

    def save(self, *args, **kwargs):
        # Payment confirmation is a terminal business transition for the order.
        # A replayed checkout request, provider timeout or stale browser POST
        # must never downgrade an already-paid order back to payment_open,
        # failed or canceled. Refund/chargeback state lives on Payment/License.
        #
        # The row lock is essential here. A plain read-then-save guard has a
        # TOCTOU race: another transaction can commit ``paid`` after the read
        # but before this stale save obtains its UPDATE lock, causing the stale
        # writer to overwrite the successful payment. Serialize every
        # non-paid transition with the order row so whichever transaction wins
        # first still leaves ``paid`` terminal.
        if self.pk and self.status != 'paid':
            with transaction.atomic():
                previous = (
                    type(self).objects.select_for_update()
                    .filter(pk=self.pk)
                    .values_list('status', flat=True)
                    .first()
                )
                if previous == 'paid':
                    self.status = 'paid'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    price_version = models.ForeignKey('catalog.ProductPrice', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_gross = models.DecimalField(max_digits=10, decimal_places=2)
    unit_net = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    product_name_snapshot = models.CharField(max_length=160)
    target_license = models.ForeignKey(
        'licenses.License',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='renewal_order_items',
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='order_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_gross__gte=0), name='order_item_gross_nonnegative'),
            models.CheckConstraint(condition=Q(unit_net__gte=0), name='order_item_net_nonnegative'),
        ]

    def __str__(self):
        return f'{self.order.order_number} · {self.product_name_snapshot} × {self.quantity}'
