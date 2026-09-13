"""Pure prompt composition logic.

This module deliberately has no Django imports. The server-side composer is
stateless: prompt inputs and generated prompt text are returned to the caller
and are not persisted by this layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


CONTEXT_AUDIENCE_LABELS = {'Zielgruppe', 'Publikum', 'Empfängerrolle'}
DEFAULT_NO_FABRICATION_RULE = (
    'Erfinde keine Fakten, Zahlen, Termine, Personen, Verantwortlichkeiten, Quellen oder Zusagen; '
    'wenn eine notwendige Information fehlt, benenne die konkrete Lücke statt sie stillschweigend zu ergänzen.'
)


class PromptValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None, code: str = 'invalid'):
        super().__init__(message)
        self.field = field
        self.code = code


@dataclass(frozen=True)
class ComposeResult:
    prompt: str
    ready: bool
    progress_percent: int
    task_id: str
    app_code: str
    policy_version: int
    prompt_version: int


def _clean(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _strip_terminal_punctuation(value: str) -> str:
    return re.sub(r'[.!?]+$', '', value.strip())


def _fill_template(template: str, values: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0)).strip()

    return re.sub(r'\{([^}]+)\}', repl, template or '')


def _task_has_own_audience(fields: list[dict[str, Any]]) -> bool:
    return any(str(field.get('label', '')) in CONTEXT_AUDIENCE_LABELS for field in fields)


def _task_context_sentence(context_template: str, fields: list[dict[str, Any]], values: dict[str, str]) -> str:
    """Render the task-specific context sentence.

    The approved PM20 asset contains handcrafted context templates for 80 of
    194 tasks.  For those tasks we preserve the browser Golden-Master wording
    exactly.  Later PM20 tasks still define concrete required/optional fields
    but have no TASK_CONTEXT_SPEC entry in the asset.  Silently dropping those
    user values would make the server composer unusable, so the central domain
    uses a deterministic, non-inventive fallback that carries every supplied
    field into the prompt.  This fallback never fabricates values and is
    intentionally obvious in parity tests/documentation.
    """
    if not any(values.values()):
        return ''

    if context_template:
        sentence = _fill_template(context_template, values)
        for field in fields:
            if field.get('kind') != 'optional':
                continue
            value = _clean(values.get(str(field.get('label', '')), ''))
            fragment = str(field.get('optional_fragment', '') or '')
            if value and fragment:
                sentence += _fill_template(fragment, {'value': value})
        sentence = _strip_terminal_punctuation(_clean(sentence))
        return f'{sentence}.' if sentence else ''

    supplied: list[str] = []
    for field in fields:
        label = str(field.get('label', '')).strip()
        value = _clean(values.get(label, ''))
        if label and value:
            supplied.append(f'{label}: „{value}“')
    return ('Berücksichtige dabei diese konkreten Angaben: ' + '; '.join(supplied) + '.') if supplied else ''


def _fit_compact(value: str, max_chars: int) -> str:
    value = _clean(value)
    if len(value) <= max_chars:
        return value
    shortened = value[: max_chars - 1]
    shortened = re.sub(r'[,;:\s]+$', '', shortened)
    return shortened + '…'


def _option_values(options: list[dict[str, Any]], kind: str) -> list[str]:
    return [str(item['value']) for item in options if item.get('kind') == kind]


def _validate_choice(value: str, allowed: list[str], field: str) -> str:
    if not allowed:
        return ''
    if value not in allowed:
        raise PromptValidationError(
            f'Ungültiger Wert für {field}. Erlaubt: {", ".join(allowed)}',
            field=field,
            code='choice',
        )
    return value


def compose_prompt(spec: dict[str, Any], payload: dict[str, Any]) -> ComposeResult:
    """Compose a PromptMaster prompt from a versioned catalog specification.

    `spec` is produced by the Django service layer from PromptDefinition,
    PromptVersion, PromptField, PromptOption, MicrosoftCapability and the active
    PromptPolicySet. No input or generated prompt is persisted here.
    """
    app = spec['application']
    version = spec['version']
    policy = spec['policy']
    fields = list(version.get('fields', []))
    options = list(version.get('options', []))

    tier_rank = int(payload.get('microsoft_tier_rank', 0))
    required_tier = max(int(app.get('minimum_tier_rank', 0)), int(version.get('minimum_tier_rank', 0)))
    if tier_rank < required_tier:
        raise PromptValidationError(
            f'Microsoft-Copilot-Stufe nicht ausreichend. Benötigter Rang: {required_tier}.',
            field='microsoft_tier',
            code='tier_required',
        )

    raw_fields = payload.get('fields') or {}
    if not isinstance(raw_fields, dict):
        raise PromptValidationError('fields muss ein Objekt sein.', field='fields')
    values = {str(k): _clean(v) for k, v in raw_fields.items()}

    required_fields = [field for field in fields if field.get('kind') == 'required']
    for field in required_fields:
        label = str(field.get('label', ''))
        if not values.get(label):
            raise PromptValidationError(f'Pflichtfeld fehlt: {label}', field=label, code='required')

    audiences = _option_values(options, 'audience')
    focuses_allowed = _option_values(options, 'focus')
    outputs = _option_values(options, 'output')
    sources = _option_values(options, 'source')

    own_audience = _task_has_own_audience(fields)
    audience = _clean(payload.get('audience'))
    if not own_audience:
        if not audience and audiences:
            audience = audiences[0]
        if audiences:
            _validate_choice(audience, audiences, 'audience')
        if not audience:
            raise PromptValidationError('Zielgruppe fehlt.', field='audience', code='required')

    focus = payload.get('focus')
    if focus is None:
        focus = focuses_allowed[:2]
    if not isinstance(focus, list):
        raise PromptValidationError('focus muss eine Liste sein.', field='focus')
    focus = [_clean(item) for item in focus if _clean(item)]
    invalid_focus = [item for item in focus if item not in focuses_allowed]
    if invalid_focus:
        raise PromptValidationError(
            f'Ungültige Schwerpunkte: {", ".join(invalid_focus)}', field='focus', code='choice'
        )

    output = _clean(payload.get('output')) or (outputs[0] if outputs else '')
    source = _clean(payload.get('source')) or (sources[0] if sources else '')
    tone = _clean(payload.get('tone')) or 'professional'
    detail = _clean(payload.get('detail')) or 'standard'

    if outputs:
        _validate_choice(output, outputs, 'output')
    if sources:
        _validate_choice(source, sources, 'source')
    _validate_choice(tone, list((policy.get('tone_rules') or {}).keys()), 'tone')
    _validate_choice(detail, list((policy.get('detail_rules') or {}).keys()), 'detail')

    intent = str(version.get('intent', '')).strip()
    context_sentence = _task_context_sentence(
        str(version.get('context_template', '') or ''), fields, values
    )

    max_chars = version.get('max_chars')
    if max_chars:
        compact = [_strip_terminal_punctuation(intent)]
        if context_sentence:
            compact.append(_strip_terminal_punctuation(context_sentence))
        if focus:
            compact.append('Fokus: ' + ', '.join(focus))
        prompt = _fit_compact('. '.join(compact) + '.', int(max_chars))
    else:
        paragraphs = [intent]
        if context_sentence:
            paragraphs.append(context_sentence)

        family = str(version.get('family', 'analysis'))
        method_steps = (policy.get('method_rules') or {}).get(family) or (policy.get('method_rules') or {}).get('analysis', [])
        paragraphs.append('Arbeite dabei in folgender Reihenfolge: ' + ' '.join(method_steps))

        if focus:
            paragraphs.append('Lege besonderes Augenmerk auf ' + ', '.join(focus) + '.')

        if not own_audience and audience:
            paragraphs.append(f'Richte die Darstellung auf „{audience}“ aus.')

        detail_text = (policy.get('detail_rules') or {}).get(detail, detail)
        tone_text = (policy.get('tone_rules') or {}).get(tone, tone)
        paragraphs.append(
            f'Liefere das Ergebnis im Format „{output}“. Gestalte die Antwort {detail_text} und {tone_text}.'
        )

        source_instruction = (policy.get('source_instructions') or {}).get(source, source)
        paragraphs.append('Verwende als Informationsgrundlage ' + source_instruction + '.')

        paragraphs.append(f'Für {app["name"]} gilt dabei: {app.get("rule", "")}')

        quality = (policy.get('quality_rules') or {}).get(family) or (policy.get('quality_rules') or {}).get('analysis', '')
        no_fabrication = policy.get('no_fabrication_rule') or DEFAULT_NO_FABRICATION_RULE
        paragraphs.append('Führe abschließend diese Qualitätsprüfung durch: ' + quality + ' ' + no_fabrication)
        prompt = '\n\n'.join(paragraphs)

    steps = [True, True]
    steps.extend(bool(values.get(str(field.get('label', '')))) for field in required_fields)
    if not own_audience:
        steps.append(bool(audience))
    steps.extend([bool(focus), bool(detail), bool(output), bool(tone)])
    progress = int((100 * sum(1 for item in steps if item) / len(steps)) + 0.5) if steps else 0

    return ComposeResult(
        prompt=prompt,
        ready=True,
        progress_percent=progress,
        task_id=str(spec['task_id']),
        app_code=str(app['code']),
        policy_version=int(policy.get('version', 1)),
        prompt_version=int(version.get('version', 1)),
    )
