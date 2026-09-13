from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Product(TimeStampedModel):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    visible = models.BooleanField(default=True)
    purchasable = models.BooleanField(default=True)
    default_license_days = models.PositiveIntegerField(default=365)
    default_device_limit = models.PositiveSmallIntegerField(default=2)
    reminder_1_days = models.PositiveSmallIntegerField(default=60)
    reminder_2_days = models.PositiveSmallIntegerField(default=30)
    critical_warning_days = models.PositiveSmallIntegerField(default=7)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(default_license_days__gt=models.F('reminder_1_days'))
                    & Q(reminder_1_days__gt=models.F('reminder_2_days'))
                    & Q(reminder_2_days__gt=models.F('critical_warning_days'))
                    & Q(critical_warning_days__gt=0)
                    & Q(default_device_limit__gt=0)
                ),
                name='product_reminder_order_valid',
            )
        ]

    def clean(self):
        errors = {}
        if self.default_license_days < 1:
            errors['default_license_days'] = 'Laufzeit muss mindestens einen Tag betragen.'
        if self.default_device_limit < 1:
            errors['default_device_limit'] = 'Gerätelimit muss mindestens eins betragen.'
        if not (0 < self.critical_warning_days < self.reminder_2_days < self.reminder_1_days < self.default_license_days):
            errors['reminder_1_days'] = 'Reminder müssen 0 < kritisch < Reminder 2 < Reminder 1 < Laufzeit erfüllen.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class ProductPrice(TimeStampedModel):
    TYPE = [('new', 'Neukauf'), ('renewal', 'Verlängerung')]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='prices')
    price_type = models.CharField(max_length=20, choices=TYPE)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['product', 'price_type', 'valid_from'])]
        constraints = [
            models.CheckConstraint(
                condition=Q(gross_amount__gte=0),
                name='product_price_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F('valid_from')),
                name='product_price_valid_window',
            ),
        ]

    def __str__(self):
        return f'{self.product} · {self.get_price_type_display()} · {self.gross_amount} {self.currency}'


class Feature(TimeStampedModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=160)

    def __str__(self):
        return self.name


class ProductEntitlement(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='entitlements')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['product', 'feature'], name='uniq_product_feature')]


class TaxRule(TimeStampedModel):
    country = models.CharField(max_length=2)
    customer_type = models.CharField(
        max_length=20,
        choices=[('company', 'Firma'), ('private', 'Privat')],
    )
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19)
    require_vat_id = models.BooleanField(default=False)
    require_tax_number = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['country', 'customer_type'],
                condition=Q(active=True),
                name='uniq_active_tax_rule',
            ),
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100),
                name='tax_rate_valid_percent',
            ),
        ]

    def __str__(self):
        return f'{self.country} · {self.customer_type} · {self.tax_rate}%'
