#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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

# Build-Artefakte, die durch CI/Build-Prozesse reproduzierbar neu erzeugt
# werden und deshalb nicht gegen einen statischen Manifest-Hash geprüft
# werden dürfen.
VOLATILE_PREFIXES = (
    'marketing/dist/',
)


def relative_name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def ignored(path: Path) -> bool:
    """
    Ignore environment-, dependency- and cache-specific files.
    """
    if bool(IGNORED_PARTS.intersection(path.parts)):
        return True

    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True

    return False


def volatile(rel: str) -> bool:
    """
    Return True for reproducible/generated build artifacts whose content
    may legitimately change after a build during CI.

    These files may remain present in FILE_MANIFEST.tsv for inventory
    purposes, but they are deliberately excluded from byte/hash drift
    validation.
    """
    return any(
        rel.startswith(prefix)
        for prefix in VOLATILE_PREFIXES
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open('rb') as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b'',
        ):
            h.update(chunk)

    return h.hexdigest()


# ---------------------------------------------------------------------------
# Load expected manifest
# ---------------------------------------------------------------------------

if not TSV.exists():
    raise SystemExit(
        'MANIFEST VALIDATION FAIL: FILE_MANIFEST.tsv missing'
    )

expected: dict[str, tuple[int, str, str]] = {}

for line in TSV.read_text(
    encoding='utf-8'
).splitlines()[1:]:

    if not line.strip():
        continue

    try:
        path, size, digest, role = line.split('\t', 3)
    except ValueError as exc:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: malformed manifest row: {line}'
        ) from exc

    expected[path] = (
        int(size),
        digest,
        role,
    )


# ---------------------------------------------------------------------------
# Validate repository files
# ---------------------------------------------------------------------------

actual_paths: list[str] = []

for path in sorted(ROOT.rglob('*')):

    if not path.is_file():
        continue

    if ignored(path):
        continue

    if path.resolve() in EXCLUDED:
        continue

    rel = relative_name(path)

    # marketing/dist is generated during the CI build. Its correctness is
    # validated by the dedicated marketing validators/browser smoke tests.
    # Do not compare generated output with a historical manifest checksum.
    if volatile(rel):
        continue

    actual_paths.append(rel)

    row = expected.get(rel)

    if not row:
        raise SystemExit(
            f'MANIFEST VALIDATION FAIL: unlisted file {rel}'
        )

    size, digest, _role = row

    actual_size = path.stat().st_size

    if actual_size != size:
        raise SystemExit(
            'MANIFEST VALIDATION FAIL: '
            f'size drift {rel} '
            f'(expected {size}, actual {actual_size})'
        )

    actual_digest = sha256(path)

    if actual_digest != digest:
        raise SystemExit(
            'MANIFEST VALIDATION FAIL: '
            f'hash drift {rel}'
        )


# ---------------------------------------------------------------------------
# Detect files listed in the manifest but missing from the repository
#
# Volatile build artifacts are intentionally ignored here as well because
# they can be created/removed/rebuilt as part of CI.
# ---------------------------------------------------------------------------

expected_nonvolatile = {
    path
    for path in expected
    if not volatile(path)
}

extra = sorted(
    expected_nonvolatile - set(actual_paths)
)

if extra:
    raise SystemExit(
        'MANIFEST VALIDATION FAIL: missing files '
        + ', '.join(extra[:20])
    )


print(
    'MANIFEST VALIDATION OK: '
    f'{len(actual_paths)} stable files checked; '
    'generated marketing/dist artifacts excluded from hash drift validation'
)