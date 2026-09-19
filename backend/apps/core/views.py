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
    tax = TaxRule.objects.filter(country='DE', active=True).order_by('customer_type').first()
    tax_basis_points = int((tax.tax_rate if tax else Decimal('19.00')) * 100)
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
            {'id': 'PROMPTMASTER_FREE', 'monthlyGrossCents': 0, 'termMonths': 0, 'active': bool(free)},
            {
                'id': 'PROMPTMASTER_PRO',
                'monthlyGrossCents': cents(monthly_gross),
                'annualGrossCents': cents(annual_gross),
                'termMonths': 12,
                'active': bool(pro),
                'purchasable': bool(pro and pro.purchasable),
            },
        ],
        'maxQuantity': MAX_PURCHASE_QUANTITY,
        'checkoutEnabled': bool(pro and pro.purchasable),
        'loginEnabled': True,
        'freeUrl': '/free/',
        'proApplicationCount': len(applications),
        'proApplicationNames': applications,
        'generatedAt': now.isoformat(),
    })
    response['Cache-Control'] = 'no-store'
    return response
