#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print('+', ' '.join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


checks = [
    ('python', 'scripts/validate_python_syntax.py'),
    ('python', 'scripts/validate_prompt_assets.py'),
    ('python', 'scripts/validate_prompt_domain.py'),
    ('python', 'scripts/validate_runtime_catalog.py'),
    ('python', 'scripts/validate_marketing.py'),
    ('python', 'scripts/validate_static.py'),
    ('python', 'scripts/validate_repo.py'),
    ('python', 'scripts/validate_manifest.py'),
]
for command in checks:
    run(*command)

for path in sorted((ROOT / 'scripts').glob('*.sh')) + sorted((ROOT / 'backup').glob('*.sh')):
    run('bash', '-n', str(path))

if (ROOT / '.git').exists():
    run('git', 'diff', '--check')
    proc = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    disallowed = []
    for line in proc.stdout.splitlines():
        rel = line[3:].strip()
        if rel in {'.env'} or rel.startswith('.env.') and rel != '.env.example':
            disallowed.append(rel)
        if '__pycache__' in rel or rel.endswith('.pyc'):
            disallowed.append(rel)
    if disallowed:
        raise SystemExit('GITHUB PREFLIGHT FAIL: untracked/generated secret/cache files: ' + ', '.join(disallowed))

print('GITHUB PREFLIGHT OK: static/code/assets/runtime-catalog/repository guards passed')
print('NOTE: Django/PostgreSQL/Docker runtime validation still requires a Docker-capable host or GitHub Actions.')
