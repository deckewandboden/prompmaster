from __future__ import annotations

from django.db.models import Prefetch

from apps.catalog.models import Product, ProductEntitlement

from .composer_core import PromptValidationError, compose_prompt
from .free_legacy import AUDIENCE_DISPLAY, FORMAT_LABELS
from .free_surface import (
    FREE_INPUT_META,
    FREE_SURFACE_ALIAS_TO_PRO_ID,
    FREE_SURFACE_PRO_CONTRACTS,
    FREE_TO_PRO_APP_CODE,
)
from .models import (
    MicrosoftCapability,
    MicrosoftTier,
    PromptApplication,
    PromptDefinition,
    PromptField,
    PromptOption,
    PromptLegacyContract,
    PromptPolicySet,
    PromptVersion,
)


def active_policy() -> PromptPolicySet:
    policy = PromptPolicySet.objects.filter(active=True).order_by('-version').first()
    if not policy:
        raise PromptValidationError('Keine aktive Prompt-Policy vorhanden.', code='catalog_not_seeded')
    return policy


def published_version(task_id: str) -> PromptVersion:
    version = (
        PromptVersion.objects.select_related('definition__application', 'policy_set')
        .prefetch_related(
            Prefetch('fields', queryset=PromptField.objects.order_by('sort_order')),
            Prefetch('options', queryset=PromptOption.objects.order_by('kind', 'sort_order')),
        )
        .filter(definition__task_id=task_id, definition__active=True, lifecycle='PUBLISHED')
        .first()
    )
    if not version:
        raise PromptValidationError('Prompt-Aufgabe nicht veröffentlicht.', field='task_id', code='not_found')
    return version


def tier_by_code(code: str) -> MicrosoftTier:
    tier = MicrosoftTier.objects.filter(code=code, active=True).first()
    if not tier:
        raise PromptValidationError('Unbekannte Microsoft-Copilot-Stufe.', field='microsoft_tier', code='choice')
    return tier


def _minimum_tier_rank(version: PromptVersion) -> tuple[int, int]:
    app_rank = 0
    task_rank = 0
    from django.db.models import Q
    caps = MicrosoftCapability.objects.filter(active=True).select_related('minimum_tier').filter(
        Q(definition=version.definition) | Q(application=version.definition.application)
    )
    for cap in caps:
        if cap.scope == 'application':
            app_rank = max(app_rank, cap.minimum_tier.rank)
        elif cap.scope == 'task':
            task_rank = max(task_rank, cap.minimum_tier.rank)
    return app_rank, task_rank


def build_spec(task_id: str) -> dict:
    version = published_version(task_id)
    policy = version.policy_set
    app = version.definition.application
    app_rank, task_rank = _minimum_tier_rank(version)
    ordered_fields = sorted(
        version.fields.all(),
        key=lambda field: (0 if field.kind == 'required' else 1, field.sort_order, field.label),
    )
    fields = [
        {
            'label': field.label,
            'kind': field.kind,
            'sort_order': field.sort_order,
            'optional_fragment': field.optional_fragment,
        }
        for field in ordered_fields
    ]
    options = [
        {
            'kind': option.kind,
            'value': option.value,
            'label': option.label,
            'sort_order': option.sort_order,
        }
        for option in version.options.all()
    ]
    return {
        'task_id': version.definition.task_id,
        'application': {
            'code': app.code,
            'name': app.name,
            'rule': version.app_rule_snapshot or app.rule,
            'minimum_tier_rank': app_rank,
        },
        'version': {
            'version': version.version,
            'title': version.title,
            'area': version.area,
            'family': version.family,
            'intent': version.intent,
            'max_chars': version.max_chars,
            'context_template': version.context_template,
            'minimum_tier_rank': task_rank,
            'fields': fields,
            'options': options,
        },
        'policy': {
            'version': policy.version,
            'source_labels': policy.source_labels,
            'source_instructions': policy.source_instructions,
            'method_rules': policy.method_rules,
            'quality_rules': policy.quality_rules,
            'tone_rules': policy.tone_rules,
            'detail_rules': policy.detail_rules,
            'no_fabrication_rule': policy.no_fabrication_rule,
        },
    }



