#!/usr/bin/env python3
"""Verify that pm20_golden_logic.json is an exact extraction of approved Pro HTML.

No JavaScript runtime and no third-party parser are needed. Only the known
constant shapes in the approved Golden Master are parsed.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRO = ROOT / 'backend/private_assets/promptmaster_pro.html'
DATA = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'
EXPECTED_SHA = 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf'


def extract_object(text: str, name: str) -> str:
    m = re.search(rf'\bconst\s+{re.escape(name)}\s*=\s*', text)
    if not m:
        raise ValueError(f'const {name} not found')
    start = text.find('{', m.end())
    if start < 0:
        raise ValueError(f'const {name} has no object literal')
    depth = 0
    quote = None
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'", '`'}:
            quote = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError(f'const {name} object literal is unbalanced')


def quote_bare_keys(literal: str) -> str:
    return re.sub(
        r'([\{,]\s*)([A-Za-z_$][A-Za-z0-9_$-]*)(\s*:)',
        lambda m: f'{m.group(1)}"{m.group(2)}"{m.group(3)}',
        literal,
    )


def parse_json_or_bare(text: str, name: str):
    literal = extract_object(text, name)
    try:
        return json.loads(literal)
    except json.JSONDecodeError:
        return json.loads(quote_bare_keys(literal))


def parse_task_access(text: str) -> dict:
    literal = extract_object(text, 'TASK_ACCESS_RULES')
    result = {}
    for task_id, tier in re.findall(r"['\"](PM20-\d+)['\"]\s*:\s*\{\s*tier\s*:\s*(\d+)\s*\}", literal):
        result[task_id] = {'tier': int(tier)}
    return result


def main() -> int:
    actual_sha = hashlib.sha256(PRO.read_bytes()).hexdigest() if PRO.is_file() else ''
    if actual_sha != EXPECTED_SHA:
        print(f'[FAIL] Pro Golden Master hash: {actual_sha} != {EXPECTED_SHA}')
        return 1
    html = PRO.read_text(encoding='utf-8')
    stored = json.loads(DATA.read_text(encoding='utf-8'))
    extracted = {}
    for name in (
        'APP', 'SRC_LABEL', 'SRC_INSTRUCTION', 'METHOD', 'QUALITY', 'TONE', 'DETAIL',
        'M365_TIER', 'ACCESS_RULES', 'TASK_CONTEXT_SPEC',
    ):
        extracted[name] = parse_json_or_bare(html, name)
    extracted['TASK_ACCESS_RULES'] = parse_task_access(html)

    errors = []
    for name, value in extracted.items():
        if stored.get(name) != value:
            errors.append(name)
    if errors:
        print('[FAIL] Extracted Golden-Master constants differ:', ', '.join(errors))
        return 1

    app_count = len(extracted['APP'])
    task_count = sum(len(app.get('tasks') or []) for app in extracted['APP'].values())
    ctx_count = len(extracted['TASK_CONTEXT_SPEC'])
    meta = stored.get('_meta') or {}
    if (app_count, task_count, ctx_count) != (
        meta.get('application_count'), meta.get('task_count'), meta.get('context_spec_count')
    ):
        print('[FAIL] Extraction counts differ from metadata')
        return 1
    print(f'GOLDEN EXTRACTION OK: {app_count} apps / {task_count} tasks / {ctx_count} context specs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
