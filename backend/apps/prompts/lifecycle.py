from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.audit.services import audit

from .composer_core import PromptValidationError
from .models import PromptDefinition, PromptField, PromptOption, PromptTestCase, PromptVersion
from .services import compose_version


TRANSITIONS = {
    'DRAFT': {'TEST'},
    'TEST': {'DRAFT', 'REVIEW'},
    'REVIEW': {'DRAFT', 'APPROVED'},
    'APPROVED': {'DRAFT', 'PUBLISHED'},
    'PUBLISHED': {'ARCHIVED'},
    'ARCHIVED': set(),
}


@dataclass(frozen=True)
class TestRunSummary:
    total: int
    passed: int
    failed: int
    errors: int

    @property
    def ok(self):
        return self.total > 0 and self.passed == self.total


def clone_as_draft(definition: PromptDefinition, actor=None, request=None, source: PromptVersion | None = None):
    source = source or definition.versions.order_by('-version').first()
    if not source:
        raise ValidationError('Für diese PromptDefinition existiert keine Quellversion.')

    with transaction.atomic():
        locked = PromptDefinition.objects.select_for_update().get(pk=definition.pk)
        next_version = (locked.versions.aggregate(v=Max('version'))['v'] or 0) + 1
        draft = PromptVersion.objects.create(
            definition=locked,
            policy_set=source.policy_set,
            version=next_version,
            lifecycle='DRAFT',
            title=source.title,
            area=source.area,
            family=source.family,
            intent=source.intent,
            access=source.access,
            product_status=source.product_status,
            max_chars=source.max_chars,
            context_template=source.context_template,
            app_rule_snapshot=source.app_rule_snapshot,
            source_sha256=source.source_sha256,
            published_at=None,
        )
        for field in source.fields.order_by('kind', 'sort_order'):
            PromptField.objects.create(
                version=draft,
                label=field.label,
                kind=field.kind,
                sort_order=field.sort_order,
                optional_fragment=field.optional_fragment,
            )
        for option in source.options.order_by('kind', 'sort_order'):
            PromptOption.objects.create(
                version=draft,
                kind=option.kind,
                value=option.value,
                label=option.label,
                sort_order=option.sort_order,
            )
        for case in source.test_cases.filter(enabled=True).order_by('sort_order', 'name'):
            PromptTestCase.objects.create(
                version=draft,
                name=case.name,
                input_payload=case.input_payload,
                expected_contains=case.expected_contains,
                expected_not_contains=case.expected_not_contains,
                enabled=True,
                sort_order=case.sort_order,
            )
        if actor is not None:
            audit(actor, 'prompt.version.draft_created', draft, {'source_version': source.version}, request=request)
        return draft


def _test_case_payload(case: PromptTestCase):
    data = dict(case.input_payload or {})
    tier = data.pop('microsoft_tier', 'premium')
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else data
    return tier, payload


def run_test_case(case: PromptTestCase):
    now = timezone.now()
    try:
        tier, payload = _test_case_payload(case)
        result = compose_version(version=case.version, microsoft_tier=tier, payload=payload)
        prompt = result.prompt
        missing = [str(value) for value in (case.expected_contains or []) if str(value) not in prompt]
        forbidden = [str(value) for value in (case.expected_not_contains or []) if str(value) in prompt]
        if missing or forbidden:
            bits = []
            if missing:
                bits.append('Fehlt: ' + ', '.join(missing))
            if forbidden:
                bits.append('Unerwartet enthalten: ' + ', '.join(forbidden))
            case.last_status = 'FAILED'
            case.last_error = '; '.join(bits)
        else:
            case.last_status = 'PASSED'
            case.last_error = ''
    except (PromptValidationError, ValidationError, ValueError, TypeError) as exc:
        case.last_status = 'ERROR'
        case.last_error = str(exc)[:4000]
    case.last_run_at = now
    case.save(update_fields=['last_status', 'last_error', 'last_run_at', 'updated_at'])
    return case.last_status


def run_version_tests(version: PromptVersion):
    cases = list(version.test_cases.filter(enabled=True).order_by('sort_order', 'name'))
    passed = failed = errors = 0
    for case in cases:
        state = run_test_case(case)
        if state == 'PASSED':
            passed += 1
        elif state == 'FAILED':
            failed += 1
        else:
            errors += 1
    return TestRunSummary(total=len(cases), passed=passed, failed=failed, errors=errors)


def _validate_transition(version: PromptVersion, target: str):
    if target not in dict(PromptVersion.LIFECYCLE):
        raise ValidationError('Unbekannter Lifecycle-Status.')
    if target not in TRANSITIONS.get(version.lifecycle, set()):
        raise ValidationError(f'Übergang {version.lifecycle} → {target} ist nicht erlaubt.')

    if version.lifecycle == 'DRAFT' and target == 'TEST':
        if not version.test_cases.filter(enabled=True).exists():
            raise ValidationError('Vor TEST muss mindestens ein aktiver Prompt-Testfall existieren.')

    if version.lifecycle == 'TEST' and target == 'REVIEW':
        summary = run_version_tests(version)
        if not summary.ok:
            raise ValidationError(
                f'REVIEW blockiert: Testfälle {summary.passed}/{summary.total} bestanden, '
                f'{summary.failed} fehlgeschlagen, {summary.errors} Fehler.'
            )

    if version.lifecycle == 'APPROVED' and target == 'PUBLISHED':
        summary = run_version_tests(version)
        if not summary.ok:
            raise ValidationError('PUBLISH blockiert: alle aktiven Testfälle müssen unmittelbar zuvor bestehen.')


def transition(version: PromptVersion, target: str, actor=None, request=None):
    target = str(target or '').upper()
    with transaction.atomic():
        locked = PromptVersion.objects.select_for_update().select_related('definition').get(pk=version.pk)
        _validate_transition(locked, target)
        previous = locked.lifecycle

        if target == 'PUBLISHED':
            PromptVersion.objects.select_for_update().filter(
                definition=locked.definition,
                lifecycle='PUBLISHED',
            ).exclude(pk=locked.pk).update(lifecycle='ARCHIVED', updated_at=timezone.now())
            locked.published_at = timezone.now()
        elif previous == 'PUBLISHED' and target == 'ARCHIVED':
            # published_at stays as historical evidence
            pass
        else:
            if target != 'PUBLISHED':
                locked.published_at = None

        locked.lifecycle = target
        locked.save(update_fields=['lifecycle', 'published_at', 'updated_at'])
        if actor is not None:
            audit(
                actor,
                'prompt.version.lifecycle',
                locked,
                {'from': previous, 'to': target},
                request=request,
            )
        return locked
