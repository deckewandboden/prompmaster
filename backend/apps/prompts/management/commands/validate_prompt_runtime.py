import json
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from apps.contenthub.models import FAQEntry
from apps.core.security import token_pair
from apps.integrations.models import ServiceAccount
from apps.prompts.free_legacy import compose_free_legacy
from apps.prompts.free_surface import FREE_SURFACE_IDS
from apps.prompts.lifecycle import run_test_case
from apps.prompts.models import PromptApplication, PromptDefinition, PromptLegacyContract, PromptTestCase, PromptVersion
from apps.prompts.services import catalog_snapshot


class Command(BaseCommand):
    help = 'Prüft 194 PM20-Definitionen, den 227-Aufgaben-Pro-Katalog, Smoke-Tests, FAQ und MCP-Transport.'

    def handle(self, *args, **options):
        counts = (
            PromptApplication.objects.filter(active=True).count(),
            PromptDefinition.objects.filter(active=True).count(),
            PromptLegacyContract.objects.filter(source='FREE_1_2_4').count(),
            PromptVersion.objects.filter(lifecycle='PUBLISHED').count(),
            PromptTestCase.objects.filter(
                name='system-smoke',
                enabled=True,
                version__lifecycle='PUBLISHED',
            ).count(),
        )
        if counts != (34, 194, 16, 194, 194):
            raise CommandError(f'PromptDomain-Zähler falsch: {counts}')

        pro_catalog = catalog_snapshot('PRO')
        pro_tasks = [
            task
            for app in pro_catalog.get('applications') or []
            for task in app.get('tasks') or []
        ]
        pro_ids = {task.get('id') for task in pro_tasks}
        if (
            pro_catalog.get('application_count') != 34
            or pro_catalog.get('task_count') != 227
            or len(pro_ids) != 227
        ):
            raise CommandError(
                'Pro-Runtime-Katalog unvollständig: '
                f"{pro_catalog.get('application_count')} Apps / "
                f"{pro_catalog.get('task_count')} Tasks / "
                f"{len(pro_ids)} eindeutige IDs"
            )
        missing_surface = set(FREE_SURFACE_IDS) - pro_ids
        if missing_surface:
            raise CommandError(
                'Free→Pro-Parität verletzt; fehlende Aufgaben: '
                + ', '.join(sorted(missing_surface))
            )

        legacy_contracts = list(
            PromptLegacyContract.objects.filter(source='FREE_1_2_4').order_by('legacy_id')
        )
        incomplete_legacy = [
            contract.legacy_id
            for contract in legacy_contracts
            if not isinstance(contract.payload, dict)
            or not isinstance(contract.payload.get('runtime_contract'), dict)
        ]
        if incomplete_legacy:
            raise CommandError(
                f'Free-Runtime-Verträge unvollständig: {incomplete_legacy}'
            )
        free_probe = next(
            (contract for contract in legacy_contracts if contract.legacy_id == 'chat_sum'),
            None,
        )
        if not free_probe:
            raise CommandError('Free-Runtime-Probe chat_sum fehlt.')
        free_result = compose_free_legacy(
            contract=free_probe,
            microsoft_tier='chatbasic',
            payload={
                'primary': 'Runtime-Validator',
                'secondary': 'Free-Datenbankprobe',
                'audience': 'self',
                'focus': ['Kernaussagen'],
                'output': 'bullets',
                'tone': 'professional',
                'detail': 'short',
            },
        )
        if (
            not free_result.get('ready')
            or free_result.get('source') != 'PromptLegacyContract'
            or 'Free-Datenbankprobe' not in free_result.get('prompt', '')
        ):
            raise CommandError(f'Free-Datenbankkomposition fehlerhaft: {free_result}')

        failed = []
        cases = PromptTestCase.objects.filter(
            name='system-smoke', enabled=True, version__lifecycle='PUBLISHED'
        ).select_related('version__definition')
        for case in cases.iterator():
            state = run_test_case(case)
            if state != 'PASSED':
                failed.append((case.version.definition.task_id, state, case.last_error))
                if len(failed) >= 10:
                    break
        if failed:
            raise CommandError(f'Prompt-Smoke-Tests fehlgeschlagen: {failed}')

        if FAQEntry.objects.filter(audience='public', active=True).count() < 6:
            raise CommandError('Zentrale FAQ wurde nicht vollständig geseedet.')

        raw, hashed = token_pair()
        account = ServiceAccount.objects.create(
            name=f'runtime-validator-{uuid.uuid4()}',
            token_hash=hashed,
            scopes=['ops.read', 'prompt.read', 'prompt.draft', 'prompt.test'],
        )
        try:
            host = next((value for value in settings.ALLOWED_HOSTS if value not in {'*', ''}), 'localhost')
            client = Client(HTTP_HOST=host, HTTP_AUTHORIZATION=f'Bearer {raw}')
            health = client.get('/api/v1/mcp/health/')
            if health.status_code != 200 or health.json().get('status') != 'ok':
                raise CommandError(f'MCP health fehlgeschlagen: {health.status_code} {health.content[:500]!r}')
            initialize = client.post(
                '/api/v1/mcp/',
                data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}),
                content_type='application/json',
            )
            if initialize.status_code != 200:
                raise CommandError(f'MCP initialize fehlgeschlagen: {initialize.status_code}')
            tools = client.post(
                '/api/v1/mcp/',
                data=json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}),
                content_type='application/json',
            )
            names = {row['name'] for row in tools.json().get('result', {}).get('tools', [])}
            if names != {'prompt.read', 'prompt.draft', 'prompt.test'}:
                raise CommandError(f'MCP Tools unerwartet: {sorted(names)}')
            faq = client.get('/api/v1/content/faqs/')
            if faq.status_code != 200 or faq.json().get('count', 0) < 6:
                raise CommandError('FAQ API fehlgeschlagen.')
        finally:
            account.delete()

        self.stdout.write(self.style.SUCCESS('PROMPT RUNTIME VALIDATION OK: 34 apps / 194 PM20 + 33 Free-surface = 227 Pro tasks / 194 PM20 smoke tests / MCP / FAQ'))
