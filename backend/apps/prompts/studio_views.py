from __future__ import annotations

import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.audit.services import audit
from apps.core.permissions import has_perm

from .composer_core import PromptValidationError
from .forms import PromptPreviewForm, PromptQualityPolicyForm, PromptTestCaseForm, PromptVersionEditorForm
from .lifecycle import clone_as_draft, run_test_case, run_version_tests, transition
from .models import (
    PromptDefinition,
    PromptQualityPolicy,
    PromptQualitySnapshot,
    PromptTestCase,
    PromptVersion,
)
from .quality import active_quality_policy, analyze_all_published, quality_tasks
from .services import build_spec_for_version, compose_version


def studio_perm(code='prompts.read'):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.is_staff or not has_perm(request.user, code):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return deco


def _latest_quality(definition):
    return definition.quality_snapshots.order_by('-calculated_at').first()


@studio_perm('prompts.read')
def index(request):
    q = (request.GET.get('q') or '').strip()
    qs = PromptDefinition.objects.filter(active=True).select_related('application').prefetch_related('versions')
    if q:
        qs = qs.filter(
            Q(task_id__icontains=q)
            | Q(application__name__icontains=q)
            | Q(versions__title__icontains=q)
        ).distinct()
    rows = []
    for definition in qs.order_by('application__sort_order', 'task_id'):
        published = next((v for v in definition.versions.all() if v.lifecycle == 'PUBLISHED'), None)
        draft_count = sum(1 for v in definition.versions.all() if v.lifecycle in {'DRAFT', 'TEST', 'REVIEW', 'APPROVED'})
        rows.append({
            'definition': definition,
            'published': published,
            'draft_count': draft_count,
            'quality': _latest_quality(definition),
        })
    return render(request, 'ns_admin/prompt_studio/index.html', {'rows': rows, 'q': q})


@studio_perm('prompts.read')
def definition_detail(request, task_id):
    definition = get_object_or_404(PromptDefinition.objects.select_related('application'), task_id=task_id)
    versions = list(
        definition.versions.select_related('policy_set')
        .prefetch_related('test_cases', 'ratings')
        .order_by('-version')
    )
    quality = _latest_quality(definition)
    return render(
        request,
        'ns_admin/prompt_studio/definition_detail.html',
        {'definition': definition, 'versions': versions, 'quality': quality},
    )


@studio_perm('prompts.write')
def create_draft(request, task_id):
    if request.method != 'POST':
        raise PermissionDenied
    definition = get_object_or_404(PromptDefinition, task_id=task_id)
    source_id = request.POST.get('source_version')
    source = None
    if source_id:
        source = get_object_or_404(PromptVersion, pk=source_id, definition=definition)
    try:
        draft = clone_as_draft(definition, actor=request.user, request=request, source=source)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('prompt_studio:definition', task_id=task_id)
    messages.success(request, f'DRAFT v{draft.version} wurde erzeugt.')
    return redirect('prompt_studio:version_edit', pk=draft.pk)


@studio_perm('prompts.read')
def version_detail(request, pk):
    version = get_object_or_404(
        PromptVersion.objects.select_related('definition__application', 'policy_set')
        .prefetch_related('fields', 'options', 'test_cases', 'ratings'),
        pk=pk,
    )
    preview_form = PromptPreviewForm(
        initial={
            'microsoft_tier': 'premium',
            'payload_json': json.dumps(_sample_payload(version), ensure_ascii=False, indent=2),
        }
    )
    preview = None
    preview_error = None
    if request.method == 'POST' and request.POST.get('action') == 'preview':
        preview_form = PromptPreviewForm(request.POST)
        if preview_form.is_valid():
            try:
                preview = compose_version(
                    version=version,
                    microsoft_tier=preview_form.cleaned_data['microsoft_tier'],
                    payload=preview_form.cleaned_data['payload_json'],
                )
            except PromptValidationError as exc:
                preview_error = str(exc)
    return render(
        request,
        'ns_admin/prompt_studio/version_detail.html',
        {
            'version': version,
            'preview_form': preview_form,
            'preview': preview,
            'preview_error': preview_error,
            'spec': build_spec_for_version(version),
        },
    )


def _sample_payload(version):
    fields = {}
    for field in version.fields.all().order_by('kind', 'sort_order'):
        if field.kind == 'required':
            fields[field.label] = f'Testwert für {field.label}'
    options = list(version.options.all())
    by_kind = {}
    for option in options:
        by_kind.setdefault(option.kind, []).append(option.value)
    payload = {
        'fields': fields,
        'tone': 'professional',
        'detail': 'standard',
    }
    if by_kind.get('audience'):
        payload['audience'] = by_kind['audience'][0]
    if by_kind.get('focus'):
        payload['focus'] = by_kind['focus'][:2]
    if by_kind.get('output'):
        payload['output'] = by_kind['output'][0]
    if by_kind.get('source'):
        payload['source'] = by_kind['source'][0]
    return payload


@studio_perm('prompts.write')
def version_edit(request, pk):
    version = get_object_or_404(PromptVersion.objects.prefetch_related('fields', 'options'), pk=pk)
    if version.lifecycle != 'DRAFT':
        messages.error(request, 'Nur DRAFT-Versionen dürfen bearbeitet werden.')
        return redirect('prompt_studio:version', pk=pk)
    form = PromptVersionEditorForm(request.POST or None, instance=version)
    if request.method == 'POST' and form.is_valid():
        version = form.save()
        form.save_related_prompt_structure(version)
        audit(
            request.user,
            'prompt.version.edited',
            version,
            {'task_id': version.definition.task_id, 'version': version.version},
            request=request,
        )
        messages.success(request, 'Prompt-Version gespeichert.')
        return redirect('prompt_studio:version', pk=version.pk)
    return render(request, 'ns_admin/prompt_studio/version_edit.html', {'form': form, 'version': version})


