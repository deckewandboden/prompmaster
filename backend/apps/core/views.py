from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def home(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    if request.user.is_staff:
        return redirect('ns_admin:dashboard')
    return redirect('portal:dashboard')


def health_live(request):
    return JsonResponse({'status': 'ok'})


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return JsonResponse({'status': 'ready'})
    except Exception:
        return JsonResponse({'status': 'not_ready'}, status=503)


def metrics_internal(request):
    # Caddy supplies X-Forwarded-For for all public requests. Prometheus talks
    # directly to the web container and does not, so public access is hidden
    # while the metrics port remains unexposed on the host.
    if request.headers.get('X-Forwarded-For'):
        return HttpResponse(status=404)
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


def legal_public(request, doc_type):
    from django.http import Http404
    from django.utils import timezone
    from apps.legal.models import LegalDocument

    allowed = {code for code, _label in LegalDocument.DOC_TYPES}
    if doc_type not in allowed:
        raise Http404
    document = (
        LegalDocument.objects.filter(doc_type=doc_type, active=True, valid_from__lte=timezone.now())
        .order_by('-valid_from')
        .first()
    )
    if not document:
        raise Http404
    return render(request, 'legal_public.html', {'document': document})




def _resolve_consumer_contract_end(email, order_number):
    """Resolve a contract end date without exposing contract existence publicly."""
    from django.db.models import Q
    from apps.licenses.models import LicenseTerm
    from apps.orders.models import Order

    email = (email or '').strip().lower()
    order_number = (order_number or '').strip()
    if not email or not order_number:
        return None

    order = (
        Order.objects.filter(order_number__iexact=order_number)
        .filter(
            Q(private_user__email__iexact=email)
            | Q(
                company__memberships__user__email__iexact=email,
                company__memberships__active=True,
            )
        )
        .distinct()
        .first()
    )
    if not order:
        return None

    latest = (
        LicenseTerm.objects.filter(
            order_item__order=order,
            status='active',
        )
        .order_by('-valid_until')
        .values_list('valid_until', flat=True)
        .first()
    )
    return latest.date() if latest else None

def contract_withdrawal(request):
    from django.utils import timezone

    from apps.core.security import check_rate
    from apps.legal.forms import WithdrawalDeclarationForm
    from apps.legal.models import ConsumerContractDeclaration
    from apps.notifications.services import queue_email

    if request.method == 'POST':
        limited = check_rate(request, 'contract-withdrawal', 20, 3600)
        if limited:
            return limited

    form = WithdrawalDeclarationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        declaration = ConsumerContractDeclaration.objects.create(
            kind='withdrawal',
            name=form.cleaned_data['name'].strip(),
            email=form.cleaned_data['email'].strip().lower(),
            contract_reference=form.cleaned_data['contract_reference'].strip(),
            request_meta={'source': 'public_web'},
        )
        submitted = timezone.localtime(declaration.submitted_at).strftime('%d.%m.%Y %H:%M:%S %Z')
        queue_email(
            'withdrawal_received',
            declaration.email,
            {
                'name': declaration.name,
                'contract_reference': declaration.contract_reference,
                'submitted_at': submitted,
                'declaration_id': str(declaration.id),
            },
        )
        return render(
            request,
            'legal_action_success.html',
            {
                'declaration': declaration,
                'title': 'Widerruf eingegangen',
                'message': 'Ihr Widerruf wurde elektronisch entgegengenommen.',
            },
        )

    return render(
        request,
        'legal_action_form.html',
        {
            'form': form,
            'page_title': 'Vertrag widerrufen',
            'eyebrow': 'WIDERRUFSFUNKTION',
            'intro': (
                'Mit diesem Formular können Verbraucher einen über PromptMaster '
                'geschlossenen Fernabsatzvertrag widerrufen.'
            ),
            'notice': (
                'Nach dem Absenden erhalten Sie unverzüglich eine elektronische '
                'Eingangsbestätigung an die angegebene E-Mail-Adresse.'
            ),
            'submit_label': 'Widerruf bestätigen',
        },
    )


def contract_cancellation(request):
    from django.utils import timezone

    from apps.core.security import check_rate
    from apps.legal.forms import CancellationDeclarationForm
    from apps.legal.models import ConsumerContractDeclaration
    from apps.notifications.services import queue_email

    if request.method == 'POST':
        limited = check_rate(request, 'contract-cancellation', 20, 3600)
        if limited:
            return limited

    form = CancellationDeclarationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        contract_reference = form.cleaned_data['contract_reference'].strip()
        requested_end_date = form.cleaned_data.get('requested_end_date')
        if requested_end_date is None:
            requested_end_date = _resolve_consumer_contract_end(
                email,
                contract_reference,
            )
        declaration = ConsumerContractDeclaration.objects.create(
            kind='cancellation',
            cancellation_kind=form.cleaned_data['cancellation_kind'],
            name=form.cleaned_data['name'].strip(),
            email=email,
            contract_reference=contract_reference,
            requested_end_date=requested_end_date,
            reason=(form.cleaned_data.get('reason') or '').strip(),
            request_meta={'source': 'public_web'},
        )
        submitted = timezone.localtime(declaration.submitted_at).strftime('%d.%m.%Y %H:%M:%S %Z')
        requested_end = (
            declaration.requested_end_date.strftime('%d.%m.%Y')
            if declaration.requested_end_date
            else 'zum frühestmöglichen Zeitpunkt'
        )
        queue_email(
            'cancellation_received',
            declaration.email,
            {
                'name': declaration.name,
                'contract_reference': declaration.contract_reference,
                'submitted_at': submitted,
                'declaration_id': str(declaration.id),
                'cancellation_kind': declaration.get_cancellation_kind_display(),
                'requested_end_date': requested_end,
                'reason': declaration.reason or '–',
            },
        )
        return render(
            request,
            'legal_action_success.html',
            {
                'declaration': declaration,
                'title': 'Kündigung eingegangen',
                'message': 'Ihre Kündigung wurde elektronisch entgegengenommen.',
            },
        )

    return render(
        request,
        'legal_action_form.html',
        {
            'form': form,
            'page_title': 'Verträge hier kündigen',
            'eyebrow': 'KÜNDIGUNGSFUNKTION',
            'intro': (
                'Hier können Verbraucher einen über PromptMaster geschlossenen '
                'Laufzeitvertrag ordentlich oder außerordentlich kündigen.'
            ),
            'notice': (
                'Wenn Sie keinen Beendigungszeitpunkt angeben, behandeln wir die '
                'Kündigung als Erklärung zum frühestmöglichen Zeitpunkt.'
            ),
            'submit_label': 'jetzt kündigen',
        },
    )

def checkout_csrf(request):
    """Issue a CSRF token for the static public checkout page."""
    if request.method != 'GET':
        return HttpResponse(status=405)
    from django.middleware.csrf import get_token

    response = JsonResponse({'csrfToken': get_token(request)})
    response['Cache-Control'] = 'no-store'
    return response


def public_checkout_start(request):
    """Create a new customer/order and hand the browser to Mollie.

    GET /checkout/ remains the static marketing surface. Only this same-origin
    POST endpoint mutates customer, order and payment state.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    import secrets
    from urllib.parse import urlencode

    from django.contrib import messages
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction
    from django.urls import reverse
    from django.utils import timezone

    from apps.catalog.models import Product
    from apps.companies.models import Company, Membership, PrivateCustomerProfile
    from apps.core.security import check_rate, client_ip
    from apps.legal.models import LegalAcceptance, LegalDocument
    from apps.orders.forms import PublicCheckoutForm
    from apps.orders.services import MAX_PURCHASE_QUANTITY, create_order
    from apps.payments.mollie import MollieClient, MollieError
    from apps.payments.models import Payment

    limited = check_rate(request, 'public-checkout', 10, 3600)
    if limited:
        return limited

    form = PublicCheckoutForm(request.POST)
    try:
        fallback_quantity = int(request.POST.get('quantity') or 1)
    except (TypeError, ValueError):
        fallback_quantity = 1
    fallback_quantity = max(1, min(MAX_PURCHASE_QUANTITY, fallback_quantity))

    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('ns_admin:dashboard')
        return redirect(
            f"{reverse('portal:buy')}?{urlencode({'quantity': fallback_quantity})}"
        )

    if not form.is_valid():
        return redirect(
            f"/checkout/?{urlencode({'quantity': fallback_quantity, 'error': 'invalid'})}"
        )

    data = form.cleaned_data
    quantity = data['quantity']
    User = get_user_model()
    existing = User.objects.filter(email__iexact=data['email']).first()
    if existing:
        # A customer can leave Mollie and return to the public checkout before
        # the post-payment activation mail has established a usable password.
        # Sending that placeholder account to the normal login would dead-end
        # the purchase. Resume the still-open provider checkout instead, and
        # fall back to password recovery only when the prior provider attempt
        # is no longer resumable.
        from django.db.models import Q
        from apps.orders.models import Order

        public_orders = (
            Order.objects.filter(billing_snapshot__source='public_checkout')
            .filter(
                Q(private_user=existing)
                | Q(
                    company__memberships__user=existing,
                    company__memberships__active=True,
                )
            )
            .distinct()
        )
        if not existing.has_usable_password() and public_orders.exists():
            resumable = (
                Payment.objects.filter(
                    order__in=public_orders,
                    status__in={'created', 'open', 'pending', 'authorized'},
                )
                .order_by('-created_at')
                .first()
            )
            checkout_url = ''
            if resumable:
                checkout_url = (
                    (((resumable.last_provider_payload or {}).get('_links') or {})
                     .get('checkout') or {})
                    .get('href') or ''
                ).strip()
            if checkout_url.startswith('https://'):
                return redirect(checkout_url)

            if public_orders.filter(status='paid').exists():
                return redirect('/checkout/success/?state=paid')

            messages.info(
                request,
                'Für diese E-Mail-Adresse besteht bereits ein noch nicht aktiviertes '
                'PromptMaster-Konto. Bitte setzen Sie zuerst Ihr Passwort zurück.',
            )
            return redirect(
                f"{reverse('accounts:password_reset')}?{urlencode({'checkout': 1})}"
            )

        messages.info(
            request,
            'Für diese E-Mail-Adresse besteht bereits ein PromptMaster-Konto. Bitte anmelden.',
        )
        next_url = f"{reverse('portal:buy')}?{urlencode({'quantity': quantity})}"
        return redirect(
            f"{reverse('accounts:login')}?{urlencode({'next': next_url})}"
        )

    private_customer = data['customer_type'] == 'private'
    required_docs = ['terms', 'privacy', 'license'] + (['withdrawal'] if private_customer else [])
    now = timezone.now()
    documents = {}
    for doc_type in required_docs:
        document = (
            LegalDocument.objects.filter(
                doc_type=doc_type,
                active=True,
                valid_from__lte=now,
            )
            .order_by('-valid_from')
            .first()
        )
        if not document:
            return redirect(
                f"/checkout/?{urlencode({'quantity': quantity, 'error': 'unavailable'})}"
            )
        documents[doc_type] = document

    product = Product.objects.filter(
        code='PRO',
        active=True,
        purchasable=True,
    ).first()
    if not product:
        return redirect(
            f"/checkout/?{urlencode({'quantity': quantity, 'error': 'unavailable'})}"
        )

    checkout_key = request.session.get('public_checkout_key')
    if not checkout_key:
        checkout_key = secrets.token_urlsafe(24)
        request.session['public_checkout_key'] = checkout_key

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=data['email'],
                password=None,
                first_name=data['first_name'].strip(),
                last_name=data['last_name'].strip(),
                two_factor_required=(data['customer_type'] == 'company'),
            )

            if data['customer_type'] == 'company':
                company = Company.objects.create(
                    customer_number=f'C-{user.id.hex[:24].upper()}',
                    name=data['company_name'].strip(),
                    legal_form=data['legal_form'].strip(),
                    email=user.email,
                    phone=data['phone'].strip(),
                    street=data['street'].strip(),
                    house_number=data['house_number'].strip(),
                    postal_code=data['postal_code'].strip(),
                    city=data['city'].strip(),
                    country=data['country'],
                    vat_id=data['vat_id'].strip(),
                    tax_number=data['tax_number'].strip(),
                )
                Membership.objects.create(
                    company=company,
                    user=user,
                    role='admin',
                    active=True,
                )
            else:
                PrivateCustomerProfile.objects.create(
                    user=user,
                    customer_number=f'P-{user.id.hex[:24].upper()}',
                    phone=data['phone'].strip(),
                    street=data['street'].strip(),
                    house_number=data['house_number'].strip(),
                    postal_code=data['postal_code'].strip(),
                    city=data['city'].strip(),
                    country=data['country'],
                )

            evidence = {
                'source': 'public_checkout',
                'ip': client_ip(request),
                'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:300],
                'early_performance_requested': bool(
                    private_customer and data.get('request_early_performance')
                ),
            }
            for doc_type in ('terms', 'privacy'):
                LegalAcceptance.objects.create(
                    user=user,
                    document=documents[doc_type],
                    order=None,
                    evidence=evidence,
                )

            order = create_order(
                user=user,
                product=product,
                quantity=quantity,
                idempotency_key=checkout_key,
            )
            snapshot = dict(order.billing_snapshot or {})
            snapshot['source'] = 'public_checkout'
            snapshot['legal_versions'] = {
                doc_type: document.version
                for doc_type, document in documents.items()
            }
            if private_customer:
                snapshot['early_performance_requested'] = bool(
                    data.get('request_early_performance')
                )
            order.billing_snapshot = snapshot
            order.save(update_fields=['billing_snapshot', 'updated_at'])

            for document in documents.values():
                LegalAcceptance.objects.create(
                    user=user,
                    document=document,
                    order=order,
                    evidence=evidence,
                )

            payload = MollieClient().create_payment(
                amount=order.gross_total,
                currency=order.currency,
                description=f'PromptMaster {order.order_number}',
                redirect_url=request.build_absolute_uri('/checkout/success/'),
                webhook_url=request.build_absolute_uri(
                    reverse('payments:mollie_webhook')
                ),
                metadata={'order_id': str(order.id)},
                idempotency_key=order.idempotency_key,
            )
            payment_id = str(payload.get('id') or '')[:100]
            checkout_url = (
                (((payload.get('_links') or {}).get('checkout') or {}).get('href') or '')
                .strip()
            )
            if not payment_id or not checkout_url.startswith('https://'):
                raise MollieError(
                    'Mollie response is missing payment ID or secure checkout URL'
                )

            Payment.objects.create(
                provider_payment_id=payment_id,
                order=order,
                status=str(payload.get('status') or 'open')[:40],
                amount=order.gross_total,
                currency=order.currency,
                last_provider_payload=payload,
            )
            order.status = 'payment_open'
            order.save(update_fields=['status', 'updated_at'])
    except IntegrityError:
        messages.info(
            request,
            'Für diese E-Mail-Adresse besteht bereits ein PromptMaster-Konto. Bitte anmelden.',
        )
        next_url = f"{reverse('portal:buy')}?{urlencode({'quantity': quantity})}"
        return redirect(
            f"{reverse('accounts:login')}?{urlencode({'next': next_url})}"
        )
    except (ValidationError, MollieError):
        return redirect(
            f"/checkout/?{urlencode({'quantity': quantity, 'error': 'payment'})}"
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception('Public checkout failed')
        return redirect(
            f"/checkout/?{urlencode({'quantity': quantity, 'error': 'payment'})}"
        )

    request.session['public_checkout_key'] = secrets.token_urlsafe(24)
    return redirect(checkout_url)


def public_catalog(request):
    """Public, non-sensitive product metadata used by the marketing frontend.

    Browser-visible prices are display-only. Checkout always recalculates from
    ProductPrice server-side before creating an order.
    """
    from decimal import Decimal, ROUND_HALF_UP
    from django.utils import timezone
    from apps.catalog.models import Product, TaxRule
    from apps.catalog.services import current_price
    from apps.orders.services import MAX_PURCHASE_QUANTITY
    from apps.prompts.models import PromptApplication

    now = timezone.now()
    pro = Product.objects.filter(code='PRO', active=True, visible=True).first()
    free = Product.objects.filter(code='FREE', active=True, visible=True).first()
    pro_price = current_price(pro, 'new', now) if pro else None
    annual_gross = pro_price.gross_amount if pro_price else Decimal('35.88')
    monthly_gross = (annual_gross / Decimal('12')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    company_tax = TaxRule.objects.filter(
        country='DE',
        customer_type='company',
        active=True,
    ).first()
    private_tax = TaxRule.objects.filter(
        country='DE',
        customer_type='private',
        active=True,
    ).first()
    display_tax = private_tax or company_tax
    tax_basis_points = int(
        (display_tax.tax_rate if display_tax else Decimal('19.00')) * 100
    )
    applications = list(
        PromptApplication.objects.filter(active=True).order_by('sort_order', 'name').values_list('name', flat=True)
    )

    def cents(value):
        return int((Decimal(value) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    response = JsonResponse({
        'currency': pro_price.currency if pro_price else 'EUR',
        'priceBasis': 'gross',
        'taxBasisPoints': tax_basis_points,
        'market': 'DE',
        'products': [
            {'id': 'PROMPTMASTER_FREE', 'monthlyGrossCents': 0, 'annualGrossCents': 0, 'termDays': 0, 'active': bool(free)},
            {
                'id': 'PROMPTMASTER_PRO',
                'monthlyGrossCents': cents(monthly_gross),
                'annualGrossCents': cents(annual_gross),
                'termDays': int(pro.default_license_days) if pro else 0,
                'active': bool(pro),
                'purchasable': bool(pro and pro.purchasable),
            },
        ],
        'maxQuantity': MAX_PURCHASE_QUANTITY,
        'checkoutEnabled': bool(pro and pro.purchasable and pro_price),
        'companyRequireVatId': bool(company_tax and company_tax.require_vat_id),
        'companyRequireTaxNumber': bool(
            company_tax and company_tax.require_tax_number
        ),
        'loginEnabled': True,
        'freeUrl': '/free/',
        'proApplicationCount': len(applications),
        'proApplicationNames': applications,
        'generatedAt': now.isoformat(),
    })
    response['Cache-Control'] = 'no-store'
    return response