def build_spec_for_version(version: PromptVersion) -> dict:
    version = (
        PromptVersion.objects.select_related('definition__application', 'policy_set')
        .prefetch_related(
            Prefetch('fields', queryset=PromptField.objects.order_by('sort_order')),
            Prefetch('options', queryset=PromptOption.objects.order_by('kind', 'sort_order')),
        )
        .get(pk=version.pk)
    )
    policy = version.policy_set
    app = version.definition.application
    app_rank, task_rank = _minimum_tier_rank(version)
    ordered_fields = sorted(
        version.fields.all(),
        key=lambda field: (0 if field.kind == 'required' else 1, field.sort_order, field.label),
    )
    fields = [
        {
            'label': field.label,
            'kind': field.kind,
            'sort_order': field.sort_order,
            'optional_fragment': field.optional_fragment,
        }
        for field in ordered_fields
    ]
    options = [
        {
            'kind': option.kind,
            'value': option.value,
            'label': option.label,
            'sort_order': option.sort_order,
        }
        for option in version.options.all()
    ]
    return {
        'task_id': version.definition.task_id,
        'application': {
            'code': app.code,
            'name': app.name,
            'rule': version.app_rule_snapshot or app.rule,
            'minimum_tier_rank': app_rank,
        },
        'version': {
            'version': version.version,
            'title': version.title,
            'area': version.area,
            'family': version.family,
            'intent': version.intent,
            'max_chars': version.max_chars,
            'context_template': version.context_template,
            'minimum_tier_rank': task_rank,
            'fields': fields,
            'options': options,
        },
        'policy': {
            'version': policy.version,
            'source_labels': policy.source_labels,
            'source_instructions': policy.source_instructions,
            'method_rules': policy.method_rules,
            'quality_rules': policy.quality_rules,
            'tone_rules': policy.tone_rules,
            'detail_rules': policy.detail_rules,
            'no_fabrication_rule': policy.no_fabrication_rule,
        },
    }


def compose_version(*, version: PromptVersion, microsoft_tier: str, payload: dict):
    tier = tier_by_code(microsoft_tier)
    spec = build_spec_for_version(version)
    compose_payload = dict(payload or {})
    compose_payload['microsoft_tier_rank'] = tier.rank
    return compose_prompt(spec, compose_payload)

def task_entitled(product_code: str, task_id: str) -> bool:
    feature_code = f'prompt.task.{task_id}'
    return ProductEntitlement.objects.filter(
        product__code=product_code,
        product__active=True,
        feature__code=feature_code,
        enabled=True,
    ).exists()


def compose_task(*, task_id: str, microsoft_tier: str, payload: dict, product_code: str = 'PRO'):
    if not task_entitled(product_code, task_id):
        raise PromptValidationError(
            'Diese Prompt-Aufgabe ist für das ausgewählte PromptMaster-Produkt nicht freigeschaltet.',
            field='task_id',
            code='entitlement_required',
        )
    tier = tier_by_code(microsoft_tier)
    spec = build_spec(task_id)
    compose_payload = dict(payload or {})
    compose_payload['microsoft_tier_rank'] = tier.rank
    return compose_prompt(spec, compose_payload)



def _policy_spec(policy: PromptPolicySet) -> dict:
    return {
        'version': policy.version,
        'source_labels': policy.source_labels,
        'source_instructions': policy.source_instructions,
        'method_rules': policy.method_rules,
        'quality_rules': policy.quality_rules,
        'tone_rules': policy.tone_rules,
        'detail_rules': policy.detail_rules,
        'no_fabrication_rule': policy.no_fabrication_rule,
    }


def _surface_options(contract: dict) -> list[dict]:
    options = []
    for kind, key in (
        ('source', 'sources'),
        ('output', 'outputs'),
        ('focus', 'focus'),
        ('audience', 'audiences'),
    ):
        for index, value in enumerate(contract.get(key) or []):
            options.append({
                'kind': kind,
                'value': value,
                'label': value,
                'sort_order': index,
            })
    return options


def _surface_fields(contract: dict) -> list[dict]:
    fields = []
    for kind, key in (('required', 'required'), ('optional', 'optional')):
        for index, label in enumerate(contract.get(key) or []):
            fields.append({
                'label': label,
                'kind': kind,
                'sort_order': index,
                'optional_fragment': '',
            })
    return fields


