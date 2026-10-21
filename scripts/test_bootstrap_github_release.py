#!/usr/bin/env python3
"""Hermetic end-to-end integration tests for PUBLIC GitHub bootstrapping.

Actual Git repositories, Git stash, binary patch, bundle, fast-forward, and
synthetic HTTPS-to-file URL rewrites are used. No network or Docker required.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("bootstrap_github_release.sh")
PUBLIC = "https://github.com/deckewandboden/prompmaster.git"
SSH = "git@github.com:deckewandboden/prompmaster.git"


def git(root: Path, *args: str, env=None, check=True):
    process = subprocess.run(
        ["git", *args], cwd=root, env=env, text=True, capture_output=True,
        check=False, timeout=25,
    )
    if check and process.returncode:
        raise AssertionError(f"git {args} failed: {process.stderr}")
    return process.stdout.strip()


class GitHubBootstrapContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.live = self.base / "live"
        self.writer = self.base / "writer"
        self.rescue = self.base / "rescue"

        self.remote.mkdir()
        git(self.remote, "init", "--bare", "--initial-branch=main")
        git(self.base, "clone", str(self.remote), str(self.live))
        git(self.live, "config", "user.name", "CI Test")
        git(self.live, "config", "user.email", "ci@example.test")
        (self.live / "scripts").mkdir()
        (self.live / ".gitignore").write_text(".env\nartifacts/\n", encoding="utf-8")
        (self.live / "scripts/release_from_github.sh").write_text(
            '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
            'git rev-parse HEAD > "$PM_TEST_RELEASE_MARKER"\n',
            encoding="utf-8",
        )
        (self.live / "branding.txt").write_text("Original branding\n", encoding="utf-8")
        (self.live / "brand.png").write_bytes(b"\x89PNG\r\n\x1a\noriginal-bytes")
        git(self.live, "add", ".")
        git(self.live, "commit", "-m", "initial")
        git(self.live, "push", "-u", "origin", "main")
        self.initial = git(self.live, "rev-parse", "HEAD")
        git(self.base, "clone", str(self.remote), str(self.writer))
        git(self.writer, "config", "user.name", "CI Test")
        git(self.writer, "config", "user.email", "ci@example.test")
        (self.writer / "remote-version.txt").write_text("New published UI languages\n", encoding="utf-8")
        git(self.writer, "add", ".")
        git(self.writer, "commit", "-m", "new GitHub release")
        git(self.writer, "push", "origin", "main")
        self.target = git(self.writer, "rev-parse", "HEAD")

        git(self.live, "remote", "set-url", "origin", SSH)
        (self.live / "artifacts/deploy-state").mkdir(parents=True)
        (self.live / "artifacts/deploy-state/last-successful-sha").write_text(self.initial)
        (self.live / ".env").write_text("ENVIRONMENT=production\nPRIVATE_TEST_SECRET=NEVER_BACKUP\n")
        (self.live / ".env").chmod(0o600)

        # Git's trusted URL rewrite maps the *fixed public HTTPS address* to
        # a local bare repository; no GitHub/network access is attempted.
        self.env = {
            **os.environ,
            "PM_GITHUB_RELEASE_ROOT": str(self.live),
            "PM_LOCAL_EDIT_RESCUE_DIR": str(self.rescue),
            "PM_TEST_RELEASE_MARKER": str(self.base / "release-performed"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{self.remote.as_uri()}.insteadOf",
            "GIT_CONFIG_VALUE_0": PUBLIC,
        }
        self.env.pop("DOCKER_HOST", None)
        self.env.pop("DOCKER_CONTEXT", None)

    def invoke(self, *args, **extra_env):
        env = {**self.env, **{key: str(value) for key, value in extra_env.items()}}
        return subprocess.run(
            ["bash", str(SOURCE), *args],
            cwd=self.base, env=env,
            text=True, capture_output=True, check=False, timeout=35,
        )

    def dirty(self):
        (self.live / "branding.txt").write_text("Local original custom branding\n")
        (self.live / "brand.png").write_bytes(b"\x89PNG\r\n\x1a\nCUSTOM-BINARY")
        (self.live / "secret-untracked.txt").write_text("Never touch untracked files\n")

    def test_dirty_source_is_preserved_and_https_release_runs(self):
        self.dirty()
        out = self.invoke()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("RESCUE=PASS", out.stdout)
        self.assertIn("GITHUB_BOOTSTRAP=PASS", out.stdout)
        self.assertEqual(git(self.live, "rev-parse", "HEAD"), self.target)
        self.assertEqual(git(self.live, "config", "--get", "remote.origin.url"), PUBLIC)
        self.assertEqual((self.base / "release-performed").read_text().strip(), self.target)
        self.assertEqual((self.live / "branding.txt").read_text(), "Original branding\n")
        self.assertEqual((self.live / "secret-untracked.txt").read_text(), "Never touch untracked files\n")
        self.assertFalse(git(self.live, "status", "--porcelain", "--untracked-files=no"))

        backups = list(self.rescue.glob("release-*"))
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertTrue((backup / "modified-tracked.patch").is_file())
        self.assertIn("Local original custom branding", (backup / "modified-tracked.patch").read_text())
        self.assertTrue((backup / "tracked-edits.bundle").is_file())
        self.assertIn("STASH_SHA=", (backup / "source-info.txt").read_text())
        self.assertEqual(
            git(self.live, "bundle", "verify", str(backup / "tracked-edits.bundle"), check=False) is not None,
            True,
        )
        stashed = git(self.live, "stash", "show", "--format=full", "--stat")
        self.assertIn("branding.txt", stashed)
        self.assertIn("brand.png", stashed)
        self.assertNotIn("PRIVATE_TEST_SECRET", (backup / "modified-tracked.patch").read_text())
        self.assertNotIn(".env", (backup / "modified-tracked-status.txt").read_text())

    def test_clean_source_updates_without_creating_stash(self):
        out = self.invoke()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("already clean", out.stdout)
        self.assertEqual(git(self.live, "rev-parse", "HEAD"), self.target)
        self.assertFalse(self.rescue.exists())
        self.assertEqual(git(self.live, "stash", "list"), "")

    def test_other_branch_stops_before_mutation(self):
        self.dirty()
        git(self.live, "switch", "-c", "wrong-branch")
        out = self.invoke()
        self.assertEqual(out.returncode, 2)
        self.assertIn("Only main", out.stderr)
        self.assertEqual(git(self.live, "config", "--get", "remote.origin.url"), SSH)
        self.assertIn("Local original custom branding", (self.live / "branding.txt").read_text())

    def test_unknown_origin_fails_closed(self):
        self.dirty()
        git(self.live, "remote", "set-url", "origin", "git@github.com:other/repo.git")
        out = self.invoke()
        self.assertEqual(out.returncode, 2)
        self.assertIn("Unexpected Git origin", out.stderr)
        self.assertFalse(self.rescue.exists())

    def test_missing_acceptance_marker_does_not_stash(self):
        self.dirty()
        (self.live / "artifacts/deploy-state/last-successful-sha").unlink()
        out = self.invoke()
        self.assertEqual(out.returncode, 2)
        self.assertIn("accepted existing deployment marker", out.stderr)
        self.assertEqual(git(self.live, "stash", "list"), "")

    def test_insecure_env_is_not_stashed(self):
        self.dirty()
        (self.live / ".env").chmod(0o644)
        out = self.invoke()
        self.assertEqual(out.returncode, 2)
        self.assertIn("not 0600", out.stderr)
        self.assertFalse(self.rescue.exists())

    def test_diverged_local_commit_is_not_reset(self):
        git(self.live, "config", "user.name", "Local")
        (self.live / "branding.txt").write_text("Locally committed changes\n")
        git(self.live, "add", "branding.txt")
        git(self.live, "commit", "-m", "local divergent change")
        local_sha = git(self.live, "rev-parse", "HEAD")
        out = self.invoke()
        self.assertEqual(out.returncode, 2)
        self.assertIn("diverged", out.stderr)
        self.assertEqual(git(self.live, "rev-parse", "HEAD"), local_sha)
        self.assertFalse(self.rescue.exists())

    def test_invalid_argument_rejected_without_touching_files(self):
        self.dirty()
        out = self.invoke("--force")
        self.assertEqual(out.returncode, 2)
        self.assertIn("No arguments", out.stderr)
        self.assertIn("Local original custom branding", (self.live / "branding.txt").read_text())


if __name__ == "__main__":
    unittest.main()
