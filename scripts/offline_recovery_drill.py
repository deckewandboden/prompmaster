#!/usr/bin/env python3
"""Independent, fail-closed restore test for a Windows-offloaded full GPG archive.

Never run on the production Docker host. Does not approve go-live by itself.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

PG = "pf-export-state/postgres.dump"
REDIS = "pf-export-state/redis.rdb"
REQUIRED = {
    PG, REDIS, "pf-export-state/state-sha256.txt",
    "pf-export-state/git-head.txt",
    "root/projekte/docker/promptmaster/.env",
    "root/projekte/docker/promptmaster/.git/HEAD",
    "root/projekte/docker/promptmaster/compose.yaml",
    "root/projekte/docker/promptmaster/Caddyfile.external",
    "var/lib/docker/volumes/promptmaster_backup_repository/_data/config",
}


def blocked(reason):
    raise RuntimeError("BLOCKED: " + reason)


def archive_creation_time(filename: str) -> dt.datetime:
    match = re.fullmatch(
        r"PROMPTFINISHER_FULL_(\d{8}T\d{6}Z)_[0-9a-f]{8}\.tar\.gz\.gpg",
        filename,
    )
    if match is None:
        blocked("Archivname ohne verifizierbares Erstellungsdatum")
    return dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
        tzinfo=dt.timezone.utc,
    )


def sha_check(archive):
    sidecar = Path(str(archive) + ".sha256")
    if any(p.is_symlink() or not p.is_file() for p in (archive, sidecar)):
        blocked("Archiv oder SHA256-Begleitdatei fehlt oder ist Symlink")
    line = sidecar.read_text(encoding="ascii").strip().split()
    if len(line) != 2 or not re.fullmatch(r"[a-fA-F0-9]{64}", line[0]):
        blocked("Ungültige SHA256-Begleitdatei")
    # Original server-generated sidecars may contain an absolute Linux path.
    if Path(line[1]).name != archive.name:
        blocked("SHA256-Begleitdatei gehört zu einem anderen Archiv")
    digest = hashlib.sha256()
    with archive.open("rb") as f:
        for piece in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(piece)
    if digest.hexdigest() != line[0].lower():
        blocked("SHA256 der Offline-Kopie stimmt nicht")
    return digest.hexdigest()


def check_isolated_host():
    if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
        blocked("Externe Docker-Kontexte sind verboten")
    context = json.loads(subprocess.check_output(["docker", "context", "inspect"], text=True))
    if len(context) != 1 or context[0]["Endpoints"]["docker"]["Host"] != "unix:///var/run/docker.sock":
        blocked("Kein lokaler Docker-Daemon")
    for command in (
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
    ):
        names = subprocess.check_output(command, text=True).splitlines()
        if any(name.startswith(("promptmaster_", "promptfinisher_", "promptmaster-", "promptfinisher-")) for name in names):
            blocked("PROMPTFINISHER-Container oder -Volumes gefunden: nur auf externem Recovery-Host testen")


def decrypt_selected(archive, password, workdir):
    command = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback",
               "--passphrase-fd", "0", "--decrypt", str(archive)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin and proc.stdout and proc.stderr
    proc.stdin.write(password.encode("utf-8") + b"\n")
    proc.stdin.close()
    found = {}
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|gz") as tar:
            for member in tar:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    blocked("Unsicherer TAR-Pfad")
                name = str(path)
                if name not in REQUIRED:
                    continue
                if name in found or not member.isfile():
                    blocked("Doppelter/ungültiger Pflichtbestandteil: " + name)
                stream = tar.extractfile(member)
                if stream is None:
                    blocked("Pflichtbestandteil nicht lesbar: " + name)
                dest = workdir / name.rsplit("/", 1)[-1]
                digest = hashlib.sha256()
                with dest.open("xb") as out:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        out.write(chunk)
                        digest.update(chunk)
                found[name] = digest.hexdigest()
        proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace")
        proc.stderr.close()
        if proc.wait(timeout=30):
            blocked("GPG-Entschlüsselung fehlgeschlagen: " + stderr[-300:])
    except Exception:
        proc.kill()
        proc.wait()
        raise
    missing = REQUIRED - set(found)
    if missing:
        blocked("Pflichtbestandteile fehlen: " + ", ".join(sorted(missing)))
    return found


def verify_state(workdir, hashes):
    lines = (workdir / "state-sha256.txt").read_text(encoding="utf-8").splitlines()
    for rel in (PG, REDIS):
        entry = next((line for line in lines if line.split() and Path(line.split()[-1]).name == Path(rel).name), "")
        if not entry or entry.split()[0].lower() != hashes[rel]:
            blocked("Interne Prüfsumme ungültig: " + rel)
    if not re.fullmatch(b"REDIS[0-9]{4}", (workdir / "redis.rdb").read_bytes()[:9]):
        blocked("Redis-Dump-Header ungültig")
    head = (workdir / "git-head.txt").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        blocked("Ungültige Projekt-Git-SHA im Archiv")
    return head


def restore_database(workdir):
    # No shared database volume, no published port, no external network.
    name = "pf-dr-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(25)
    started = False
    try:
        subprocess.run(["docker", "run", "-d", "--rm", "--network", "none", "--name", name,
                        "-e", "POSTGRES_PASSWORD=" + password, "postgres:18-alpine"],
                       check=True, stdout=subprocess.DEVNULL, timeout=120)
        started = True
        for _ in range(35):
            probe = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if probe.returncode == 0:
                break
            time.sleep(2)
        else:
            blocked("PostgreSQL-18-Wiederherstellungscontainer nicht bereit")
        subprocess.run(["docker", "cp", str(workdir / "postgres.dump"), name + ":/tmp/offline.dump"],
                       check=True, stdout=subprocess.DEVNULL, timeout=120)
        subprocess.run(["docker", "exec", name, "pg_restore", "--exit-on-error", "--single-transaction",
                        "--no-owner", "--no-acl", "-U", "postgres", "-d", "postgres",
                        "/tmp/offline.dump"], check=True, timeout=180)
        def count(sql):
            result = subprocess.check_output(["docker", "exec", name, "psql", "-X", "-U", "postgres",
                                              "-d", "postgres", "-At", "-c", sql],
                                             text=True, timeout=20)
            return int(result.strip())
        migrations = count("SELECT count(*) FROM django_migrations")
        tables = count("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        if min(migrations, tables) < 1:
            blocked("Datenbankwiederherstellung unvollständig")
        return migrations, tables
    finally:
        if started:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=25)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        if any(shutil.which(exe) is None for exe in ("docker", "gpg")):
            blocked("docker oder gpg fehlt")
        if args.report.exists() or args.report.is_symlink():
            blocked("Report-Datei existiert schon; Überschreiben verboten")
        check_isolated_host()
        archive_sha = sha_check(args.archive)
        secret = getpass.getpass("Archivpasswort (nicht sichtbar): ")
        if not secret:
            blocked("Archivpasswort leer")
        with tempfile.TemporaryDirectory(prefix="pf-offline-restore-") as tmp:
            os.chmod(tmp, 0o700)
            workdir = Path(tmp)
            hashes = decrypt_selected(args.archive, secret, workdir)
            secret = ""
            head = verify_state(workdir, hashes)
            migrations, tables = restore_database(workdir)
        archive_created = archive_creation_time(args.archive.name)
        report = {"result": "PASS", "scope": "isolated_postgresql_restore_and_archive_manifest",
                  "archive_sha256": archive_sha, "original_git_head": head,
                  "archive_created_at_utc": archive_created.isoformat(),
                  "migrations_count": migrations, "tables_count": tables,
                  "host": socket.gethostname(),
                  "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "limitations": "No full application startup, payment, visual or legal acceptance"}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as output:
            os.chmod(args.report, 0o600)
            json.dump(report, output, indent=2)
            output.write("\n")
        print("OFFLINE_RECOVERY_DRILL=PASS")
        print("OFFLINE_POSTGRES_18_ISOLATED_RESTORE=PASS")
        print("MIGRATIONS=" + str(migrations))
        print("EVIDENCE=" + str(args.report))
        print("PRODUCTION_UNCHANGED=YES")
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError,
            KeyError) as exc:
        print("OFFLINE_RECOVERY_DRILL=BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
