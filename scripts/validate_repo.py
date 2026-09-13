#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = [
    'README.md', 'SPEC.md', 'AGENTS.md', '.env.example', '.gitignore',
    'compose.yaml', 'compose.staging.yaml', 'compose.production.yaml', 'Dockerfile', 'Dockerfile.caddy', 'Caddyfile',
    '.github/workflows/ci.yml',
    'backend/manage.py', 'backend/config/settings.py', 'backend/config/urls.py',
    'backend/apps/prompts/models.py', 'backend/apps/prompts/services.py', 'backend/apps/prompts/lifecycle.py',
    'backend/apps/prompts/quality.py', 'backend/apps/prompts/studio_views.py',
    'backend/apps/mcp_internal/views.py', 'backend/apps/contenthub/models.py',
    'product/golden_masters/promptmaster_free.html', 'product/golden_masters/promptmaster_pro.html',
    'scripts/bootstrap.sh', 'scripts/deploy.sh', 'scripts/runtime_validate.sh',
    'docs/SOURCE_OF_TRUTH.md', 'docs/RELEASE_GATES.md', 'docs/GITHUB_TRANSFER.md',
    'docs/COMPLETE_PROJECT_SUMMARY.md', 'docs/MERGE_PROVENANCE.md', 'docs/COMPLETE_FILE_INVENTORY.md',
    'FILE_MANIFEST.tsv', 'MANIFEST.json',
    'marketing/index.html', 'marketing/dist/index.html', 'marketing/public/models/head.glb',
    'archive/chat-transfer-2026-09-12/00_START_HERE.md', 'tools/recovery/v13-exact-exporter/PromptMaster_v13_EXAKT_exportieren.ps1',
]
missing = [name for name in required if not (ROOT / name).exists()]
if missing:
    raise SystemExit('REPO VALIDATION FAIL: missing ' + ', '.join(missing))

urls = (ROOT / 'backend/config/urls.py').read_text(encoding='utf-8')
for fragment in (
    "api/v1/prompts/", "api/v1/mcp/", "api/v1/content/", "ns-admin/prompt-studio/", "ns-admin/content/"
):
    if fragment not in urls:
        raise SystemExit(f'REPO VALIDATION FAIL: URL integration missing: {fragment}')

settings = (ROOT / 'backend/config/settings.py').read_text(encoding='utf-8')
for app in ('apps.prompts', 'apps.mcp_internal', 'apps.contenthub'):
    if app not in settings:
        raise SystemExit(f'REPO VALIDATION FAIL: INSTALLED_APPS missing {app}')

seed = (ROOT / 'backend/apps/core/management/commands/seed_defaults.py').read_text(encoding='utf-8')
for permission in ('prompts.read', 'prompts.write', 'prompts.compose', 'prompts.publish', 'prompts.quality', 'content.read', 'content.write'):
    if permission not in seed:
        raise SystemExit(f'REPO VALIDATION FAIL: permission missing {permission}')

# Repository safety guard: placeholders are fine in .env.example; actual
# high-risk credential patterns in tracked source are not.
secret_patterns = [
    re.compile(r'(?i)(mollie|graph|aws)[_-]?(api[_-]?key|client[_-]?secret)\s*[=:]\s*["\']?(live_|test_|eyJ|[A-Za-z0-9_\-]{32,})'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]
allowed_suffixes = {'.py', '.sh', '.yml', '.yaml', '.md', '.txt', '.json', '.html', ''}
for path in ROOT.rglob('*'):
    if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:
        continue
    if path.name == '.env.example':
        continue
    if path.suffix.lower() not in allowed_suffixes:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for pattern in secret_patterns:
        if pattern.search(text):
            raise SystemExit(f'REPO VALIDATION FAIL: possible credential in {path.relative_to(ROOT)}')

print('REPO VALIDATION OK: structure, routes, permissions, secret guard')
