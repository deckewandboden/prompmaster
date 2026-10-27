#!/usr/bin/env python3
"""Hermetic positive/negative contract tests for GitHub release launcher."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("release_from_github.sh")
SHA = "b" * 40
PREVIOUS = "a" * 40


class ReleaseFromGitHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "bin").mkdir()
        (self.root / ".git").mkdir()
        (self.root / "artifacts/deploy-state").mkdir(parents=True)
        shutil.copyfile(SOURCE, self.root / "scripts/release_from_github.sh")
        (self.root / ".env").write_text("ENVIRONMENT=production\nCADDY_DOMAIN=example.test\n")
        (self.root / ".env").chmod(0o600)
        (self.root / "artifacts/deploy-state/last-successful-sha").write_text(PREVIOUS + "\n")
        self.mock("git", r'''#!/bin/bash
case "$*" in
  "rev-parse --show-toplevel") echo "$PM_TEST_ROOT";;
  "branch --show-current") echo "${PM_TEST_BRANCH:-main}";;
  "status --porcelain --untracked-files=no") echo "${PM_TEST_DIRTY:-}";;
  "remote get-url origin") echo "${PM_TEST_ORIGIN:-git@github.com:deckewandboden/prompmaster.git}";;
  "rev-parse HEAD") echo "$PM_TEST_SHA";;
  "rev-parse refs/remotes/origin/main") echo "${PM_TEST_TARGET:-$PM_TEST_SHA}";;
  "fetch --no-tags origin main") echo "git-fetch" >> "$PM_TEST_ROOT/actions";;
  "merge-base --is-ancestor "*) [[ "${PM_TEST_DIVERGED:-0}" != 1 ]];;
  "merge --ff-only refs/remotes/origin/main") echo "git-fast-forward" >> "$PM_TEST_ROOT/actions";;
  *) echo "Unexpected git invocation: $*" >&2; exit 90;;
esac
''')
        self.mock("docker", r'''#!/bin/bash
[[ "$*" == "compose version" ]]
''')
        self.mock("curl", r'''#!/bin/bash
file=""
head=0
language=de
args=("$@")
for ((i=0;i<${#args[@]};i++)); do
  [[ "${args[$i]}" == "-o" ]] && file="${args[$((i+1))]}"
  [[ "${args[$i]}" == "-I" ]] && head=1
  if [[ "${args[$i]}" == "-H" && "${args[$((i+1))]}" == "Cookie: promptfinisher_language="* ]]; then
    language="${args[$((i+1))]#Cookie: promptfinisher_language=}"
  fi
done
url="${args[${#args[@]}-1]}"
if [[ "$head" == 1 ]]; then
  if [[ "${PM_TEST_BAD_CACHE:-0}" == 1 ]]; then
    printf 'HTTP/2 200\r\ncache-control: public, max-age=31536000, immutable\r\n'
  else
    printf 'HTTP/2 200\r\ncache-control: no-cache, must-revalidate\r\n'
  fi
  exit 0
fi
if [[ "$url" == *"/static/js/promptfinisher_product_i18n.20261011.js" ]]; then
  printf 'PROMPTFINISHER "de":{} "en":{} "es":{} "pt":{} "tr":{} "ru":{} "pl":{} "fr":{} "it":{}' > "$file"
  [[ "${PM_TEST_MISSING_LANGUAGE:-0}" == 1 ]] || printf ' "nl":{}' >> "$file"
elif [[ "$url" == *"/free/" ]]; then
  if [[ "${PM_TEST_MISMATCH_LANGUAGE:-}" == "$language" ]]; then language=de; fi
  printf '<html lang="%s"><script src="promptfinisher_product_i18n.20261011.js"></script></html>' "$language" > "$file"
else
  printf '<html>PROMPTFINISHER</html>' > "$file"
fi
if [[ "${PM_TEST_HTTP_FAIL:-0}" == 1 && "$url" == *"/free/" ]]; then
  printf '503'
else
  printf '200'
fi
''')
        (self.root / "scripts/deploy.sh").write_text(
            '#!/bin/bash\n'
            'echo "deploy:$GIT_SHA" >> "$PM_TEST_ROOT/actions"\n'
            'printf "%s\\n" "$GIT_SHA" > "$PM_TEST_ROOT/artifacts/deploy-state/last-successful-sha"\n'
        )
        self.env = {
            **os.environ,
            "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
            "PM_TEST_ROOT": str(self.root),
            "PM_TEST_SHA": SHA,
        }
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
            self.env.pop(key, None)

    def mock(self, name, text):
        path = self.root / "bin" / name
        path.write_text(text)
        path.chmod(0o755)

    def run_release(self, *args, **overrides):
        env = {**self.env, **{k: str(v) for k, v in overrides.items()}}
        return subprocess.run(
            ["bash", "scripts/release_from_github.sh", *args],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_verify_only_never_deploys(self):
        result = self.run_release("--verify-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NO_DEPLOY=YES", result.stdout)
        self.assertNotIn("deploy:", (self.root / "actions").read_text())
        self.assertEqual(
            (self.root / "artifacts/deploy-state/last-successful-sha").read_text().strip(),
            PREVIOUS,
        )

    def test_deploy_and_public_ten_language_acceptance(self):
        result = self.run_release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LANGUAGES=10", result.stdout)
        actions = (self.root / "actions").read_text()
        self.assertIn(f"deploy:{SHA}", actions)
        self.assertIn("git-fast-forward", actions)
        receipt = self.root / f"artifacts/deploy-state/github-release-verified-{SHA}.txt"
        self.assertTrue(receipt.is_file())
        self.assertIn("LIVE_HTTPS=PASS", receipt.read_text())
        self.assertIn("CHECKOUT_ACTIVATION=NOT_PERFORMED", receipt.read_text())

    def test_refuses_dirty_tree(self):
        self.assertEqual(self.run_release(PM_TEST_DIRTY=" M Dockerfile").returncode, 2)
        self.assertFalse((self.root / "actions").exists())

    def test_refuses_unapproved_origin(self):
        self.assertEqual(self.run_release(PM_TEST_ORIGIN="git@github.com:wrong/repo.git").returncode, 2)

    def test_refuses_diverged_main(self):
        self.assertEqual(self.run_release(PM_TEST_DIVERGED=1).returncode, 2)
        self.assertNotIn("deploy:", (self.root / "actions").read_text())

    def test_refuses_other_branch(self):
        self.assertEqual(self.run_release(PM_TEST_BRANCH="feature").returncode, 2)

    def test_refuses_remote_docker(self):
        self.assertEqual(self.run_release(DOCKER_HOST="tcp://untrusted:2375").returncode, 2)

    def test_refuses_missing_existing_release_marker(self):
        (self.root / "artifacts/deploy-state/last-successful-sha").unlink()
        self.assertEqual(self.run_release().returncode, 2)

    def test_refuses_insecure_environment(self):
        (self.root / ".env").chmod(0o644)
        self.assertEqual(self.run_release().returncode, 2)

    def test_refuses_http_failure_without_success_receipt(self):
        result = self.run_release(PM_TEST_HTTP_FAIL=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 503", result.stderr)
        self.assertFalse((self.root / f"artifacts/deploy-state/github-release-verified-{SHA}.txt").exists())

    def test_refuses_missing_locale_without_success_receipt(self):
        result = self.run_release(PM_TEST_MISSING_LANGUAGE=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing nl", result.stderr)
        self.assertFalse((self.root / f"artifacts/deploy-state/github-release-verified-{SHA}.txt").exists())

    def test_refuses_stale_asset_cache(self):
        result = self.run_release(PM_TEST_BAD_CACHE=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale-cache", result.stderr)

    def test_refuses_raw_free_language_mismatch_without_success_receipt(self):
        result = self.run_release(PM_TEST_MISMATCH_LANGUAGE='en')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Free raw HTML lang mismatch: en', result.stderr)
        self.assertFalse((self.root / f"artifacts/deploy-state/github-release-verified-{SHA}.txt").exists())

    def test_invalid_cli_does_not_deploy(self):
        result = self.run_release("--force")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "actions").exists())


if __name__ == "__main__":
    unittest.main()
