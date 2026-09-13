#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
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


def role(rel: Path) -> str:
    top = rel.parts[0] if rel.parts else ''
    return {
        'backend': 'active-backend',
        'marketing': 'active-marketing',
        'product': 'active-product',
        'scripts': 'active-operations',
        'backup': 'active-operations',
        'monitoring': 'active-operations',
        '.github': 'active-ci',
        'docs': 'documentation',
        'archive': 'historical-reference',
        'tools': 'recovery-tool',
    }.get(top, 'repository-root')


files = []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or ignored(path):
        continue
    if path.resolve() in EXCLUDED:
        continue
    rel = path.relative_to(ROOT)
    data = {
        'path': rel.as_posix(),
        'size': path.stat().st_size,
        'sha256': sha256(path),
        'role': role(rel),
    }
    files.append(data)

TSV.write_text(
    'path\tsize_bytes\tsha256\trole\n' + ''.join(
        f"{f['path']}\t{f['size']}\t{f['sha256']}\t{f['role']}\n" for f in files
    ),
    encoding='utf-8',
)
summary = Counter(f['role'] for f in files)
JSON_OUT.write_text(json.dumps({
    'project': 'PromptMaster Commercial RC14 Full Repository',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'file_count_excluding_manifest_files': len(files),
    'total_bytes_excluding_manifest_files': sum(f['size'] for f in files),
    'roles': dict(sorted(summary.items())),
    'files': files,
}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

groups = defaultdict(list)
for f in files:
    groups[f['role']].append(f)
lines = [
    '# Vollständiges Datei-Inventar — PromptMaster RC14', '',
    f"Erfasst: **{len(files)} Dateien** (Manifest-/Inventardateien selbst ausgenommen), **{sum(f['size'] for f in files):,} Byte**.", '',
    'Maschinenlesbar: `FILE_MANIFEST.tsv` und `MANIFEST.json`.', '',
]
for group in sorted(groups):
    items = groups[group]
    lines += [f'## {group}', '', f'{len(items)} Dateien.', '', '| Pfad | Größe | SHA256 |', '|---|---:|---|']
    for f in items:
        lines.append(f"| `{f['path']}` | {f['size']} | `{f['sha256']}` |")
    lines.append('')
MD.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'MANIFEST OK: {len(files)} files / {sum(f["size"] for f in files)} bytes')
