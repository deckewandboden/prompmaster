#!/usr/bin/env python3
"""Independent positive and negative tests; no Docker or production changes."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import offline_recovery_drill as drill


class OfflineRecoveryTests(unittest.TestCase):
    def test_original_absolute_sha256_path_works(self):
        with tempfile.TemporaryDirectory() as t:
            archive = Path(t) / "PROMPTFINISHER_FULL_test.tar.gz.gpg"
            archive.write_bytes(b"test")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            Path(str(archive) + ".sha256").write_text(
                digest + "  /root/promptfinisher-full-export/" + archive.name + "\n"
            )
            self.assertEqual(drill.sha_check(archive), digest)

    def test_wrong_checksum_and_wrong_archive_name_fail(self):
        with tempfile.TemporaryDirectory() as t:
            archive = Path(t) / "archive.tar.gz.gpg"
            archive.write_bytes(b"test")
            sha = Path(str(archive) + ".sha256")
            sha.write_text("f" * 64 + "  " + archive.name + "\n")
            with self.assertRaisesRegex(RuntimeError, "SHA256"):
                drill.sha_check(archive)
            sha.write_text(hashlib.sha256(b"test").hexdigest() + "  another.gpg\n")
            with self.assertRaisesRegex(RuntimeError, "anderen Archiv"):
                drill.sha_check(archive)

    def test_production_host_blocked_before_restore(self):
        def fake(cmd, **kwargs):
            if cmd == ["docker", "context", "inspect"]:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(
                    [{"Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}}}]), "")
            if cmd[:3] == ["docker", "ps", "-a"]:
                return subprocess.CompletedProcess(cmd, 0, "promptfinisher-postgres-1\n", "")
            raise AssertionError("Must never mutate Docker during host preflight: " + str(cmd))
        with patch.dict("os.environ", {"DOCKER_HOST": "", "DOCKER_CONTEXT": ""}):
            with patch.object(subprocess, "check_output",
                              side_effect=lambda c, **kw: fake(c, **kw).stdout):
                with self.assertRaisesRegex(RuntimeError, "PROMPTFINISHER-Container"):
                    drill.check_isolated_host()

    def test_remote_docker_refused(self):
        with patch.dict("os.environ", {"DOCKER_HOST": "ssh://production", "DOCKER_CONTEXT": ""}):
            with patch.object(subprocess, "check_output", side_effect=AssertionError("unwanted")):
                with self.assertRaisesRegex(RuntimeError, "Docker-Kontexte"):
                    drill.check_isolated_host()

    def test_gpg_real_encrypted_stream_and_manifest(self):
        if not drill.shutil.which("gpg"):
            self.skipTest("gpg absent")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "gpg-home").mkdir(mode=0o700)
            contents = {name: b"testfile" for name in drill.REQUIRED}
            contents[drill.PG] = b"mock-database"
            contents[drill.REDIS] = b"REDIS0011mock-data"
            contents["pf-export-state/git-head.txt"] = b"a" * 40 + b"\n"
            contents["pf-export-state/state-sha256.txt"] = (
                hashlib.sha256(contents[drill.PG]).hexdigest()
                + "  /root/secure/postgres.dump\n"
                + hashlib.sha256(contents[drill.REDIS]).hexdigest()
                + "  /root/secure/redis.rdb\n"
            ).encode()
            source = root / "archive.tar.gz"
            with tarfile.open(source, "w:gz") as archive:
                for name, data in contents.items():
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
            encrypted = root / "archive.tar.gz.gpg"
            subprocess.run(
                ["gpg", "--homedir", str(root / "gpg-home"), "--batch",
                 "--yes", "--pinentry-mode", "loopback", "--passphrase", "test-five",
                 "--cipher-algo", "AES256", "--symmetric",
                 "--output", str(encrypted), str(source)],
                check=True, capture_output=True, timeout=20)
            output = root / "out"
            output.mkdir()
            hashes = drill.decrypt_selected(encrypted, "test-five", output)
            self.assertEqual(set(hashes), drill.REQUIRED)
            self.assertEqual(drill.verify_state(output, hashes), "a" * 40)

    def test_modified_internal_dump_hash_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)
            (path / "state-sha256.txt").write_text("f" * 64 + "  /tmp/postgres.dump\n")
            with self.assertRaisesRegex(RuntimeError, "Interne Prüfsumme"):
                drill.verify_state(path, {drill.PG: "a" * 64})


if __name__ == "__main__":
    unittest.main(verbosity=2)