@studio_perm('prompts.write')
def lifecycle_action(request, pk, target):
    if request.method != 'POST':
        raise PermissionDenied
    target = str(target or '').upper()
    if target == 'PUBLISHED' and not has_perm(request.user, 'prompts.publish'):
        raise PermissionDenied
    version = get_object_or_404(PromptVersion, pk=pk)
    try:
        version = transition(version, target, actor=request.user, request=request)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'Lifecycle auf {version.lifecycle} gesetzt.')
    return redirect('prompt_studio:version', pk=pk)


@studio_perm('prompts.write')
def run_tests(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    version = get_object_or_404(PromptVersion, pk=pk)
    summary = run_version_tests(version)
    audit(
        request.user,
        'prompt.version.tests_run',
        version,
        {'total': summary.total, 'passed': summary.passed, 'failed': summary.failed, 'errors': summary.errors},
        request=request,
    )
    if summary.ok:
        messages.success(request, f'Alle {summary.total} Testfälle bestanden.')
    else:
        messages.error(
            request,
            f'Tests: {summary.passed}/{summary.total} bestanden, {summary.failed} fehlgeschlagen, {summary.errors} Fehler.',
        )
    return redirect('prompt_studio:version', pk=pk)


@studio_perm('prompts.write')
def test_case_edit(request, version_id, pk=None):
    version = get_object_or_404(PromptVersion, pk=version_id)
    if version.lifecycle not in {'DRAFT', 'TEST'}:
        messages.error(request, 'Testfälle dürfen nur in DRAFT oder TEST bearbeitet werden.')
        return redirect('prompt_studio:version', pk=version.pk)
    case = get_object_or_404(PromptTestCase, pk=pk, version=version) if pk else PromptTestCase(version=version)
    form = PromptTestCaseForm(request.POST or None, instance=case)
    if request.method == 'POST' and form.is_valid():
        case = form.save(commit=False)
        case.version = version
        case.last_status = 'NEVER'
        case.last_error = ''
        case.last_run_at = None
        case.save()
        audit(request.user, 'prompt.testcase.saved', case, {'version': version.version}, request=request)
        messages.success(request, 'Testfall gespeichert.')
        return redirect('prompt_studio:version', pk=version.pk)
    return render(
        request,
        'ns_admin/prompt_studio/testcase_edit.html',
        {'form': form, 'version': version, 'case': case if case.pk else None},
    )


@studio_perm('prompts.write')
def test_case_run(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    case = get_object_or_404(PromptTestCase.objects.select_related('version'), pk=pk)
    state = run_test_case(case)
    audit(request.user, 'prompt.testcase.run', case, {'status': state}, request=request)
    if state == 'PASSED':
        messages.success(request, f'Testfall „{case.name}“ bestanden.')
    else:
        messages.error(request, f'Testfall „{case.name}“: {state} · {case.last_error}')
    return redirect('prompt_studio:version', pk=case.version_id)


@studio_perm('prompts.write')
def test_case_delete(request, pk):
    if request.method != 'POST':
        raise PermissionDenied
    case = get_object_or_404(PromptTestCase.objects.select_related('version'), pk=pk)
    version = case.version
    if version.lifecycle not in {'DRAFT', 'TEST'}:
        messages.error(request, 'Testfälle dürfen in diesem Status nicht gelöscht werden.')
        return redirect('prompt_studio:version', pk=version.pk)
    audit(request.user, 'prompt.testcase.deleted', case, {'name': case.name}, request=request)
    case.delete()
    messages.success(request, 'Testfall gelöscht.')
    return redirect('prompt_studio:version', pk=version.pk)


@studio_perm('prompts.read')
def quality_dashboard(request):
    if request.method == 'POST' and has_perm(request.user, 'prompts.quality'):
        snapshots = analyze_all_published(persist=True)
        messages.success(request, f'Qualitätsanalyse für {len(snapshots)} veröffentlichte Prompt-Versionen aktualisiert.')
        return redirect('prompt_studio:quality')
    rows = list(quality_tasks(limit=250))
    counts = {
        'critical': sum(1 for row in rows if row.status == 'CRITICAL'),
        'warn': sum(1 for row in rows if row.status == 'WARN'),
        'watch': sum(1 for row in rows if row.status == 'WATCH'),
        'ok': sum(1 for row in rows if row.status == 'OK'),
    }
    return render(request, 'ns_admin/prompt_studio/quality.html', {'rows': rows, 'counts': counts})


@studio_perm('prompts.quality')
def quality_policy(request):
    policy = active_quality_policy()
    form = PromptQualityPolicyForm(request.POST or None, instance=policy)
    if request.method == 'POST' and form.is_valid():
        policy = form.save(commit=False)
        policy.active = True
        policy.full_clean()
        policy.save()
        audit(request.user, 'prompt.quality.policy_updated', policy, {}, request=request)
        messages.success(request, 'Qualitätsschwellen gespeichert.')
        return redirect('prompt_studio:quality')
    return render(request, 'ns_admin/prompt_studio/quality_policy.html', {'form': form, 'policy': policy})
