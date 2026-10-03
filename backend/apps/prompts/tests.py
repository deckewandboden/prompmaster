import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import ProductEntitlement

from .composer_core import PromptValidationError, compose_prompt
from .free_surface import (
    FREE_SURFACE_ALIAS_TITLES,
    FREE_SURFACE_ALIAS_TO_PRO_ID,
    FREE_SURFACE_IDS,
    FREE_SURFACE_PRO_CONTRACTS,
    FREE_SURFACE_UNIQUE_IDS,
    FREE_TO_PRO_APP_CODE,
)
from .models import (
    MicrosoftCapability,
    MicrosoftTier,
    PromptApplication,
    PromptDefinition,
    PromptLegacyContract,
    PromptPolicySet,
    PromptVersion,
    PromptTestCase,
    PromptRating,
    PromptQualitySnapshot,
)
from .services import build_spec, catalog_snapshot, compose_task
from .lifecycle import clone_as_draft, transition
from .quality import save_rating


class ComposerCoreTests(SimpleTestCase):
    def _spec(self, *, context_template='Beschreibe „{Thema}“', required_tier=0, max_chars=None):
        return {
            'task_id': 'TEST-001',
            'application': {
                'code': 'test',
                'name': 'Test App',
                'rule': 'Nutze nur belegte Daten.',
                'minimum_tier_rank': required_tier,
            },
            'version': {
                'version': 3,
                'title': 'Test',
                'area': 'Test',
                'family': 'analysis',
                'intent': 'Analysiere den Sachverhalt.',
                'max_chars': max_chars,
                'context_template': context_template,
                'minimum_tier_rank': 0,
                'fields': [
                    {'label': 'Thema', 'kind': 'required', 'sort_order': 0, 'optional_fragment': ''},
                    {'label': 'Kontext', 'kind': 'optional', 'sort_order': 0, 'optional_fragment': '; Kontext „{value}“'},
                ],
                'options': [
                    {'kind': 'source', 'value': 'provided', 'label': 'Bereitgestellt', 'sort_order': 0},
                    {'kind': 'output', 'value': 'Bericht', 'label': 'Bericht', 'sort_order': 0},
                    {'kind': 'focus', 'value': 'Risiken', 'label': 'Risiken', 'sort_order': 0},
                    {'kind': 'audience', 'value': 'Management', 'label': 'Management', 'sort_order': 0},
                ],
            },
            'policy': {
                'version': 2,
                'source_labels': {'provided': 'Bereitgestellt'},
                'source_instructions': {'provided': 'ausschließlich die bereitgestellten Inhalte'},
                'method_rules': {'analysis': ['Prüfe zuerst die Fakten.', 'Leite dann Schlüsse ab.']},
                'quality_rules': {'analysis': 'Trenne Fakten und Schlussfolgerungen.'},
                'tone_rules': {'professional': 'professionell, klar und präzise'},
                'detail_rules': {'standard': 'vollständig, aber ohne unnötige Detailtiefe'},
                'no_fabrication_rule': 'Erfinde keine Angaben.',
            },
        }

    def _payload(self):
        return {
            'microsoft_tier_rank': 0,
            'fields': {'Thema': 'Servicequalität', 'Kontext': 'B2B'},
            'audience': 'Management',
            'focus': ['Risiken'],
            'output': 'Bericht',
            'source': 'provided',
            'tone': 'professional',
            'detail': 'standard',
        }

    def test_composer_is_stateless_and_uses_context(self):
        result = compose_prompt(self._spec(), self._payload())
        self.assertIn('Beschreibe „Servicequalität“; Kontext „B2B“.', result.prompt)
        self.assertIn('Nutze nur belegte Daten.', result.prompt)
        self.assertEqual(result.progress_percent, 100)
        self.assertEqual(result.policy_version, 2)
        self.assertEqual(result.prompt_version, 3)

    def test_fallback_never_drops_fields_when_golden_context_is_missing(self):
        result = compose_prompt(self._spec(context_template=''), self._payload())
        self.assertIn('Thema: „Servicequalität“', result.prompt)
        self.assertIn('Kontext: „B2B“', result.prompt)

    def test_tier_is_enforced(self):
        with self.assertRaises(PromptValidationError) as ctx:
            compose_prompt(self._spec(required_tier=2), self._payload())
        self.assertEqual(ctx.exception.code, 'tier_required')

    def test_required_field_is_enforced(self):
        payload = self._payload()
        payload['fields'] = {}
        with self.assertRaises(PromptValidationError) as ctx:
            compose_prompt(self._spec(), payload)
        self.assertEqual(ctx.exception.code, 'required')

    def test_max_chars_is_hard_bound(self):
        result = compose_prompt(self._spec(max_chars=80), self._payload())
        self.assertLessEqual(len(result.prompt), 80)


class PromptDomainSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)

    def test_catalog_import_counts_are_exact(self):
        self.assertEqual(PromptApplication.objects.filter(active=True).count(), 34)
        self.assertEqual(PromptDefinition.objects.filter(active=True).count(), 194)
        self.assertEqual(PromptVersion.objects.filter(lifecycle='PUBLISHED').count(), 194)
        self.assertEqual(MicrosoftTier.objects.filter(active=True).count(), 3)
        self.assertEqual(MicrosoftCapability.objects.filter(active=True).count(), 22)
        self.assertEqual(PromptLegacyContract.objects.filter(source='FREE_1_2_4').count(), 16)
        self.assertEqual(PromptTestCase.objects.filter(name='system-smoke').count(), 194)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_runtime_validator_ignores_archived_smoke_tests(self):
        definition = PromptDefinition.objects.get(task_id='PM20-001')
        source = PromptVersion.objects.get(definition=definition, lifecycle='PUBLISHED')
        archived = clone_as_draft(definition, source=source)
        archived.lifecycle = 'ARCHIVED'
        archived.save(update_fields=['lifecycle', 'updated_at'])
        self.assertEqual(PromptTestCase.objects.filter(name='system-smoke', enabled=True).count(), 195)
        self.assertEqual(
            PromptTestCase.objects.filter(
                name='system-smoke',
                enabled=True,
                version__lifecycle='PUBLISHED',
            ).count(),
            194,
        )
        call_command('seed_faqs', verbosity=0)
        call_command('validate_prompt_runtime', verbosity=0)

    def test_current_pm20_is_fully_entitled_for_pro(self):
        enabled = ProductEntitlement.objects.filter(
            product__code='PRO', enabled=True, feature__code__startswith='prompt.task.'
        ).count()
        self.assertEqual(enabled, 194)

    def test_pro_catalog_is_full_runtime_contract(self):
        snapshot = catalog_snapshot('PRO')
        self.assertEqual(snapshot['application_count'], 34)
        self.assertEqual(snapshot['task_count'], 215)
        self.assertEqual(len(snapshot['applications']), 34)
        tasks = [task for app in snapshot['applications'] for task in app['tasks']]
        self.assertEqual(len(tasks), 215)
        self.assertTrue(all(task['promptmaster_entitled'] for task in tasks))
        task = next(task for task in tasks if task['id'] == 'PM20-001')
        self.assertEqual(task['required'], ['Fragestellung'])
        self.assertIn('Kontext', task['optional'])
        self.assertIn('Management', task['audiences'])
        self.assertIn('Primärquellen', task['focus'])
        self.assertIn('Fundierte Antwort', task['outputs'])
        self.assertIn('webwork', task['sources'])
        app = next(app for app in snapshot['applications'] if app['code'] == 'copilot_chat')
        self.assertIn('rule', app)
        self.assertIn('copy', app)
        self.assertIn('access', app)

    def test_pro_catalog_covers_free_surface_without_duplicate_cards(self):
        snapshot = catalog_snapshot('PRO')
        tasks = [task for app in snapshot['applications'] for task in app['tasks']]
        ids = [task['id'] for task in tasks]
        id_set = set(ids)

        self.assertEqual(len(FREE_SURFACE_IDS), 33)
        self.assertEqual(len(FREE_SURFACE_ALIAS_TO_PRO_ID), 12)
        self.assertEqual(len(FREE_SURFACE_UNIQUE_IDS), 21)
        self.assertTrue(FREE_SURFACE_UNIQUE_IDS.issubset(id_set))
        self.assertTrue(set(FREE_SURFACE_ALIAS_TO_PRO_ID.values()).issubset(id_set))
        self.assertFalse(set(FREE_SURFACE_ALIAS_TO_PRO_ID).intersection(id_set))
        self.assertEqual(len(ids), len(id_set))

        for surface_id, canonical_id in FREE_SURFACE_ALIAS_TO_PRO_ID.items():
            canonical = [task for task in tasks if task['id'] == canonical_id]
            self.assertEqual(len(canonical), 1, surface_id)
            self.assertIn(surface_id, canonical[0].get('surface_aliases') or [])
            self.assertEqual(canonical[0]['title'], FREE_SURFACE_ALIAS_TITLES[surface_id])
            self.assertTrue(canonical[0].get('canonical_title'))

        # Visible parity is stricter than executable parity: every title shown
        # on Free must be findable verbatim in the corresponding Pro app.
        pro_titles_by_app = {
            app['code']: {task['title'] for task in app['tasks']}
            for app in snapshot['applications']
        }
        expected_visible = []
        for contract in PromptLegacyContract.objects.filter(source='FREE_1_2_4'):
            expected_visible.append((
                FREE_TO_PRO_APP_CODE[contract.application_code],
                contract.title,
                contract.legacy_id,
            ))
        for surface_id, contract in FREE_SURFACE_PRO_CONTRACTS.items():
            expected_visible.append((contract['app_code'], contract['title'], surface_id))

        self.assertEqual(len(expected_visible), 33)
        for app_code, title, surface_id in expected_visible:
            self.assertIn(
                title,
                pro_titles_by_app[app_code],
                f'{surface_id} fehlt in Pro sichtbar als „{title}“.',
            )

        expected_surface_counts = {
            'copilot_chat': 1,
            'outlook': 9,
            'teams': 2,
            'word': 1,
            'excel': 4,
            'powerpoint': 4,
        }
        for app_code, expected in expected_surface_counts.items():
            app = next(app for app in snapshot['applications'] if app['code'] == app_code)
            inherited = [
                task for task in app['tasks']
                if task.get('surface_origin') == 'FREE_1_2_4'
            ]
            self.assertEqual(
                len(inherited),
                expected,
                f'{app_code} hat eine falsche Anzahl zusätzlicher Free-Funktionen in Pro.',
            )
            self.assertTrue(all(task['promptmaster_entitled'] for task in inherited))

    def test_free_catalog_is_visible_but_unmapped_tasks_are_not_silently_entitled(self):
        snapshot = catalog_snapshot('FREE')
        self.assertEqual(len(snapshot['applications']), 34)
        tasks = [task for app in snapshot['applications'] for task in app['tasks']]
        self.assertEqual(len(tasks), 194)
        self.assertFalse(any(task['promptmaster_entitled'] for task in tasks))

    def test_compose_pm20_001_uses_seeded_database_domain(self):
        result = compose_task(
            task_id='PM20-001',
            microsoft_tier='chatbasic',
            product_code='PRO',
            payload={
                'fields': {'Fragestellung': 'Wie verbessern wir Support?', 'Kontext': 'B2B'},
                'audience': 'Management',
                'focus': ['Primärquellen', 'Aktualität'],
                'output': 'Fundierte Antwort',
                'source': 'webwork',
                'tone': 'professional',
                'detail': 'standard',
            },
        )
        self.assertIn('Wie verbessern wir Support?', result.prompt)
        self.assertIn('B2B', result.prompt)
        self.assertEqual(result.progress_percent, 100)

    def test_task_level_microsoft_tier_is_enforced(self):
        with self.assertRaises(PromptValidationError) as ctx:
            compose_task(
                task_id='PM20-005',
                microsoft_tier='m365basic',
                product_code='PRO',
                payload={
                    'fields': {'Projekt / Thema': 'PROMPTFINISHER'},
                    'audience': 'Management',
                    'focus': ['Kernaussagen'],
                    'output': 'Statusbericht',
                    'source': 'work',
                    'tone': 'professional',
                    'detail': 'standard',
                },
            )
        self.assertEqual(ctx.exception.code, 'tier_required')

    def test_prompt_version_pins_policy_and_application_rule_snapshot(self):
        spec = build_spec('PM20-001')
        version = PromptVersion.objects.get(definition__task_id='PM20-001', lifecycle='PUBLISHED')
        self.assertEqual(spec['policy']['version'], version.policy_set.version)
        original_rule = spec['application']['rule']
        version.definition.application.rule = 'NEUE APP-REGEL, DIE ALTE VERSION NICHT VERÄNDERN DARF'
        version.definition.application.save(update_fields=['rule', 'updated_at'])
        self.assertEqual(build_spec('PM20-001')['application']['rule'], original_rule)

    def test_reseed_does_not_reactivate_v1_over_newer_published_version(self):
        definition = PromptDefinition.objects.get(task_id='PM20-001')
        v1 = PromptVersion.objects.get(definition=definition, version=1)
        v1.lifecycle = 'ARCHIVED'
        v1.save(update_fields=['lifecycle', 'updated_at'])
        PromptPolicySet.objects.filter(active=True).update(active=False)
        policy2 = PromptPolicySet.objects.create(
            name='Test Policy',
            version=2,
            active=True,
            source_labels={},
            source_instructions={},
            method_rules={},
            quality_rules={},
            tone_rules={},
            detail_rules={},
            no_fabrication_rule='Keine Erfindungen.',
            source_sha256='f' * 64,
        )
        PromptVersion.objects.create(
            definition=definition,
            policy_set=policy2,
            version=2,
            lifecycle='PUBLISHED',
            title='Neue freigegebene Version',
            family='analysis',
            intent='Test',
            source_sha256='f' * 64,
            app_rule_snapshot='Test',
            published_at=timezone.now(),
        )
        call_command('seed_prompt_catalog', verbosity=0)
        v1.refresh_from_db()
        policy2.refresh_from_db()
        self.assertEqual(v1.lifecycle, 'ARCHIVED')
        self.assertTrue(policy2.active)
        self.assertEqual(
            PromptVersion.objects.get(definition=definition, lifecycle='PUBLISHED').version,
            2,
        )


class PromptApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)
        cls.user = get_user_model().objects.create_user(
            email='prompt-api@example.invalid',
            password='TestPassword-12345!',
            first_name='Prompt',
            last_name='Tester',
        )

    def setUp(self):
        self.client = Client()
        self.user.two_factor_required = False
        self.user.save(update_fields=["two_factor_required"])
        self.client.force_login(self.user)
        session = self.client.session
        session["security_version"] = self.user.security_version
        session["two_factor_ok"] = True
        session.save()

    @patch('apps.prompts.api._require_pro_access')
    def test_pro_catalog_api_returns_central_catalog(self, access):
        response = self.client.get('/api/v1/prompts/?product=PRO')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['catalog']['application_count'], 34)
        self.assertEqual(body['catalog']['task_count'], 215)
        self.assertEqual(len(body['catalog']['applications']), 34)
        first_task = body['catalog']['applications'][0]['tasks'][0]
        self.assertIn('required', first_task)
        self.assertIn('optional', first_task)
        self.assertIn('audiences', first_task)
        self.assertIn('focus', first_task)
        self.assertIn('outputs', first_task)
        self.assertIn('sources', first_task)
        self.assertEqual(response['Cache-Control'], 'no-store')

    @patch('apps.prompts.api._require_pro_access')
    def test_every_free_surface_function_has_one_executable_pro_implementation(self, access):
        catalog = self.client.get('/api/v1/prompts/?product=PRO').json()['catalog']
        all_tasks = [
            task
            for app in catalog['applications']
            for task in app['tasks']
        ]
        by_id = {task['id']: task for task in all_tasks}
        coverage_ids = set(FREE_SURFACE_UNIQUE_IDS) | set(FREE_SURFACE_ALIAS_TO_PRO_ID.values())
        self.assertEqual(len(coverage_ids), 33)
        self.assertTrue(coverage_ids.issubset(by_id))
        self.assertFalse(set(FREE_SURFACE_ALIAS_TO_PRO_ID).intersection(by_id))

        for task_id in sorted(coverage_ids):
            task = by_id[task_id]
            fields = {
                label: f'Testwert für {label}'
                for label in task.get('required') or []
            }
            response = self.client.post(
                '/api/v1/prompts/compose/',
                data=json.dumps({
                    'product': 'PRO',
                    'task_id': task['id'],
                    'microsoft_tier': 'premium',
                    'input': {
                        'fields': fields,
                        'audience': (task.get('audiences') or ['Management'])[0],
                        'focus': (task.get('focus') or [])[:1],
                        'output': (task.get('outputs') or ['Ergebnis'])[0],
                        'source': (task.get('sources') or ['provided'])[0],
                        'tone': 'professional',
                        'detail': 'standard',
                    },
                }),
                content_type='application/json',
            )
            self.assertEqual(
                response.status_code,
                200,
                f"{task['id']} konnte in Pro nicht ausgeführt werden: {response.content!r}",
            )
            body = response.json()
            self.assertTrue(body['ok'], task['id'])
            self.assertTrue(body['result']['ready'], task['id'])
            self.assertTrue(body['result']['prompt'].strip(), task['id'])

    @patch('apps.prompts.api._require_pro_access')
    def test_compose_api_is_stateless(self, access):
        response = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps({
                'product': 'PRO',
                'task_id': 'PM20-001',
                'microsoft_tier': 'chatbasic',
                'input': {
                    'fields': {'Fragestellung': 'Was ist neu?', 'Kontext': 'PROMPTFINISHER'},
                    'audience': 'Management',
                    'focus': ['Primärquellen'],
                    'output': 'Fundierte Antwort',
                    'source': 'webwork',
                    'tone': 'professional',
                    'detail': 'standard',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertFalse(body['result']['persisted'])
        self.assertIn('Was ist neu?', body['result']['prompt'])
        self.assertEqual(response['Cache-Control'], 'no-store')

    @patch('apps.prompts.api._require_pro_access')
    def test_power_automate_sync_requires_both_systems_then_composes(self, access):
        base = {
            'product': 'PRO',
            'task_id': 'PM20-159',
            'microsoft_tier': 'premium',
            'input': {
                'fields': {'Quellsystem': 'Sage 100'},
                'audience': 'IT',
                'focus': ['Trigger'],
                'output': 'Integrationsflow',
                'source': 'product',
                'tone': 'professional',
                'detail': 'standard',
            },
        }
        missing = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps(base),
            content_type='application/json',
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()['error']['code'], 'required')
        self.assertEqual(missing.json()['error']['field'], 'Zielsystem')

        base['input']['fields']['Zielsystem'] = 'CRM'
        complete = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps(base),
            content_type='application/json',
        )
        self.assertEqual(complete.status_code, 200)
        body = complete.json()
        self.assertTrue(body['ok'])
        self.assertIn('Sage 100', body['result']['prompt'])
        self.assertIn('CRM', body['result']['prompt'])
        self.assertTrue(body['result']['ready'])

    def test_free_server_compose_reads_persisted_legacy_contract(self):
        base = {
            'product': 'FREE',
            'task_id': 'chat_sum',
            'microsoft_tier': 'chatbasic',
            'input': {
                'primary': 'Kernaussagen und nächste Schritte',
                'secondary': 'Testinhalt aus dem Free-Browser',
                'audience': 'self',
                'focus': ['Kernaussagen'],
                'output': 'bullets',
                'tone': 'professional',
                'detail': 'short',
            },
        }
        response = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps(base),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertTrue(body['result']['ready'])
        self.assertFalse(body['result']['persisted'])
        self.assertEqual(body['result']['source'], 'PromptLegacyContract')
        self.assertIn('Testinhalt aus dem Free-Browser', body['result']['prompt'])
        self.assertEqual(response['Cache-Control'], 'no-store')

        contract = PromptLegacyContract.objects.get(
            source='FREE_1_2_4',
            legacy_id='chat_sum',
        )
        payload = dict(contract.payload)
        runtime = dict(payload['runtime_contract'])
        runtime['intent'] = 'DB-PROBE: Dieser Text stammt aus dem gespeicherten Free-Vertrag.'
        payload['runtime_contract'] = runtime
        contract.payload = payload
        contract.save(update_fields=['payload', 'updated_at'])

        changed = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps(base),
            content_type='application/json',
        )
        self.assertEqual(changed.status_code, 200)
        self.assertIn('DB-PROBE:', changed.json()['result']['prompt'])

    def test_free_server_compose_returns_partial_prompt_until_required_input_is_complete(self):
        response = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps({
                'product': 'FREE',
                'task_id': 'chat_sum',
                'microsoft_tier': 'chatbasic',
                'input': {
                    'primary': '',
                    'secondary': 'Test',
                    'audience': '',
                    'focus': [],
                    'output': '',
                    'tone': '',
                    'detail': '',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertFalse(body['result']['ready'])
        self.assertEqual(body['result']['source'], 'PromptLegacyContract')
        self.assertGreater(len(body['result']['prompt']), 100)
        self.assertGreater(body['result']['progress_percent'], 0)
        self.assertLess(body['result']['progress_percent'], 100)

    def test_free_server_compose_word_rewrite_matches_live_configuration(self):
        response = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps({
                'product': 'FREE',
                'task_id': 'word_rewrite',
                'microsoft_tier': 'm365basic',
                'input': {
                    'primary': 'Text klarer formulieren',
                    'secondary': 'Zahlen und Namen unverändert lassen',
                    'audience': 'customer',
                    'focus': ['Verständlichkeit'],
                    'output': 'prose',
                    'tone': 'professional',
                    'detail': 'short',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertTrue(body['result']['ready'])
        self.assertEqual(body['result']['task_id'], 'word_rewrite')
        self.assertEqual(body['result']['source'], 'PromptLegacyContract')
        self.assertIn('Text klarer formulieren', body['result']['prompt'])
        self.assertIn('Zahlen und Namen unverändert lassen', body['result']['prompt'])


class InternalStaffPromptApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)
        cls.user = get_user_model().objects.create_user(
            email='internal-staff-prompt@example.invalid',
            password='Internal-Staff-Prompt-Password-2026!',
            first_name='Internal',
            last_name='Staff',
            is_staff=True,
            two_factor_required=True,
            totp_secret_enc='configured-for-test',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session['security_version'] = self.user.security_version
        session['two_factor_ok'] = True
        session.save()

    def test_staff_catalog_uses_internal_entitlement_without_customer_license(self):
        response = self.client.get('/api/v1/prompts/?product=PRO')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['catalog']['task_count'], 215)

    def test_staff_can_compose_without_customer_license_or_device(self):
        response = self.client.post(
            '/api/v1/prompts/compose/',
            data=json.dumps({
                'product': 'PRO',
                'task_id': 'PM20-001',
                'microsoft_tier': 'chatbasic',
                'input': {
                    'fields': {'Fragestellung': 'Interner Test', 'Kontext': 'netstyle'},
                    'audience': 'Management',
                    'focus': ['Primärquellen'],
                    'output': 'Fundierte Antwort',
                    'source': 'webwork',
                    'tone': 'professional',
                    'detail': 'standard',
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('Interner Test', response.json()['result']['prompt'])


class PromptStudioLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_prompt_catalog', verbosity=0)
        cls.user = get_user_model().objects.create_user(
            email='prompt-studio@example.invalid', password='TestPassword-12345!', first_name='Prompt', last_name='Manager'
        )

    def test_full_lifecycle_archives_previous_published_version(self):
        definition = PromptDefinition.objects.get(task_id='PM20-001')
        original = PromptVersion.objects.get(definition=definition, lifecycle='PUBLISHED')
        draft = clone_as_draft(definition, source=original)
        self.assertEqual(draft.test_cases.filter(enabled=True).count(), 1)
        draft = transition(draft, 'TEST')
        draft = transition(draft, 'REVIEW')
        draft = transition(draft, 'APPROVED')
        draft = transition(draft, 'PUBLISHED')
        original.refresh_from_db()
        self.assertEqual(draft.lifecycle, 'PUBLISHED')
        self.assertEqual(original.lifecycle, 'ARCHIVED')

    def test_low_rating_keeps_feedback_and_high_rating_clears_it(self):
        version = PromptVersion.objects.get(definition__task_id='PM20-001', lifecycle='PUBLISHED')
        rating, snapshot = save_rating(user=self.user, version=version, stars=2, feedback='Mehr Details nötig')
        self.assertEqual(rating.feedback, 'Mehr Details nötig')
        self.assertIsInstance(snapshot, PromptQualitySnapshot)
        rating, _ = save_rating(user=self.user, version=version, stars=5, feedback='muss verschwinden')
        self.assertEqual(rating.feedback, '')
        self.assertEqual(PromptRating.objects.filter(user=self.user, version=version).count(), 1)
