from threading import Barrier, Lock, Thread
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from . import lifecycle as lifecycle_module
from . import quality as quality_module
from .lifecycle import TestRunSummary, transition
from .models import (
    PromptApplication,
    PromptDefinition,
    PromptPolicySet,
    PromptQualityPolicy,
    PromptVersion,
)
from .quality import active_quality_policy


class PromptConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Concurrency contract is PostgreSQL-specific.')
        self.application = PromptApplication.objects.create(
            code='race-app',
            name='Race App',
            rule='Race rule',
        )
        self.policy = PromptPolicySet.objects.create(
            name='Race Policy',
            version=1,
            active=True,
            source_labels={},
            source_instructions={},
            method_rules={},
            quality_rules={},
            tone_rules={},
            detail_rules={},
            no_fabrication_rule='Keine Erfindungen.',
            source_sha256='a' * 64,
        )
        self.definition = PromptDefinition.objects.create(
            task_id='RACE-001',
            application=self.application,
            active=True,
        )

    def _version(self, number):
        return PromptVersion.objects.create(
            definition=self.definition,
            policy_set=self.policy,
            version=number,
            lifecycle='APPROVED',
            title=f'Race v{number}',
            family='analysis',
            intent='Concurrency test',
            app_rule_snapshot='Race rule',
            source_sha256=str(number) * 64,
        )

    def test_concurrent_publish_yields_one_published_and_one_controlled_conflict(self):
        first = self._version(1)
        second = self._version(2)
        barrier = Barrier(2)
        original_lock = lifecycle_module._lock_prompt_definition
        result_lock = Lock()
        results = []

        def synchronized_definition_lock(definition_id):
            barrier.wait(timeout=10)
            return original_lock(definition_id)

        def worker(version_id):
            close_old_connections()
            try:
                version = PromptVersion.objects.get(pk=version_id)
                transition(version, 'PUBLISHED')
                outcome = ('ok', '')
            except Exception as exc:  # captured for cross-thread assertion
                outcome = (type(exc).__name__, str(exc))
            finally:
                close_old_connections()
            with result_lock:
                results.append(outcome)

        with (
            patch(
                'apps.prompts.lifecycle._lock_prompt_definition',
                side_effect=synchronized_definition_lock,
            ),
            patch(
                'apps.prompts.lifecycle.run_version_tests',
                return_value=TestRunSummary(total=1, passed=1, failed=0, errors=0),
            ),
        ):
            threads = [
                Thread(target=worker, args=(first.pk,)),
                Thread(target=worker, args=(second.pk,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(PromptVersion.objects.filter(definition=self.definition, lifecycle='PUBLISHED').count(), 1)
        self.assertEqual(sum(1 for kind, _ in results if kind == 'ok'), 1)
        conflicts = [message for kind, message in results if kind == 'ValidationError']
        self.assertEqual(len(conflicts), 1)
        self.assertIn('Parallel-Publish', conflicts[0])

    def test_concurrent_first_quality_policy_access_returns_single_active_policy(self):
        PromptQualityPolicy.objects.all().delete()
        barrier = Barrier(2)
        original_create = quality_module._create_default_quality_policy
        result_lock = Lock()
        results = []
        errors = []

        def synchronized_create():
            barrier.wait(timeout=10)
            return original_create()

        def worker():
            close_old_connections()
            try:
                policy = active_quality_policy()
                with result_lock:
                    results.append(str(policy.pk))
            except Exception as exc:
                with result_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            'apps.prompts.quality._create_default_quality_policy',
            side_effect=synchronized_create,
        ):
            threads = [Thread(target=worker), Thread(target=worker)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(PromptQualityPolicy.objects.filter(active=True).count(), 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(set(results)), 1)
