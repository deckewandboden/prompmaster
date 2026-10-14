#!/usr/bin/env python3
"""Sandbox tests for the production launcher; never talks to real Docker."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name('go_live.sh')
SHA = 'a42e69f2dac0991bc01f93700174e48e05af9de3'


class GoLiveContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = root = Path(self.temp.name)
        (root / 'scripts').mkdir()
        (root / 'bin').mkdir()
        shutil.copyfile(SOURCE, root / 'scripts' / 'go_live.sh')
        (root / '.env').write_text('ENVIRONMENT=production\n')
        (root / '.env').chmod(0o600)
        (root / 'scripts' / 'deploy.sh').write_text('#!/bin/bash\nprintf "MOCK_DEPLOY_INVOKED GIT_SHA=%s\\n" "$GIT_SHA"\n')
        mocks = {
            'git': '''#!/bin/bash
case "$*" in
  'rev-parse --show-toplevel') printf '%s\\n' "$PM_TEST_ROOT" ;;
  'branch --show-current') printf '%s\\n' "${PM_TEST_BRANCH:-main}" ;;
  'rev-parse HEAD') printf '%s\\n' "${PM_TEST_HEAD:-$PM_RELEASE_SHA}" ;;
  'rev-parse refs/remotes/origin/main') printf '%s\\n' "${PM_TEST_REMOTE_HEAD:-$PM_RELEASE_SHA}" ;;
  'status --porcelain --untracked-files=no') printf '%s\\n' "${PM_TEST_STATUS:-}" ;;
  *) exit 99 ;;
esac
''',
            'docker': '#!/bin/bash\n[[ "$1 $2" == "compose version" ]]\n',
            'python3': '''#!/bin/bash
if [[ "$*" == "scripts/validate_env.py --environment production --require-go-live" ]]; then
  [[ "${PM_TEST_ENV_FAIL:-0}" == 0 ]]
elif [[ "$*" == "scripts/validate_env.py --environment production" ]]; then
  [[ "${PM_TEST_ENV_FAIL:-0}" == 0 ]]
elif [[ "$*" == scripts/offline_backup_go_live_gate.py* ]]; then
  [[ "${PM_TEST_OFFLINE_EVIDENCE_VALID:-0}" == 1 ]]
else
  exit 99
fi
''',
        }
        for name, contents in mocks.items():
            file = root / 'bin' / name
            file.write_text(contents)
            file.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update({
            'PATH': str(root / 'bin') + ':' + self.env['PATH'],
            'PM_TEST_ROOT': str(root),
            'PM_RELEASE_SHA': SHA,
            'PM_GO_LIVE_CONFIRM': SHA,
            'PM_STAGING_ACCEPTED_SHA': SHA,
            'PM_LEGAL_APPROVED': 'YES',
            'PM_TRANSLATION_APPROVED': 'YES',
            'PM_VISUAL_APPROVED': 'YES',
            'PM_PAYMENT_TEST_APPROVED': 'YES',
            'PM_EXECUTE_GO_LIVE': 'YES',
            'DOCKER_HOST': '',
            'DOCKER_CONTEXT': '',
        })

    def invoke(self, *args):
        return subprocess.run(['bash', str(self.root / 'scripts' / 'go_live.sh'), *args],
                              env=self.env, text=True, capture_output=True, timeout=8)

    def blocked(self, *args):
        response = self.invoke(*args)
        self.assertNotEqual(response.returncode, 0, response.stdout + response.stderr)
        self.assertNotIn('MOCK_DEPLOY_INVOKED', response.stdout)

    def test_verify_only_never_deploys(self):
        response = self.invoke('--verify-only')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn('NO_DEPLOY=YES', response.stdout)
        self.assertNotIn('MOCK_DEPLOY_INVOKED', response.stdout)

    def test_explicit_activation_uses_existing_deploy(self):
        response = self.invoke()
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn('MOCK_DEPLOY_INVOKED GIT_SHA=' + SHA, response.stdout)

    def test_inherited_stale_git_sha_cannot_mislabel_release(self):
        self.env['GIT_SHA'] = 'b' * 40
        response = self.invoke()
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn('MOCK_DEPLOY_INVOKED GIT_SHA=' + SHA, response.stdout)

    def test_requires_execution_approval(self):
        self.env.pop('PM_EXECUTE_GO_LIVE')
        self.blocked()

    def test_requires_exact_release_confirmation(self):
        self.env['PM_GO_LIVE_CONFIRM'] = 'YES'
        self.blocked()

    def test_requires_staging_approval_for_same_sha(self):
        self.env.pop('PM_STAGING_ACCEPTED_SHA')
        self.blocked()

    def test_rejects_wrong_head(self):
        self.env['PM_TEST_HEAD'] = 'b' * 40
        self.blocked()

    def test_rejects_unmerged_branch(self):
        self.env['PM_TEST_BRANCH'] = 'feature'
        self.blocked()

    def test_rejects_stale_remote_main(self):
        self.env['PM_TEST_REMOTE_HEAD'] = 'c' * 40
        self.blocked()

    def test_rejects_modified_sources(self):
        self.env['PM_TEST_STATUS'] = ' M backend/config/settings.py'
        self.blocked()

    def test_rejects_failed_external_backup_gate(self):
        self.env['PM_TEST_ENV_FAIL'] = '1'
        self.blocked()

    def test_rejects_remote_docker(self):
        self.env['DOCKER_HOST'] = 'ssh://other'
        self.blocked()

    def test_rejects_invalid_env_permissions(self):
        (self.root / '.env').chmod(0o644)
        self.blocked()

    def test_rejects_unrecognized_flags(self):
        self.blocked('--force')

    def test_all_four_explicit_approvals_are_required(self):
        for flag in ('PM_LEGAL_APPROVED', 'PM_TRANSLATION_APPROVED',
                     'PM_VISUAL_APPROVED', 'PM_PAYMENT_TEST_APPROVED'):
            with self.subTest(flag=flag):
                self.env[flag] = ''
                self.blocked()
                self.env[flag] = 'YES'


    def test_offsite_mode_requires_independent_restore_evidence(self):
        self.env['PM_OFFSITE_BACKUP_MODE'] = 'independent-offline'
        self.env['PM_TEST_OFFLINE_EVIDENCE_VALID'] = '0'
        self.blocked('--verify-only')

    def test_offsite_evidence_does_not_override_existing_approvals(self):
        self.env['PM_OFFSITE_BACKUP_MODE'] = 'independent-offline'
        self.env['PM_TEST_OFFLINE_EVIDENCE_VALID'] = '1'
        self.env.pop('PM_STAGING_ACCEPTED_SHA')
        self.blocked('--verify-only')

    def test_accepted_independent_offsite_mode_verifies_without_deploy(self):
        self.env['PM_OFFSITE_BACKUP_MODE'] = 'independent-offline'
        self.env['PM_TEST_OFFLINE_EVIDENCE_VALID'] = '1'
        self.env['PM_OFFSITE_RESTORE_REPORT'] = '/offhost/report.json'
        self.env['PM_OFFSITE_ARCHIVE_SHA256'] = 'a' * 64
        response = self.invoke('--verify-only')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn('NO_DEPLOY=YES', response.stdout)

    def test_offsite_mode_cannot_bypass_base_production_env(self):
        self.env['PM_OFFSITE_BACKUP_MODE'] = 'independent-offline'
        self.env['PM_TEST_OFFLINE_EVIDENCE_VALID'] = '1'
        self.env['PM_TEST_ENV_FAIL'] = '1'
        self.blocked('--verify-only')

    def test_unknown_offsite_mode_is_rejected(self):
        self.env['PM_OFFSITE_BACKUP_MODE'] = 'off'
        self.blocked('--verify-only')


if __name__ == '__main__':
    unittest.main(verbosity=2)
