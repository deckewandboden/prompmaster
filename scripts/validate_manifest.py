#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TSV = ROOT / 'FILE_MANIFEST.tsv'
JSON_OUT = ROOT / 'MANIFEST.json'
MD = ROOT / 'docs' / 'COMPLETE_FILE_INVENTORY.md'

EXCLUDED = {
    TSV.resolve(),
    JSON_OUT.resolve(),
    MD.resolve(),
}

IGNORED_PARTS = {
    '.git',
    'node_modules',
    '__pycache__',
    '.pytest_cache',
    '.ruff_cache',
    '.mypy_cache',
    '.venv',
    'venv',
}

IGNORED_SUFFIXES = {
    '.pyc',
    '.pyo',
}

VOLATILE_PREFIXES = (
    'marketing/dist/',
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)

    return h.hexdigest()


def volatile(rel: str) -> bool:
    return any(
        rel.startswith(prefix)
        for prefix in VOLATILE_PREFIXES
    )


def ignored(path: Path) -> bool:
    if any(part in IGNORED_PARTS for part in path.parts):
        return True

    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True

    return False


def git_tracked_files() -> list[str]:
    """
    Manifest validation must validate the actual Git repository,
    not arbitrary local files that happen to exist beside it.
    """

    try:
        result = subprocess.run(
            ['git', 'ls-files', '-z'],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            'MANIFEST VALIDATION FAIL: unable to determine Git tracked files'
        ) from exc

    tracked: list[str] = []

    for raw in result.stdout.split(b'\0'):
        if not raw:
            continue

        tracked.append(
            raw.decode('utf-8', errors='surrogateescape')
        )

    return tracked


# ---------------------------------------------------------------------------
# Load manifest
# ---------------------------------------------------------------------------

if not TSV.exists():
    raise SystemExit(
        'MANIFEST VALIDATION FAIL: FILE_MANIFEST.tsv missing'
    )

expected: dict[str, tuple[int, str, str]] = {}

for line in TSV.read_text(encoding='utf-8').splitlines()[1:]:

    if not line.strip():
        continue

    try:
        rel, size, digest, role = line.split('\t', 3)
    except ValueError as exc:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: malformed row: {line}'
        ) from exc

    expected[rel] = (
        int(size),
        digest,
        role,
    )


# ---------------------------------------------------------------------------
# Only validate Git-tracked source files
# ---------------------------------------------------------------------------

tracked_files = git_tracked_files()

checked = 0

for rel in sorted(tracked_files):

    path = ROOT / rel

    if path.resolve() in EXCLUDED:
        continue

    if ignored(path):
        continue

    if volatile(rel):
        continue

    if not path.exists():
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: tracked file missing: {rel}'
        )

    if not path.is_file():
        continue

    row = expected.get(rel)

    if row is None:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: tracked file not listed: {rel}'
        )

    expected_size, expected_digest, _role = row

    actual_size = path.stat().st_size

    if actual_size != expected_size:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: size drift {rel}'
        )

    actual_digest = sha256(path)

    if actual_digest != expected_digest:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: hash drift {rel}'
        )

    checked += 1


# ---------------------------------------------------------------------------
# Inform about obsolete manifest rows instead of failing.
#
# These can exist because old local backup/archive files were previously
# included by the generator although they were never Git-tracked.
# ---------------------------------------------------------------------------

tracked_set = set(tracked_files)

obsolete = sorted(
    rel
    for rel in expected
    if rel not in tracked_set
    and not volatile(rel)
)

if obsolete:
    print(
        f'MANIFEST NOTICE: {len(obsolete)} non-Git manifest entries ignored'
    )


print(
    f'MANIFEST VALIDATION OK: '
    f'{checked} Git-tracked stable files checked'
)