def build_free_legacy_pro_spec(task_id: str) -> dict:
    contract = PromptLegacyContract.objects.filter(
        source='FREE_1_2_4',
        legacy_id=task_id,
    ).first()
    if not contract:
        raise PromptValidationError(
            'Free-Prompt-Aufgabe nicht veröffentlicht.',
            field='task_id',
            code='not_found',
        )
    app_code = FREE_TO_PRO_APP_CODE.get(contract.application_code)
    app = PromptApplication.objects.filter(code=app_code, active=True).first()
    if not app:
        raise PromptValidationError(
            'Prompt-Anwendung nicht veröffentlicht.',
            field='task_id',
            code='not_found',
        )
    entry = _free_legacy_catalog_entry(contract)
    policy = active_policy()
    fields = []
    for kind, key in (('required', 'required'), ('optional', 'optional')):
        for index, label in enumerate(entry[key]):
            fields.append({
                'label': label,
                'kind': kind,
                'sort_order': index,
                'optional_fragment': '',
            })
    options = []
    for kind, key in (
        ('source', 'sources'),
        ('output', 'outputs'),
        ('focus', 'focus'),
        ('audience', 'audiences'),
    ):
        for index, value in enumerate(entry[key]):
            options.append({
                'kind': kind,
                'value': value,
                'label': value,
                'sort_order': index,
            })
    return {
        'task_id': task_id,
        'application': {
            'code': app.code,
            'name': app.name,
            'rule': app.rule,
            'minimum_tier_rank': 0,
        },
        'version': {
            'version': 1,
            'title': entry['title'],
            'area': entry['area'],
            'family': entry['family'],
            'intent': entry['intent'],
            'max_chars': None,
            'context_template': '',
            'minimum_tier_rank': entry['minimum_tier_rank'],
            'fields': fields,
            'options': options,
        },
        'policy': _policy_spec(policy),
    }


def compose_free_legacy_pro_task(*, task_id: str, microsoft_tier: str, payload: dict):
    tier = tier_by_code(microsoft_tier)
    spec = build_free_legacy_pro_spec(task_id)
    compose_payload = dict(payload or {})
    compose_payload['microsoft_tier_rank'] = tier.rank
    return compose_prompt(spec, compose_payload)


def build_free_surface_pro_spec(task_id: str) -> dict:
    contract = FREE_SURFACE_PRO_CONTRACTS.get(task_id)
    if not contract:
        raise PromptValidationError(
            'Prompt-Aufgabe nicht veröffentlicht.',
            field='task_id',
            code='not_found',
        )
    app = PromptApplication.objects.filter(
        code=contract['app_code'],
        active=True,
    ).first()
    if not app:
        raise PromptValidationError(
            'Prompt-Anwendung nicht veröffentlicht.',
            field='task_id',
            code='not_found',
        )
    policy = active_policy()
    return {
        'task_id': task_id,
        'application': {
            'code': app.code,
            'name': app.name,
            'rule': app.rule,
            'minimum_tier_rank': 0,
        },
        'version': {
            'version': 1,
            'title': contract['title'],
            'area': contract['area'],
            'family': contract['family'],
            'intent': contract['intent'],
            'max_chars': None,
            'context_template': '',
            'minimum_tier_rank': int(contract.get('minimum_tier_rank') or 0),
            'fields': _surface_fields(contract),
            'options': _surface_options(contract),
        },
        'policy': _policy_spec(policy),
    }


def compose_free_surface_pro_task(*, task_id: str, microsoft_tier: str, payload: dict):
    tier = tier_by_code(microsoft_tier)
    spec = build_free_surface_pro_spec(task_id)
    compose_payload = dict(payload or {})
    compose_payload['microsoft_tier_rank'] = tier.rank
    return compose_prompt(spec, compose_payload)


