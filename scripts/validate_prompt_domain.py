#!/usr/bin/env python3
"""Static/pure-Python acceptance checks for the central PromptDomain/Composer.

Does not require Django. It validates the frozen PM20 extraction against the
approved Golden Master hashes and executes the pure server composer for all
194 PM20 tasks.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))

from apps.prompts.composer_core import PromptValidationError, compose_prompt  # noqa: E402
from apps.prompts.free_legacy import FREE_RUNTIME_CONTRACTS, compose_free_legacy  # noqa: E402

DATA = BACKEND / 'apps' / 'prompts' / 'data' / 'pm20_golden_logic.json'
FREE_DATA = BACKEND / 'apps' / 'prompts' / 'data' / 'free_legacy_tasks.json'
PRO_GM = BACKEND / 'private_assets' / 'promptmaster_pro.html'
FREE_GM = BACKEND / 'private_assets' / 'promptmaster_free_reference.html'
PRODUCT_PRO_GM = ROOT / 'product' / 'golden_masters' / 'promptmaster_pro.html'
PRODUCT_FREE_GM = ROOT / 'product' / 'golden_masters' / 'promptmaster_free.html'
PRO_SHA = 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf'
FREE_SHA = 'aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8'
AUDIENCE_LABELS = {'Zielgruppe', 'Publikum', 'Empfängerrolle'}

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ''


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:  # pragma: no cover - command-line validation
        fail(f'{path.relative_to(ROOT)} unreadable: {exc}')
        return {}


def spec_for(data: dict, app_code: str, app: dict, task: dict) -> dict:
    ctx = (data.get('TASK_CONTEXT_SPEC') or {}).get(task['id']) or {}
    fields = []
    for i, label in enumerate(task.get('required') or []):
        fields.append({'label': label, 'kind': 'required', 'sort_order': i, 'optional_fragment': ''})
    for i, label in enumerate(task.get('optional') or []):
        fields.append({
            'label': label,
            'kind': 'optional',
            'sort_order': i,
            'optional_fragment': (ctx.get('optional') or {}).get(label, ''),
        })
    options = []
    for kind, values in (
        ('source', task.get('sources') or []),
        ('output', task.get('outputs') or []),
        ('focus', task.get('focus') or []),
        ('audience', task.get('audiences') or []),
    ):
        for i, value in enumerate(values):
            options.append({'kind': kind, 'value': value, 'label': value, 'sort_order': i})
    app_rank = int(((data.get('ACCESS_RULES') or {}).get(app_code) or {}).get('tier', 0))
    task_rank = int(((data.get('TASK_ACCESS_RULES') or {}).get(task['id']) or {}).get('tier', 0))
    return {
        'task_id': task['id'],
        'application': {
            'code': app_code,
            'name': app['name'],
            'rule': app.get('rule') or '',
            'minimum_tier_rank': app_rank,
        },
        'version': {
            'version': 1,
            'title': task['title'],
            'area': task.get('area') or '',
            'family': task.get('family') or 'analysis',
            'intent': task.get('intent') or '',
            'max_chars': task.get('maxChars'),
            'context_template': ctx.get('base') or '',
            'minimum_tier_rank': task_rank,
            'fields': fields,
            'options': options,
        },
        'policy': {
            'version': 1,
            'source_labels': data.get('SRC_LABEL') or {},
            'source_instructions': data.get('SRC_INSTRUCTION') or {},
            'method_rules': data.get('METHOD') or {},
            'quality_rules': data.get('QUALITY') or {},
            'tone_rules': data.get('TONE') or {},
            'detail_rules': data.get('DETAIL') or {},
            'no_fabrication_rule': (
                'Erfinde keine Fakten, Zahlen, Termine, Personen, Verantwortlichkeiten, Quellen oder Zusagen; '
                'wenn eine notwendige Information fehlt, benenne die konkrete Lücke statt sie stillschweigend zu ergänzen.'
            ),
        },
    }


def payload_for(task: dict) -> dict:
    values = {label: f'Testwert {i + 1}' for i, label in enumerate(task.get('required') or [])}
    if task.get('optional'):
        values[task['optional'][0]] = 'Optionaler Testwert'
    return {
        'microsoft_tier_rank': 2,
        'fields': values,
        'audience': (task.get('audiences') or ['Management'])[0],
        'focus': (task.get('focus') or [])[:2],
        'output': (task.get('outputs') or ['Ergebnis'])[0],
        'source': (task.get('sources') or ['provided'])[0],
        'tone': 'professional',
        'detail': 'standard',
    }


extract_check = subprocess.run(
    [sys.executable, str(ROOT / 'scripts' / 'verify_golden_extraction.py')],
    cwd=ROOT, capture_output=True, text=True,
)
if extract_check.returncode:
    fail('Golden-Master extraction mismatch: ' + (extract_check.stdout + extract_check.stderr).strip())

data = load(DATA)
free = load(FREE_DATA)
meta = data.get('_meta') or {}

if sha(PRO_GM) != PRO_SHA:
    fail(f'Pro Golden Master hash mismatch: {sha(PRO_GM)}')
if sha(FREE_GM) != FREE_SHA:
    fail(f'Free Golden Master hash mismatch: {sha(FREE_GM)}')
if sha(PRODUCT_PRO_GM) != PRO_SHA:
    fail(f'Product Pro Golden Master hash mismatch: {sha(PRODUCT_PRO_GM)}')
if sha(PRODUCT_FREE_GM) != FREE_SHA:
    fail(f'Product Free Golden Master hash mismatch: {sha(PRODUCT_FREE_GM)}')
if meta.get('source_sha256') != PRO_SHA:
    fail('PM20 JSON source hash does not match approved Pro Golden Master')
if free.get('source_sha256') != FREE_SHA:
    fail('Free legacy JSON source hash does not match approved Free Golden Master')

apps = data.get('APP') or {}
if len(apps) != 34 or meta.get('application_count') != 34:
    fail(f'Expected 34 PM20 applications, got {len(apps)}')

tasks: dict[str, tuple[str, dict, dict]] = {}
for app_code, app in apps.items():
    for task in app.get('tasks') or []:
        tid = task.get('id')
        if not tid:
            fail(f'{app_code}: task without ID')
            continue
        if tid in tasks:
            fail(f'Duplicate task ID: {tid}')
        tasks[tid] = (app_code, app, task)
        if not task.get('required'):
            fail(f'{tid}: no required fields')
        for key in ('sources', 'outputs', 'focus', 'audiences'):
            if not task.get(key):
                fail(f'{tid}: empty {key}')
        family = task.get('family') or 'analysis'
        if family not in (data.get('METHOD') or {}):
            fail(f'{tid}: family {family} has no METHOD rule')
        if family not in (data.get('QUALITY') or {}):
            fail(f'{tid}: family {family} has no QUALITY rule')
        for source in task.get('sources') or []:
            if source not in (data.get('SRC_INSTRUCTION') or {}):
                fail(f'{tid}: source {source} has no SRC_INSTRUCTION')

if len(tasks) != 194 or meta.get('task_count') != 194:
    fail(f'Expected 194 unique PM20 tasks, got {len(tasks)}')

if data.get('M365_TIER') != {'chatbasic': 0, 'm365basic': 1, 'premium': 2}:
    fail(f'Unexpected Microsoft tier map: {data.get("M365_TIER")}')

for name in ('ACCESS_RULES', 'TASK_ACCESS_RULES'):
    for ref, rule in (data.get(name) or {}).items():
        if name == 'ACCESS_RULES' and ref not in apps:
            fail(f'{name} references missing app {ref}')
        if name == 'TASK_ACCESS_RULES' and ref not in tasks:
            fail(f'{name} references missing task {ref}')
        if 'tier' in rule and int(rule['tier']) not in {0, 1, 2}:
            fail(f'{name} {ref}: invalid tier {rule["tier"]}')

context_specs = data.get('TASK_CONTEXT_SPEC') or {}
if len(context_specs) != meta.get('context_spec_count'):
    fail('Context-spec metadata count mismatch')
for tid, ctx in context_specs.items():
    if tid not in tasks:
        fail(f'Context spec references missing task {tid}')
        continue
    task = tasks[tid][2]
    fields = set((task.get('required') or []) + (task.get('optional') or []))
    placeholders = set(re.findall(r'\{([^}]+)\}', ctx.get('base') or ''))
    if not placeholders.issubset(fields):
        fail(f'{tid}: context base references unknown fields {sorted(placeholders - fields)}')
    optional = set(task.get('optional') or [])
    if not set((ctx.get('optional') or {}).keys()).issubset(optional):
        fail(f'{tid}: context optional map references non-optional fields')

legacy_ids = [item.get('legacy_id') for item in free.get('tasks') or []]
if len(legacy_ids) != 16 or len(set(legacy_ids)) != 16:
    fail(f'Expected 16 unique Free legacy tasks, got {len(set(legacy_ids))}')

if set(legacy_ids) != set(FREE_RUNTIME_CONTRACTS):
    fail(
        'Free runtime-contract IDs differ from preserved legacy IDs: '
        f'{sorted(set(legacy_ids) ^ set(FREE_RUNTIME_CONTRACTS))}'
    )
for legacy_id in legacy_ids:
    runtime = FREE_RUNTIME_CONTRACTS.get(legacy_id) or {}
    if not runtime.get('intent') or not runtime.get('audiences') or not runtime.get('formats') or not runtime.get('focus'):
        fail(f'{legacy_id}: incomplete Free runtime contract')
        continue
    contract = SimpleNamespace(legacy_id=legacy_id, payload={'runtime_contract': runtime})
    try:
        free_result = compose_free_legacy(
            contract=contract,
            microsoft_tier='premium',
            payload={
                'primary': 'Free-Validator-Primärwert',
                'secondary': 'Free-Validator-Sekundärwert',
                'audience': runtime['audiences'][0],
                'focus': [runtime['focus'][0]],
                'output': runtime['formats'][0],
                'tone': 'professional',
                'detail': 'short',
            },
        )
    except Exception as exc:
        fail(f'{legacy_id}: Free composer failed: {exc}')
        continue
    if not free_result.get('ready') or not free_result.get('prompt'):
        fail(f'{legacy_id}: Free composer did not produce a ready prompt')
    if free_result.get('source') != 'PromptLegacyContract':
        fail(f'{legacy_id}: Free composer did not declare database contract source')

# Run every current PM20 task through the stateless composer. This catches
# field loss, unresolved placeholders, invalid policy references and maxChars.
for tid, (app_code, app, task) in tasks.items():
    spec = spec_for(data, app_code, app, task)
    payload = payload_for(task)
    try:
        result = compose_prompt(spec, payload)
    except Exception as exc:
        fail(f'{tid}: composer failed: {exc}')
        continue
    if not result.prompt.strip():
        fail(f'{tid}: empty prompt')
    if result.progress_percent != 100:
        fail(f'{tid}: expected 100% progress, got {result.progress_percent}')
    if re.search(r'\{[^}]+\}', result.prompt):
        fail(f'{tid}: unresolved placeholder in composed prompt')
    if task.get('maxChars') and len(result.prompt) > int(task['maxChars']):
        fail(f'{tid}: maxChars exceeded ({len(result.prompt)} > {task["maxChars"]})')
    # Non-compact tasks must carry every required user value. This specifically
    # guards the 114 PM20 tasks that have fields but no handcrafted context map.
    if not task.get('maxChars'):
        for value in payload['fields'].values():
            if value not in result.prompt:
                fail(f'{tid}: supplied field value lost by composer: {value}')

# Exact Golden-Master parity case: PM20-001 has a handcrafted context spec.
app_code, app, task = tasks['PM20-001']
spec = spec_for(data, app_code, app, task)
payload = {
    'microsoft_tier_rank': 0,
    'fields': {'Fragestellung': 'Wie verbessern wir den Support?', 'Kontext': 'B2B-Systemhaus'},
    'audience': 'Management',
    'focus': ['Primärquellen', 'Aktualität'],
    'output': 'Fundierte Antwort',
    'source': 'webwork',
    'tone': 'professional',
    'detail': 'standard',
}
try:
    exact = compose_prompt(spec, payload).prompt
    required_fragments = [
        task['intent'],
        'Beantworte die Fragestellung „Wie verbessern wir den Support?“ und beziehe dabei den Kontext „B2B-Systemhaus“ ein.',
        'Lege besonderes Augenmerk auf Primärquellen, Aktualität.',
        'Richte die Darstellung auf „Management“ aus.',
        'Liefere das Ergebnis im Format „Fundierte Antwort“.',
        'Für Copilot Chat gilt dabei:',
        'Erfinde keine Fakten, Zahlen, Termine, Personen, Verantwortlichkeiten, Quellen oder Zusagen;',
    ]
    for fragment in required_fragments:
        if fragment not in exact:
            fail(f'PM20-001 parity fragment missing: {fragment}')
except Exception as exc:
    fail(f'PM20-001 parity composition failed: {exc}')

# Guard tier enforcement on both application- and task-level rules.
for tid, tier in [('PM20-016', 0), ('PM20-005', 0), ('PM20-005', 1)]:
    app_code, app, task = tasks[tid]
    spec = spec_for(data, app_code, app, task)
    payload = payload_for(task)
    payload['microsoft_tier_rank'] = tier
    try:
        compose_prompt(spec, payload)
        fail(f'{tid}: tier {tier} should have been rejected')
    except PromptValidationError as exc:
        if exc.code != 'tier_required':
            fail(f'{tid}: wrong tier rejection code {exc.code}')

# Required-field and choice validation.
app_code, app, task = tasks['PM20-001']
spec = spec_for(data, app_code, app, task)
bad = payload_for(task)
bad['fields'] = {}
try:
    compose_prompt(spec, bad)
    fail('Missing required field was accepted')
except PromptValidationError as exc:
    if exc.code != 'required':
        fail(f'Missing required field returned {exc.code}')

bad = payload_for(task)
bad['source'] = '__invalid__'
try:
    compose_prompt(spec, bad)
    fail('Invalid source was accepted')
except PromptValidationError as exc:
    if exc.code != 'choice':
        fail(f'Invalid source returned {exc.code}')

if errors:
    for message in errors:
        print(f'[FAIL] {message}')
    print(f'PROMPT DOMAIN VALIDATION FAILED: {len(errors)} issue(s)')
    raise SystemExit(1)

print('PROMPT DOMAIN VALIDATION OK')
print(f'PM20 catalog: {len(apps)} apps / {len(tasks)} tasks / {len(context_specs)} handcrafted context specs')
print(f'Free legacy preservation + DB composer smoke: {len(legacy_ids)}/16 contracts')
print('Composer smoke: 194/194 tasks composed successfully with no unresolved placeholders')
