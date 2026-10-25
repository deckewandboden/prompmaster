"""Product-admin governance for reviewed legal translations (Issue #87).

This is deliberately independent of the development-only Django admin.
The public release flag is never modified from this module.
"""
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.audit.services import audit as write_audit
from apps.core.admin_views import staff_perm
from apps.core.permissions import has_perm
from apps.legal.models import LegalDocument, LegalDocumentTranslation


class TranslationDraftForm(forms.ModelForm):
    class Meta:
        model = LegalDocumentTranslation
        fields = ('document', 'language', 'content')
        labels = {
            'document': _('Deutsche Originalversion'),
            'language': _('Sprache'),
            'content': _('Übersetzung (noch nicht freigegeben)'),
        }
        widgets = {'content': forms.Textarea(attrs={'rows': 18})}


@staff_perm('legal.read')
def translation_list(request):
    entries = (
        LegalDocumentTranslation.objects.select_related(
            'document', 'approved_by', 'submitted_by',
        )
        .order_by('document__doc_type', 'document__version', 'language')
    )
    return render(request, 'ns_admin/legal_translations.html', {
        'translations': entries,
        'can_edit': has_perm(request.user, 'legal.write'),
        'publication_enabled': settings.LEGAL_TRANSLATIONS_PUBLIC_ENABLED,
    })


@staff_perm('legal.read')
def translation_detail(request, pk):
    item = get_object_or_404(
        LegalDocumentTranslation.objects.select_related(
            'document', 'submitted_by', 'approved_by',
        ), pk=pk,
    )
    return render(request, 'ns_admin/legal_translation_detail.html', {
        'translation': item,
        'can_edit': has_perm(request.user, 'legal.write'),
        'can_approve': has_perm(request.user, 'legal.approve')
                       and item.submitted_by_id != request.user.pk,
        'is_publishable': item.is_publishable(),
    })


@staff_perm('legal.write')
def translation_edit(request, pk=None):
    if pk is not None:
        item = get_object_or_404(LegalDocumentTranslation, pk=pk)
        if item.status != 'draft':
            raise PermissionDenied
    else:
        item = None
    form = TranslationDraftForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                if item:
                    # The existing draft may have changed while a form was open.
                    current = LegalDocumentTranslation.objects.select_for_update().get(pk=item.pk)
                    if current.status != 'draft':
                        raise ValidationError(_('Nur Entwürfe dürfen bearbeitet werden.'))
                    changed = form.save(commit=False)
                    current.document = changed.document
                    current.language = changed.language
                    current.content = changed.content
                    current.save()
                    item = current
                else:
                    item = form.save()
                write_audit(
                    request.user, 'legal.translation_draft_saved', item, {
                        'document_id': str(item.document_id),
                        'language': item.language,
                        'content_sha256': item.fingerprint(item.content),
                    }, request=request,
                )
            messages.success(request, _('Übersetzungsentwurf gespeichert.'))
            return redirect('ns_admin:legal_translation_detail', pk=item.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'ns_admin/form.html', {
        'title': _('Übersetzungsentwurf bearbeiten') if item else _('Übersetzungsentwurf anlegen'),
        'form': form,
        'cancel_url': reverse('ns_admin:legal_translations'),
    })


def _transition(request, pk, event):
    with transaction.atomic():
        item = get_object_or_404(
            LegalDocumentTranslation.objects.select_for_update(), pk=pk,
        )
        # The fingerprint is bound to the locked original at transition time.
        LegalDocument.objects.select_for_update().get(pk=item.document_id)
        old_status = item.status
        if event == 'submit':
            if item.status != 'draft':
                raise ValidationError(_('Nur Entwürfe können eingereicht werden.'))
            item.submitted_by = request.user
            item.status = 'review'
            item.save()
        elif event == 'draft':
            if item.status != 'review':
                raise ValidationError(_('Nur Prüfversionen können zurückgesetzt werden.'))
            item.status = 'draft'
            item.submitted_by = None
            item.save()
        elif event == 'approve':
            if item.status != 'review':
                raise ValidationError(_('Nur geprüfte Fassungen können freigegeben werden.'))
            item.approve(
                reviewer=request.user,
                reference=(request.POST.get('approval_reference') or '').strip()[:240],
            )
        else:
            raise PermissionDenied
        write_audit(request.user, 'legal.translation_' + event, item, {
            'document_id': str(item.document_id),
            'language': item.language,
            'from': old_status,
            'to': item.status,
            'source_sha256': item.source_sha256,
            'content_sha256': item.content_sha256,
            'approval_reference': item.approval_reference if event == 'approve' else '',
        }, request=request)
    return item


@staff_perm('legal.write')
@require_POST
def translation_submit(request, pk):
    try:
        _transition(request, pk, 'submit')
        messages.success(request, _('Sprachfassung zur Prüfung eingereicht.'))
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect('ns_admin:legal_translation_detail', pk=pk)


@staff_perm('legal.write')
@require_POST
def translation_return_to_draft(request, pk):
    try:
        _transition(request, pk, 'draft')
        messages.success(request, _('Sprachfassung wieder als Entwurf markiert.'))
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect('ns_admin:legal_translation_detail', pk=pk)


@staff_perm('legal.approve')
@require_POST
def translation_approve(request, pk):
    try:
        _transition(request, pk, 'approve')
        messages.success(request, _('Fachlich geprüfte Sprachfassung freigegeben.'))
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect('ns_admin:legal_translation_detail', pk=pk)