def _free_legacy_catalog_entry(contract: PromptLegacyContract) -> dict:
    runtime = (contract.payload or {}).get('runtime_contract') or {}
    meta = FREE_INPUT_META.get(contract.legacy_id) or {}
    primary = meta.get('primary') or 'Aufgabe / Kontext'
    secondary = meta.get('secondary') or 'Zusätzliche Angaben'

    required = []
    optional = []
    if runtime.get('primary_required'):
        required.append(primary)
    else:
        optional.append(primary)
    if runtime.get('secondary_required'):
        required.append(secondary)
    else:
        optional.append(secondary)

    return {
        'id': contract.legacy_id,
        'title': contract.title,
        'intent': runtime.get('intent') or contract.title,
        'required': required,
        'optional': optional,
        'area': (contract.payload or {}).get('area') or 'Free-Basis',
        'family': runtime.get('family') or 'analysis',
        'sources': ['provided'],
        'outputs': [
            FORMAT_LABELS.get(value, value)
            for value in (runtime.get('formats') or [])
        ],
        'focus': list(runtime.get('focus') or []),
        'audiences': [
            AUDIENCE_DISPLAY.get(value, value)
            for value in (runtime.get('audiences') or [])
        ],
        'access': None,
        'status': 'FREE + PRO',
        'maxChars': None,
        'prompt_version': 'FREE_1_2_4',
        'policy_version': 'FREE_1_2_4',
        'minimum_tier_rank': int(runtime.get('minimum_tier_rank') or 0),
        'promptmaster_entitled': True,
        'compatibility_kind': 'free_legacy',
        'surface_origin': 'FREE_1_2_4',
    }


def _free_pro_preview_catalog_entry(task_id: str, contract: dict, policy_version: int) -> dict:
    return {
        'id': task_id,
        'title': contract['title'],
        'intent': contract['intent'],
        'required': list(contract.get('required') or []),
        'optional': list(contract.get('optional') or []),
        'area': contract.get('area') or 'Pro',
        'family': contract.get('family') or 'analysis',
        'sources': list(contract.get('sources') or ['provided']),
        'outputs': list(contract.get('outputs') or ['Ergebnis']),
        'focus': list(contract.get('focus') or []),
        'audiences': list(contract.get('audiences') or []),
        'access': None,
        'status': 'PRO',
        'maxChars': None,
        'prompt_version': 1,
        'policy_version': policy_version,
        'minimum_tier_rank': int(contract.get('minimum_tier_rank') or 0),
        'promptmaster_entitled': True,
        'compatibility_kind': 'free_pro_preview',
        'surface_origin': 'FREE_1_2_4',
    }


def _prepend_free_surface_to_pro_catalog(apps: dict[str, dict], policy_version: int) -> None:
    surface_by_app: dict[str, list[dict]] = {}

    legacy_contracts = PromptLegacyContract.objects.filter(
        source='FREE_1_2_4',
    ).order_by('application_code', 'legacy_id')
    for contract in legacy_contracts:
        if contract.legacy_id in FREE_SURFACE_ALIAS_TO_PRO_ID:
            continue
        app_code = FREE_TO_PRO_APP_CODE.get(contract.application_code)
        if not app_code:
            continue
        surface_by_app.setdefault(app_code, []).append(
            _free_legacy_catalog_entry(contract)
        )

    for task_id, contract in FREE_SURFACE_PRO_CONTRACTS.items():
        if task_id in FREE_SURFACE_ALIAS_TO_PRO_ID:
            continue
        surface_by_app.setdefault(contract['app_code'], []).append(
            _free_pro_preview_catalog_entry(task_id, contract, policy_version)
        )

    for app_code, surface_tasks in surface_by_app.items():
        app = apps.get(app_code)
        if not app:
            raise PromptValidationError(
                f'Free/Pro-Paritätsfehler: Anwendung {app_code} fehlt im Pro-Katalog.',
                field='application',
                code='catalog_not_seeded',
            )
        existing_ids = {task['id'] for task in app['tasks']}
        collisions = existing_ids.intersection(task['id'] for task in surface_tasks)
        if collisions:
            raise PromptValidationError(
                'Free/Pro-Paritätsfehler: doppelte Task-IDs: '
                + ', '.join(sorted(collisions)),
                field='task_id',
                code='catalog_not_seeded',
            )
        app['tasks'] = surface_tasks + app['tasks']

    # Mark canonical PM20 tasks that cover a Free-surface function. They stay
    # single cards in Pro; the alias metadata is for auditability only.
    for surface_id, canonical_id in FREE_SURFACE_ALIAS_TO_PRO_ID.items():
        matches = [
            task
            for app in apps.values()
            for task in app['tasks']
            if task['id'] == canonical_id
        ]
        if len(matches) != 1:
            raise PromptValidationError(
                f'Free/Pro-Paritätsfehler: Alias {surface_id} -> {canonical_id} '
                f'hat {len(matches)} kanonische Treffer.',
                field='task_id',
                code='catalog_not_seeded',
            )
        matches[0].setdefault('surface_aliases', []).append(surface_id)


