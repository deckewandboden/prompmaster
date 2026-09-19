#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    ROOT / 'product/golden_masters/promptmaster_free.html': 'aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8',
    ROOT / 'product/golden_masters/promptmaster_pro.html': 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf',
    ROOT / 'backend/private_assets/promptmaster_pro.html': 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf',
    ROOT / 'backend/private_assets/promptmaster_free_reference.html': 'aada4fbb3461d3758c48ed808bf018716a53aa33baf81efb058412e63535b0a8',
    ROOT / 'backend/private_assets/promptmaster_pro_runtime.html': '4348a0a6c6f4aca1836f95cc5b481da5c36b68de6d2be1b520e20427188cd9c7',
}
for path, expected in EXPECTED.items():
    if not path.is_file():
        raise SystemExit(f'PROMPT ASSET FAIL: missing {path.relative_to(ROOT)}')
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f'PROMPT ASSET FAIL: {path.relative_to(ROOT)} {actual} != {expected}')

catalog_path = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'
free_path = ROOT / 'backend/apps/prompts/data/free_legacy_tasks.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
free = json.loads(free_path.read_text(encoding='utf-8'))
meta = catalog.get('_meta') or {}
apps = catalog.get('APP') or {}
tasks = [task for app in apps.values() for task in (app.get('tasks') or [])]
ids = [str(task.get('id')) for task in tasks]
if (len(apps), len(tasks), len(set(ids))) != (34, 194, 194):
    raise SystemExit(f'PROMPT ASSET FAIL: catalog counts {len(apps)}/{len(tasks)}/{len(set(ids))}')
if meta.get('source_sha256') != EXPECTED[ROOT / 'product/golden_masters/promptmaster_pro.html']:
    raise SystemExit('PROMPT ASSET FAIL: PM20 catalog source hash differs from Pro Golden Master')
if len(free.get('tasks') or []) != 16:
    raise SystemExit('PROMPT ASSET FAIL: Free legacy task count != 16')

free_bridge_path = ROOT / 'backend/static/js/free_catalog_bridge.20260918.js'
if not free_bridge_path.is_file():
    raise SystemExit('PROMPT ASSET FAIL: Free 34-app visibility bridge missing')
free_bridge = free_bridge_path.read_text(encoding='utf-8')
for marker in (
    "const LEGACY_APP_IDS=['chat','outlook','teams','word','excel','powerpoint']",
    "application_count",
    "count!==34",
    "extras.length!==28",
    "/api/v1/prompts/?product=FREE",
    "data-prolocked=\"1\"",
):
    if marker not in free_bridge:
        raise SystemExit(f'PROMPT ASSET FAIL: Free visibility bridge contract missing {marker!r}')

pro_bridge_path = ROOT / 'product/runtime/pro_server_bridge.js'
pro_bridge = pro_bridge_path.read_text(encoding='utf-8')
for marker in (
    'id="pmFeedbackReveal"',
    'Feedback ergänzen',
    'lastRatingStars>=1 && lastRatingStars<=3',
    "document.getElementById('pmFeedback').classList.add('hidden')",
):
    if marker not in pro_bridge:
        raise SystemExit(f'PROMPT ASSET FAIL: Pro rating feedback UX contract missing {marker!r}')

subprocess.run([sys.executable, str(ROOT / 'scripts/build_pro_runtime.py'), '--check'], check=True)
print('PROMPT ASSETS OK: immutable Free/Pro Golden Masters + Free 34-app/16-task visibility contract + deterministic Pro server runtime + 34 apps / 194 tasks')
