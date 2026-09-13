#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'artifacts'}
errors = []
count = 0
for path in sorted(ROOT.rglob('*.py')):
    if any(part in SKIP for part in path.parts):
        continue
    count += 1
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except Exception as exc:
        errors.append(f'{path.relative_to(ROOT)}: {exc}')
if errors:
    print('PYTHON SYNTAX VALIDATION FAILED')
    print('\n'.join(errors))
    raise SystemExit(1)
print(f'PYTHON SYNTAX OK: {count} files')
