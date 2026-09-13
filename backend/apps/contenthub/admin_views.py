from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.audit.services import audit
from apps.core.permissions import has_perm

from .forms import FAQEntryForm
from .models import FAQEntry


def content_perm(code='content.read'):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.is_staff or not has_perm(request.user, code):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return deco


@content_perm('content.read')
def faq_list(request):
    q = (request.GET.get('q') or '').strip()
    audience = (request.GET.get('audience') or '').strip()
    rows = FAQEntry.objects.all()
    if q:
        rows = rows.filter(question__icontains=q)
    if audience:
        rows = rows.filter(audience=audience)
    return render(
        request,
        'ns_admin/content/faq_list.html',
        {'rows': rows, 'q': q, 'audience': audience, 'audiences': FAQEntry.AUDIENCE},
    )


@content_perm('content.write')
def faq_edit(request, pk=None):
    faq = get_object_or_404(FAQEntry, pk=pk) if pk else FAQEntry()
    form = FAQEntryForm(request.POST or None, instance=faq)
    if request.method == 'POST' and form.is_valid():
        faq = form.save()
        audit(
            request.user,
            'content.faq.saved',
            faq,
            {'key': faq.key, 'active': faq.active, 'audience': faq.audience},
            request=request,
        )
        messages.success(request, 'FAQ gespeichert.')
        return redirect('content_admin:faqs')
    return render(request, 'ns_admin/content/faq_edit.html', {'form': form, 'faq': faq if faq.pk else None})


@content_perm('content.write')
def faq_toggle(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    faq = get_object_or_404(FAQEntry, pk=pk)
    faq.active = not faq.active
    faq.save(update_fields=['active', 'updated_at'])
    audit(request.user, 'content.faq.toggled', faq, {'active': faq.active}, request=request)
    messages.success(request, 'FAQ-Status geändert.')
    return redirect('content_admin:faqs')
