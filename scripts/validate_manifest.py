#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / 'FILE_MANIFEST.tsv'
JSON_OUT = ROOT / 'MANIFEST.json'
MD = ROOT / 'docs' / 'COMPLETE_FILE_INVENTORY.md'
EXCLUDED = {TSV.resolve(), JSON_OUT.resolve(), MD.resolve()}
IGNORED_PARTS = {'.git', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', '.venv', 'venv'}
IGNORED_SUFFIXES = {'.pyc', '.pyo'}


def ignored(path: Path) -> bool:
    return bool(IGNORED_PARTS.intersection(path.parts)) or path.suffix in IGNORED_SUFFIXES


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

expected = {}
for line in TSV.read_text(encoding='utf-8').splitlines()[1:]:
    if not line.strip():
        continue
    path, size, digest, role = line.split('\t', 3)
    expected[path] = (int(size), digest, role)
actual_paths = []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or ignored(path):
        continue
    if path.resolve() in EXCLUDED:
        continue
    rel = path.relative_to(ROOT).as_posix()
    actual_paths.append(rel)
    row = expected.get(rel)
    if not row:
        raise SystemExit(f'MANIFEST VALIDATION FAIL: unlisted file {rel}')
    size, digest, _role = row
    if path.stat().st_size != size:
        raise SystemExit(f'MANIFEST VALIDATION FAIL: size drift {rel}')
    if sha256(path) != digest:
        raise SystemExit(f'MANIFEST VALIDATION FAIL: hash drift {rel}')
extra = sorted(set(expected) - set(actual_paths))
if extra:
    raise SystemExit('MANIFEST VALIDATION FAIL: missing files ' + ', '.join(extra[:20]))
print(f'MANIFEST VALIDATION OK: {len(actual_paths)} files')
