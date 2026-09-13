#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'
BRIDGE = ROOT / 'product/runtime/pro_server_bridge.js'
RUNTIME = ROOT / 'backend/private_assets/promptmaster_pro_runtime.html'
SERVICE = ROOT / 'backend/apps/prompts/services.py'

catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
apps = catalog.get('APP') or {}
tasks = [task for app in apps.values() for task in (app.get('tasks') or [])]
ids = [str(task.get('id') or '') for task in tasks]
if (len(apps), len(tasks), len(set(ids))) != (34, 194, 194):
    raise SystemExit(f'RUNTIME CATALOG FAIL: expected 34/194/194, got {len(apps)}/{len(tasks)}/{len(set(ids))}')

missing_contract = []
for app_code, app in apps.items():
    for key in ('name', 'group', 'icon', 'color', 'copy', 'access', 'target', 'rule', 'tasks'):
        if key not in app:
            missing_contract.append(f'app {app_code}: {key}')
    for task in app.get('tasks') or []:
        for key in ('id', 'title', 'intent', 'required', 'optional', 'area', 'family', 'sources', 'outputs', 'focus', 'audiences'):
            if key not in task:
                missing_contract.append(f'task {task.get("id", "?")}: {key}')
if missing_contract:
    raise SystemExit('RUNTIME CATALOG FAIL: missing Golden contract fields: ' + ', '.join(missing_contract[:20]))

bridge = BRIDGE.read_text(encoding='utf-8')
for token in (
    '/api/v1/prompts/?product=PRO',
    'applyCentralCatalog',
    'centralRenderCatalog',
    'hydrateCentralCatalog',
    'clearObject(APP)',
    'clearObject(ACCESS_RULES)',
    'clearObject(TASK_ACCESS_RULES)',
):
    if token not in bridge:
        raise SystemExit(f'RUNTIME CATALOG FAIL: bridge token missing: {token}')
if "const core=['copilot_chat'" in bridge or "const more=['onenote'" in bridge:
    raise SystemExit('RUNTIME CATALOG FAIL: runtime bridge must not hard-code the old 16-app catalog')

service = SERVICE.read_text(encoding='utf-8')
for token in (
    "'application_count': len(applications)",
    "'task_count': task_count",
    "'required': [field.label",
    "'optional': [field.label",
    "'sources': option_values('source')",
    "'outputs': option_values('output')",
    "'focus': option_values('focus')",
    "'audiences': option_values('audience')",
):
    if token not in service:
        raise SystemExit(f'RUNTIME CATALOG FAIL: service contract missing: {token}')

subprocess.run(['node', '--check', str(BRIDGE)], check=True)
subprocess.run(['python', str(ROOT / 'scripts/build_pro_runtime.py'), '--check'], check=True)
runtime = RUNTIME.read_text(encoding='utf-8')
if 'hydrateCentralCatalog();' not in runtime:
    raise SystemExit('RUNTIME CATALOG FAIL: derived Pro runtime lacks central catalog bootstrap')
if runtime.count('/api/v1/prompts/?product=PRO') != 1:
    raise SystemExit('RUNTIME CATALOG FAIL: unexpected central catalog endpoint occurrence count')

print('RUNTIME CATALOG OK: authoritative server catalog bridge + 34 apps / 194 tasks')