def catalog_snapshot(product_code: str = 'PRO') -> dict:
    """Return the authoritative product catalog consumed by the Pro runtime.

    The browser Golden Master is only a presentation/reference asset.  Runtime
    application/task metadata comes from the published PromptDomain state so
    Prompt Studio publications become visible without rebuilding the HTML.
    """
    policy = active_policy()
    product = Product.objects.filter(code=product_code, active=True).first()
    feature_codes: set[str] = set()
    if product:
        feature_codes = set(
            ProductEntitlement.objects.filter(product=product, enabled=True).values_list('feature__code', flat=True)
        )

    published_versions = (
        PromptVersion.objects.filter(lifecycle='PUBLISHED')
        .select_related('policy_set')
        .prefetch_related(
            Prefetch('fields', queryset=PromptField.objects.order_by('kind', 'sort_order', 'label')),
            Prefetch('options', queryset=PromptOption.objects.order_by('kind', 'sort_order', 'value')),
        )
        .order_by('-version')
    )
    definitions = (
        PromptDefinition.objects.filter(active=True, application__active=True)
        .select_related('application')
        .prefetch_related(
            Prefetch('versions', queryset=published_versions, to_attr='published_runtime_versions'),
            'microsoft_capabilities__minimum_tier',
            'application__microsoft_capabilities__minimum_tier',
        )
        .order_by('application__sort_order', 'task_id')
    )

    apps: dict[str, dict] = {}
    for definition in definitions:
        versions = getattr(definition, 'published_runtime_versions', [])
        version = versions[0] if versions else None
        if not version:
            continue

        task_feature = f'prompt.task.{definition.task_id}'
        entitled = task_feature in feature_codes
        if product_code != 'FREE' and product and not entitled:
            # Product-specific paid catalogs are fail-closed.  Free remains a
            # visibility/reference catalog until its reviewed legacy mapping is
            # published, so its tasks are returned with entitlement=false.
            continue

        app = definition.application
        app_min_rank = max(
            (cap.minimum_tier.rank for cap in app.microsoft_capabilities.all() if cap.active),
            default=0,
        )
        app_entry = apps.setdefault(
            app.code,
            {
                'code': app.code,
                'name': app.name,
                'group': app.group,
                'icon': app.icon,
                'color': app.color,
                # Runtime keys intentionally mirror the existing Golden Master
                # JS contract to keep the visual layer stable.
                'copy': app.description,
                'access': app.access_text,
                'status': app.status,
                'target': app.target,
                'rule': app.rule,
                'evidence': app.evidence,
                'sort_order': app.sort_order,
                'minimum_tier_rank': app_min_rank,
                'promptmaster_entitled': (
                    f'prompt.app.{app.code}' in feature_codes
                    if product
                    else True
                ),
                'tasks': [],
            },
        )

        task_min_rank = max(
            (cap.minimum_tier.rank for cap in definition.microsoft_capabilities.all() if cap.active),
            default=0,
        )
        fields = list(version.fields.all())
        options = list(version.options.all())

        def option_values(kind: str) -> list[str]:
            return [option.value for option in options if option.kind == kind]

        app_entry['tasks'].append(
            {
                'id': definition.task_id,
                'title': version.title,
                'intent': version.intent,
                'required': [field.label for field in fields if field.kind == 'required'],
                'optional': [field.label for field in fields if field.kind == 'optional'],
                'area': version.area,
                'family': version.family,
                'sources': option_values('source'),
                'outputs': option_values('output'),
                'focus': option_values('focus'),
                'audiences': option_values('audience'),
                'access': version.access,
                'status': version.product_status or app.status,
                'maxChars': version.max_chars,
                'prompt_version': version.version,
                'policy_version': version.policy_set.version,
                'minimum_tier_rank': task_min_rank,
                'promptmaster_entitled': entitled,
            }
        )

    if product_code == 'PRO':
        _prepend_free_surface_to_pro_catalog(apps, policy.version)

    applications = sorted(apps.values(), key=lambda item: (item['sort_order'], item['name']))
    task_count = sum(len(app['tasks']) for app in applications)
    return {
        'product_code': product_code,
        'policy_version': policy.version,
        'source_labels': policy.source_labels,
        'application_count': len(applications),
        'task_count': task_count,
        'applications': applications,
    }

