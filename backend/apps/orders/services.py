import secrets
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.catalog.models import TaxRule
from apps.catalog.services import current_price
from .models import Order, OrderItem

CENT = Decimal('0.01')
MAX_PURCHASE_QUANTITY = 500


def _tax_rule_for(user, company):
    if company:
        country = company.country
        customer_type = 'company'
        if not all([company.name, company.email, company.street, company.postal_code, company.city, company.country]):
            raise ValidationError('Bitte Unternehmens- und Adressdaten vor dem Kauf vervollständigen.')
    else:
        try:
            profile = user.private_customer
        except Exception as exc:
            raise ValidationError('Privatkundenprofil fehlt.') from exc
        country = profile.country
        customer_type = 'private'
        if not all([profile.street, profile.postal_code, profile.city, profile.country]):
            raise ValidationError('Bitte Adressdaten vor dem Kauf vervollständigen.')

    rule = TaxRule.objects.filter(country=country, customer_type=customer_type, active=True).first()
    if not rule:
        raise ValidationError('Für dieses Land ist noch keine aktive Steuerregel konfiguriert.')
    if company and rule.require_vat_id and not company.vat_id:
        raise ValidationError('Für diesen Kauf ist eine USt-IdNr. erforderlich.')
    if company and rule.require_tax_number and not company.tax_number:
        raise ValidationError('Für diesen Kauf ist eine Steuernummer erforderlich.')
    return rule


def _billing_snapshot(user, company, rule):
    if company:
        return {
            'customer_type': 'company',
            'company': company.name,
            'legal_form': company.legal_form,
            'email': company.email or user.email,
            'street': company.street,
            'house_number': company.house_number,
            'postal_code': company.postal_code,
            'city': company.city,
            'country': company.country,
            'vat_id': company.vat_id,
            'tax_number': company.tax_number,
            'tax_rate': str(rule.tax_rate),
        }
    profile = user.private_customer
    return {
        'customer_type': 'private',
        'name': user.full_name,
        'email': user.email,
        'street': profile.street,
        'house_number': profile.house_number,
        'postal_code': profile.postal_code,
        'city': profile.city,
        'country': profile.country,
        'tax_rate': str(rule.tax_rate),
    }


@transaction.atomic
def create_order(*, user, product, quantity=1, target_license=None, idempotency_key=None):
    if quantity < 1 or quantity > MAX_PURCHASE_QUANTITY:
        raise ValidationError('Ungültige Anzahl.')
    if not product.active or not product.purchasable:
        raise ValidationError('Produkt ist derzeit nicht kaufbar.')

    membership = user.company_memberships.select_for_update().filter(active=True).select_related('company').first()
    if not membership:
        # Serialize private-customer checkout just as company checkout is
        # serialized by the membership row. This closes double-submit races.
        user = get_user_model().objects.select_for_update().get(pk=user.pk)
    company = membership.company if membership else None
    if company and membership.role != 'admin':
        raise ValidationError('Nur der Firmenadministrator darf Lizenzen kaufen oder verlängern.')

    if target_license:
        from apps.licenses.models import License
        target_license = License.objects.select_for_update().get(pk=target_license.pk)
        if quantity != 1:
            raise ValidationError('Eine Verlängerung gilt immer für genau eine Lizenz.')
        if target_license.product_id != product.id:
            raise ValidationError('Produkt und Lizenz stimmen nicht überein.')
        if company and target_license.company_id != company.id:
            raise ValidationError('Lizenz gehört nicht zu diesem Unternehmen.')
        if not company and target_license.owner_user_id != user.id:
            raise ValidationError('Lizenz gehört nicht zu diesem Benutzer.')
        pending_renewal = OrderItem.objects.filter(
            target_license=target_license,
            order__status__in=['draft', 'payment_open'],
        ).select_related('order').order_by('-created_at').first()
        if pending_renewal:
            return pending_renewal.order

    if idempotency_key:
        existing = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            owner_ok = existing.company_id == (company.id if company else None) and existing.private_user_id == (None if company else user.id)
            if not owner_ok:
                raise ValidationError('Ungültiger Checkout-Schlüssel.')
            return existing

    price_type = 'renewal' if target_license else 'new'
    price = current_price(product, price_type)
    if not price:
        raise ValidationError('Kein gültiger Preis konfiguriert.')

    rule = _tax_rule_for(user, company)
    divisor = Decimal('1') + (rule.tax_rate / Decimal('100'))
    unit_net = (price.gross_amount / divisor).quantize(CENT, rounding=ROUND_HALF_UP)
    unit_tax = price.gross_amount - unit_net
    gross = (price.gross_amount * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    tax_total = (unit_tax * quantity).quantize(CENT, rounding=ROUND_HALF_UP)

    order = Order.objects.create(
        order_number=f'PM-O-{uuid.uuid4().hex.upper()}',
        company=company,
        private_user=None if company else user,
        status='draft',
        currency=price.currency,
        gross_total=gross,
        tax_total=tax_total,
        billing_snapshot=_billing_snapshot(user, company, rule),
        idempotency_key=idempotency_key or secrets.token_urlsafe(24),
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        price_version=price,
        quantity=quantity,
        unit_gross=price.gross_amount,
        unit_net=unit_net,
        tax_rate=rule.tax_rate,
        product_name_snapshot=product.name,
        target_license=target_license,
    )
    return order
