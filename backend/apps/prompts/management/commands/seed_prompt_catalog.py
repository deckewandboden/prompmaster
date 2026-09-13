from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Feature, Product, ProductEntitlement
from apps.prompts.composer_core import DEFAULT_NO_FABRICATION_RULE
from apps.prompts.models import (
    MicrosoftCapability,
    MicrosoftTier,
    PromptApplication,
    PromptDefinition,
    PromptField,
    PromptLegacyContract,
    PromptOption,
    PromptPolicySet,
    PromptVersion,
    PromptTestCase,
)


DATA_DIR = Path(__file__).resolve().parents[2] / 'data'
CATALOG_FILE = DATA_DIR / 'pm20_golden_logic.json'
FREE_LEGACY_FILE = DATA_DIR / 'free_legacy_tasks.json'

TIER_NAMES = {
    'chatbasic': 'Copilot Chat',
    'm365basic': 'M365 Copilot (Basic)',
    'premium': 'Microsoft 365 Copilot Business',
}


class Command(BaseCommand):
    help = 'Importiert den aktuellen PM20-Golden-Master in die zentrale Prompt-Domain.'

    def _load(self, path: Path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            raise CommandError(f'{path.name} kann nicht gelesen werden: {exc}') from exc

    @transaction.atomic
    def handle(self, *args, **options):
        data = self._load(CATALOG_FILE)
        meta = data.get('_meta') or {}
        expected_sha = str(meta.get('source_sha256') or '')
        expected_apps = int(meta.get('application_count') or 0)
        expected_tasks = int(meta.get('task_count') or 0)

        if expected_apps != 34 or expected_tasks != 194:
            raise CommandError(f'Katalog-Metadaten unerwartet: {expected_apps} Apps / {expected_tasks} Tasks.')

        golden_path = Path(settings.PRO_GOLDEN_MASTER_PATH)
        if not golden_path.is_file():
            raise CommandError(f'Pro-Golden-Master fehlt: {golden_path}')
        actual_sha = hashlib.sha256(golden_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise CommandError(f'Pro-Golden-Master SHA256 abweichend: {actual_sha} != {expected_sha}')

        tiers = {}
        for code, rank in sorted((data.get('M365_TIER') or {}).items(), key=lambda item: item[1]):
            tier, _ = MicrosoftTier.objects.update_or_create(
                code=code,
                defaults={
                    'name': TIER_NAMES.get(code, code),
                    'rank': int(rank),
                    'description': 'Aus dem aktuellen PromptMaster-Pro-Golden-Master importiert.',
                    'active': True,
                },
            )
            tiers[code] = tier

        existing_active_policy = PromptPolicySet.objects.filter(active=True).exclude(
            name='PM20 Golden Master', version=1
        ).exists()
        policy, _ = PromptPolicySet.objects.update_or_create(
            name='PM20 Golden Master',
            version=1,
            defaults={
                'active': not existing_active_policy,
                'source_labels': data.get('SRC_LABEL') or {},
                'source_instructions': data.get('SRC_INSTRUCTION') or {},
                'method_rules': data.get('METHOD') or {},
                'quality_rules': data.get('QUALITY') or {},
                'tone_rules': data.get('TONE') or {},
                'detail_rules': data.get('DETAIL') or {},
                'no_fabrication_rule': DEFAULT_NO_FABRICATION_RULE,
                'source_sha256': expected_sha,
            },
        )

        # The catalog Product is the commercial entitlement source. FREE is a
        # non-purchasable catalog identity; its 16 legacy tasks are preserved
        # below until an explicitly reviewed PM20 mapping exists.
        pro, _ = Product.objects.get_or_create(
            code='PRO',
            defaults={
                'name': 'PromptMaster Pro',
                'description': 'PromptMaster Pro',
                'default_license_days': 365,
                'default_device_limit': 2,
                'reminder_1_days': 60,
                'reminder_2_days': 30,
                'critical_warning_days': 7,
            },
        )
        Product.objects.get_or_create(
            code='FREE',
            defaults={
                'name': 'PromptMaster Free',
                'description': 'PromptMaster Free – ohne Konto nutzbar',
                'active': True,
                'visible': True,
                'purchasable': False,
                'default_license_days': 365,
                'default_device_limit': 1,
                'reminder_1_days': 60,
                'reminder_2_days': 30,
                'critical_warning_days': 7,
            },
        )

        app_objects = {}
        definition_objects = {}
        context_specs = data.get('TASK_CONTEXT_SPEC') or {}
        source_labels = data.get('SRC_LABEL') or {}
        task_count = 0

        for app_order, (app_code, app_data) in enumerate((data.get('APP') or {}).items()):
            app, _ = PromptApplication.objects.update_or_create(
                code=app_code,
                defaults={
                    'name': app_data.get('name') or app_code,
                    'group': app_data.get('group') or 'm365',
                    'icon': app_data.get('icon') or '',
                    'color': app_data.get('color') or '',
                    'description': app_data.get('copy') or '',
                    'access_text': app_data.get('access') or '',
                    'status': app_data.get('status') or '',
                    'target': app_data.get('target') or '',
                    'rule': app_data.get('rule') or '',
                    'evidence': app_data.get('evidence') or [],
                    'sort_order': app_order,
                    'active': True,
                },
            )
            app_objects[app_code] = app

            app_feature, _ = Feature.objects.get_or_create(
                code=f'prompt.app.{app_code}', defaults={'name': f'Prompt-App: {app.name}'}
            )
            ProductEntitlement.objects.update_or_create(
                product=pro, feature=app_feature, defaults={'enabled': True}
            )

            for task_data in app_data.get('tasks') or []:
                task_count += 1
                task_id = task_data['id']
                definition, _ = PromptDefinition.objects.update_or_create(
                    task_id=task_id,
                    defaults={'application': app, 'active': True, 'legacy': False},
                )
                definition_objects[task_id] = definition

                context = context_specs.get(task_id) or {}
                version, created = PromptVersion.objects.get_or_create(
                    definition=definition,
                    version=1,
                    defaults={
                        'policy_set': policy,
                        'lifecycle': 'PUBLISHED',
                        'title': task_data.get('title') or task_id,
                        'area': task_data.get('area') or '',
                        'family': task_data.get('family') or 'analysis',
                        'intent': task_data.get('intent') or '',
                        'access': task_data.get('access'),
                        'product_status': task_data.get('status') or '',
                        'max_chars': task_data.get('maxChars'),
                        'context_template': context.get('base') or '',
                        'app_rule_snapshot': app.rule,
                        'source_sha256': expected_sha,
                        'published_at': timezone.now(),
                    },
                )
                if not created:
                    # Same frozen source SHA: repair deterministic seed state,
                    # but never overwrite a version from a different source.
                    if version.source_sha256 != expected_sha:
                        raise CommandError(f'{task_id} v1 stammt aus anderer Quelle; kein stilles Überschreiben.')
                    newer_published_exists = PromptVersion.objects.filter(
                        definition=definition, lifecycle='PUBLISHED'
                    ).exclude(pk=version.pk).exists()
                    version.lifecycle = 'ARCHIVED' if newer_published_exists else 'PUBLISHED'
                    version.policy_set = policy
                    version.title = task_data.get('title') or task_id
                    version.area = task_data.get('area') or ''
                    version.family = task_data.get('family') or 'analysis'
                    version.intent = task_data.get('intent') or ''
                    version.access = task_data.get('access')
                    version.product_status = task_data.get('status') or ''
                    version.max_chars = task_data.get('maxChars')
                    version.context_template = context.get('base') or ''
                    version.app_rule_snapshot = app.rule
                    version.save()

                version.fields.all().delete()
                for index, label in enumerate(task_data.get('required') or []):
                    PromptField.objects.create(
                        version=version,
                        label=label,
                        kind='required',
                        sort_order=index,
                    )
                optional_fragments = context.get('optional') or {}
                for index, label in enumerate(task_data.get('optional') or []):
                    PromptField.objects.create(
                        version=version,
                        label=label,
                        kind='optional',
                        sort_order=index,
                        optional_fragment=optional_fragments.get(label) or '',
                    )

                version.options.all().delete()
                for kind, values in (
                    ('source', task_data.get('sources') or []),
                    ('output', task_data.get('outputs') or []),
                    ('focus', task_data.get('focus') or []),
                    ('audience', task_data.get('audiences') or []),
                ):
                    for index, value in enumerate(values):
                        PromptOption.objects.create(
                            version=version,
                            kind=kind,
                            value=value,
                            label=(source_labels.get(value, value) if kind == 'source' else value),
                            sort_order=index,
                        )

                # Every seeded version receives a deterministic, non-destructive
                # smoke test. This is the minimum gate for later lifecycle
                # transitions; Prompt Managers can add richer regression tests
                # in Prompt Studio without changing the Golden Master.
                sample_fields = {
                    field.label: f'Testwert für {field.label}'
                    for field in version.fields.filter(kind='required').order_by('sort_order')
                }
                sample_payload = {
                    'microsoft_tier': 'premium',
                    'payload': {
                        'fields': sample_fields,
                        'tone': 'professional',
                        'detail': 'standard',
                    },
                }
                for option_kind, payload_key, many in (
                    ('audience', 'audience', False),
                    ('focus', 'focus', True),
                    ('output', 'output', False),
                    ('source', 'source', False),
                ):
                    values = list(
                        version.options.filter(kind=option_kind)
                        .order_by('sort_order')
                        .values_list('value', flat=True)
                    )
                    if values:
                        sample_payload['payload'][payload_key] = values[:2] if many else values[0]
                PromptTestCase.objects.update_or_create(
                    version=version,
                    name='system-smoke',
                    defaults={
                        'input_payload': sample_payload,
                        'expected_contains': [],
                        'expected_not_contains': ['{', '}'],
                        'enabled': True,
                        'sort_order': 0,
                        'last_status': 'NEVER',
                        'last_error': '',
                        'last_run_at': None,
                    },
                )

                task_feature, _ = Feature.objects.get_or_create(
                    code=f'prompt.task.{task_id}', defaults={'name': f'Prompt-Task: {task_id}'}
                )
                ProductEntitlement.objects.update_or_create(
                    product=pro, feature=task_feature, defaults={'enabled': True}
                )

        if len(app_objects) != 34 or task_count != 194:
            raise CommandError(f'Import unvollständig: {len(app_objects)} Apps / {task_count} Tasks.')

        MicrosoftCapability.objects.all().delete()
        reverse_tier = {int(rank): code for code, rank in (data.get('M365_TIER') or {}).items()}
        for app_code, rule in (data.get('ACCESS_RULES') or {}).items():
            if app_code not in app_objects or 'tier' not in rule:
                continue
            tier_code = reverse_tier[int(rule['tier'])]
            app = app_objects[app_code]
            MicrosoftCapability.objects.create(
                code=f'app:{app_code}',
                name=f'{app.name} · {tiers[tier_code].name}',
                scope='application',
                application=app,
                minimum_tier=tiers[tier_code],
                description=app.access_text,
                active=True,
            )
        for task_id, rule in (data.get('TASK_ACCESS_RULES') or {}).items():
            if task_id not in definition_objects or 'tier' not in rule:
                continue
            tier_code = reverse_tier[int(rule['tier'])]
            definition = definition_objects[task_id]
            MicrosoftCapability.objects.create(
                code=f'task:{task_id}',
                name=f'{task_id} · {tiers[tier_code].name}',
                scope='task',
                definition=definition,
                minimum_tier=tiers[tier_code],
                description='Task-spezifische Microsoft-Copilot-Stufe aus dem Golden Master.',
                active=True,
            )

        legacy = self._load(FREE_LEGACY_FILE)
        legacy_sha = legacy.get('source_sha256') or ''
        PromptLegacyContract.objects.filter(source='FREE_1_2_4').delete()
        for item in legacy.get('tasks') or []:
            PromptLegacyContract.objects.create(
                source='FREE_1_2_4',
                legacy_id=item['legacy_id'],
                application_code=item.get('app_code') or '',
                title=item.get('title') or item['legacy_id'],
                payload=item,
                mapping_status='unmapped',
                source_sha256=legacy_sha,
            )
        if PromptLegacyContract.objects.filter(source='FREE_1_2_4').count() != 16:
            raise CommandError('Free-Legacy-Verträge wurden nicht vollständig importiert.')

        self.stdout.write(
            self.style.SUCCESS(
                f'PromptDomain gesetzt: 34 Apps / 194 PM20 Tasks / 16 Free-Legacy-Verträge · Policy {policy.version}.'
            )
        )
