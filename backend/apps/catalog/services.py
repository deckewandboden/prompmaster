from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Product, ProductPrice


PRO_ACCESS_FEATURE = 'promptmaster.pro_runtime'


def current_price(product, price_type, at=None):
    at = at or timezone.now()
    return (
        ProductPrice.objects.filter(
            product=product,
            price_type=price_type,
            active=True,
            valid_from__lte=at,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at))
        .order_by('-valid_from')
        .first()
    )


@transaction.atomic
def create_price_version(*, product, price_type, gross_amount, currency='EUR', valid_from=None):
    valid_from = valid_from or timezone.now()
    if gross_amount < 0:
        raise ValidationError('Preis darf nicht negativ sein.')

    # Lock the parent even when no price row exists yet; otherwise two empty
    # streams could race and both insert an open-ended version.
    product = Product.objects.select_for_update().get(pk=product.pk)

    rows = list(
        ProductPrice.objects.select_for_update()
        .filter(product=product, price_type=price_type, active=True)
        .order_by('-valid_from')
    )
    for row in rows:
        if row.valid_from >= valid_from:
            raise ValidationError('Es existiert bereits eine Preisversion ab diesem oder einem späteren Zeitpunkt.')
        if row.valid_until is None or row.valid_until > valid_from:
            row.valid_until = valid_from
            row.save(update_fields=['valid_until', 'updated_at'])

    return ProductPrice.objects.create(
        product=product,
        price_type=price_type,
        gross_amount=gross_amount,
        currency=currency.upper(),
        valid_from=valid_from,
        active=True,
    )
