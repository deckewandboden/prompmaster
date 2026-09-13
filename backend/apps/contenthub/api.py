from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import FAQEntry


@require_GET
def faq_list(request):
    audience = (request.GET.get('audience') or 'public').strip().lower()
    allowed = {value for value, _ in FAQEntry.AUDIENCE}
    if audience not in allowed:
        return JsonResponse({'detail': 'invalid_audience'}, status=400)
    rows = list(
        FAQEntry.objects.filter(active=True, audience=audience)
        .order_by('sort_order', 'question')
        .values('key', 'question', 'answer', 'audience', 'sort_order')
    )
    response = JsonResponse({'count': len(rows), 'results': rows}, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
