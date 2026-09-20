#!/usr/bin/env python3
"""Fail-closed static release validator for PromptMaster.

This is intentionally stricter than a syntax check. Runtime validation remains
in runtime_validate.sh, but a release cannot reach Docker if deterministic
repository invariants are already broken.
"""
from __future__ import annotations

import ast
import builtins
import symtable
import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


class ComposeLoader(yaml.SafeLoader):
    """Safe YAML loader with Docker Compose's local !override tag."""


def _construct_compose_override(loader, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return loader.construct_scalar(node)


ComposeLoader.add_constructor('!override', _construct_compose_override)


def fail(message: str):
    errors.append(message)


# 1) Every Python source must parse.
for path in sorted((ROOT / 'backend').rglob('*.py')) + sorted((ROOT / 'scripts').glob('*.py')):
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        fail(f'PY {path.relative_to(ROOT)}: {exc}')

# 2) Every shell script must pass bash -n.
for path in sorted(ROOT.rglob('*.sh')):
    proc = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True)
    if proc.returncode:
        fail(f'SH {path.relative_to(ROOT)}: {proc.stderr.strip()}')

# 3) Configuration files must parse as YAML.
yaml_files = [
    ROOT / 'compose.yaml', ROOT / 'compose.staging.yaml', ROOT / 'compose.production.yaml', ROOT / 'compose.external-caddy.yaml',
    ROOT / 'monitoring/prometheus.yml', ROOT / '.github/workflows/ci.yml',
]
for path in yaml_files:
    try:
        payload = yaml.load(path.read_text(encoding='utf-8'), Loader=ComposeLoader)
        if payload is None:
            fail(f'YAML empty: {path.relative_to(ROOT)}')
    except Exception as exc:
        fail(f'YAML {path.relative_to(ROOT)}: {exc}')

# 4) No unfinished markers in executable/product files.
markers = ('TODO_FATAL', 'FIXME_FATAL', 'NotImplementedError(')
for path in ROOT.rglob('*'):
    if path.is_file() and path.name != Path(__file__).name and path.suffix in {'.py', '.html', '.yaml', '.yml', '.sh'}:
        text = path.read_text(encoding='utf-8', errors='ignore')
        for marker in markers:
            if marker in text:
                fail(f'Unfinished marker {marker}: {path.relative_to(ROOT)}')

# 5) Compose security/reproducibility.
for path in [ROOT/'compose.yaml', ROOT/'compose.staging.yaml', ROOT/'compose.production.yaml']:
    text = path.read_text(encoding='utf-8')
    for bad in ('5432:5432', '6379:6379', '9090:9090', '9100:9100', '9187:9187'):
        if bad in text:
            fail(f'Public data/monitoring port {bad}: {path.name}')
    if re.search(r'image:\s*[^\n]+:latest\b', text):
        fail(f'Unpinned latest image: {path.name}')

compose = yaml.safe_load((ROOT/'compose.yaml').read_text())
services = (compose or {}).get('services', {})
required_services = {'postgres','redis','web','worker','beat','caddy','prometheus','node-exporter','cadvisor','postgres-exporter','backup'}
missing_services = required_services - set(services)
if missing_services:
    fail(f'Missing compose services: {sorted(missing_services)}')

# Monitoring trust-boundary invariants. These are intentionally explicit:
# cAdvisor remains privileged, but it must never become a public application
# endpoint and its host mounts must remain read-only.
def _network_names(service):
    networks = (service or {}).get('networks') or []
    return set(networks if isinstance(networks, list) else networks.keys())

for name in ('prometheus', 'cadvisor'):
    service = services.get(name, {})
    if service.get('ports'):
        fail(f'{name} must not publish host ports')
    if _network_names(service) != {'monitor'}:
        fail(f'{name} must be attached only to the internal monitor network')

cadvisor = services.get('cadvisor', {})
if cadvisor.get('privileged') is not True:
    fail('cadvisor trust-boundary contract expects privileged: true until a separately validated replacement exists')

required_cadvisor_mounts = {
    '/:/rootfs:ro',
    '/var/run:/var/run:ro',
    '/sys:/sys:ro',
    '/var/lib/docker/:/var/lib/docker:ro',
    '/dev/disk/:/dev/disk:ro',
}
cadvisor_mounts = set(cadvisor.get('volumes') or [])
missing_mounts = required_cadvisor_mounts - cadvisor_mounts
if missing_mounts:
    fail(f'cadvisor required read-only host mounts missing/changed: {sorted(missing_mounts)}')

for name in ('prometheus', 'node-exporter', 'cadvisor', 'postgres-exporter'):
    image = str((services.get(name) or {}).get('image') or '')
    tail = image.rsplit('/', 1)[-1]
    if not image or (':' not in tail and '@sha256:' not in image):
        fail(f'{name} image must be version-pinned')

# 6) Required release files.
required = [
    'backend/config/settings.py','backend/config/urls.py','backend/apps/core/datagrid.py',
    'backend/private_assets/promptmaster_pro.html',
    'backend/apps/payments/services.py','backend/apps/ops/api.py','backend/apps/proaccess/views.py',
    'backend/templates/portal/base.html','backend/templates/ns_admin/base.html',
    'backend/static/brand/promptmaster-logo-reference.png','scripts/runtime_validate.sh',
    'backend/apps/prompts/models.py','backend/apps/prompts/composer_core.py',
    'backend/apps/prompts/services.py','backend/apps/prompts/api.py','backend/apps/prompts/api_urls.py',
    'backend/apps/prompts/management/commands/seed_prompt_catalog.py',
    'backend/apps/prompts/data/pm20_golden_logic.json','backend/apps/prompts/data/free_legacy_tasks.json',
    'backend/apps/prompts/migrations/0001_initial.py','scripts/verify_golden_extraction.py','scripts/validate_prompt_domain.py',
    'docs/PROMPT_DOMAIN_AND_COMPOSER.md','docs/FREE_LEGACY_MAPPING_STATUS.md',
    'product/golden_masters/promptmaster_free.html','product/golden_masters/promptmaster_pro.html',
    'product/golden_masters/SHA256SUMS.txt',
    'SPEC.md','AGENTS.md','README.md',
]
for rel in required:
    if not (ROOT/rel).exists():
        fail(f'Missing {rel}')

# 7) Exact approved PromptMaster logo regression guard.
logo = ROOT/'backend/static/brand/promptmaster-logo-reference.png'
if logo.exists():
    data = logo.read_bytes()
    expected_sha = '5848c7bc83fa903f9eb2de1b8a3c8443a9dca937cf3659494d2db2d5a26ff231'
    if hashlib.sha256(data).hexdigest() != expected_sha:
        fail('PromptMaster logo hash differs from approved 239x47 reference')
    try:
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('not png')
        width, height = struct.unpack('>II', data[16:24])
        if (width, height) != (239, 47):
            fail(f'PromptMaster logo dimensions are {width}x{height}, expected 239x47')
    except Exception as exc:
        fail(f'Logo metadata invalid: {exc}')

css = (ROOT/'backend/static/css/app.css').read_text(encoding='utf-8')
for token in ('--button-h:40px', '.brand img{display:block;width:239px;height:47px', '.btn.sm{height:34px', '@media(max-width:700px)'):
    if token not in css:
        fail(f'Design-system invariant missing from app.css: {token}')

# 8) Every model app must have concrete initial migrations; migration CreateModel
# names must cover all concrete model classes defined by that app.
for models_path in sorted((ROOT/'backend/apps').glob('*/models.py')):
    app = models_path.parent.name
    tree = ast.parse(models_path.read_text(encoding='utf-8'))
    model_names = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name not in {'TimeStampedModel', 'AppendOnlyQuerySet'}:
            bases = {getattr(base, 'id', '') or getattr(base, 'attr', '') for base in node.bases}
            # Project model files contain only Django models plus helper queryset.
            if node.name.endswith(('QuerySet', 'Manager')):
                continue
            model_names.append(node.name)
    if not model_names:
        continue
    migration_files = sorted((models_path.parent/'migrations').glob('[0-9][0-9][0-9][0-9]_*.py'))
    if not migration_files:
        fail(f'{app}: models exist but no concrete migration exists')
        continue
    migration_text = '\n'.join(p.read_text(encoding='utf-8') for p in migration_files)
    created = set(re.findall(r"CreateModel\(\s*name=['\"]([^'\"]+)", migration_text))
    for name in model_names:
        if name not in created:
            fail(f'{app}: model {name} missing from migrations')

# 9) Template route names must exist in the named URL namespace.
def names_from(path: Path):
    if not path.exists(): return set()
    return set(re.findall(r"name\s*=\s*['\"]([A-Za-z0-9_:-]+)['\"]", path.read_text(encoding='utf-8')))
url_names = {
    'accounts': names_from(ROOT/'backend/apps/accounts/urls.py'),
    'portal': names_from(ROOT/'backend/apps/companies/portal_urls.py'),
    'ns_admin': names_from(ROOT/'backend/apps/core/admin_urls.py'),
    'payments': names_from(ROOT/'backend/apps/payments/webhook_urls.py'),
    'proaccess': names_from(ROOT/'backend/apps/proaccess/urls.py'),
    'ops_api': names_from(ROOT/'backend/apps/ops/api_urls.py'),
    'content_admin': names_from(ROOT/'backend/apps/contenthub/admin_urls.py'),
    'prompt_studio': names_from(ROOT/'backend/apps/prompts/studio_urls.py'),
}
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for namespace, name in re.findall(r"{%\s*url\s+['\"]([A-Za-z0-9_]+):([A-Za-z0-9_]+)['\"]", text):
        if namespace in url_names and name not in url_names[namespace]:
            fail(f'{template.relative_to(ROOT)} references missing URL {namespace}:{name}')

# 10) Every POST form in templates must contain csrf_token before its closing tag.
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for match in re.finditer(r'<form\b[^>]*method=["\']post["\'][^>]*>', text, flags=re.I):
        closing = text.find('</form>', match.end())
        if closing < 0 or '{% csrf_token %}' not in text[match.end():closing]:
            fail(f'{template.relative_to(ROOT)} has POST form without csrf_token')


# 10b) Responsive tables collapse into cards below 700px. Every real data
# cell therefore needs its own label once THEAD is hidden. Colspan-only empty
# state rows are exempt.
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    if '<table' not in text:
        continue
    for match in re.finditer(r'<td\b([^>]*)>', text, flags=re.I):
        attrs = match.group(1)
        if 'data-label=' in attrs or 'colspan=' in attrs:
            continue
        line = text.count('\n', 0, match.start()) + 1
        fail(
            f'{template.relative_to(ROOT)}:{line} table cell lacks data-label '
            'required by mobile card layout'
        )


# 10c) Literal design-system controls must use one of the defined visual
# variants. A naked .btn has no intended product color; unknown badge/alert
# variants are almost always stale prototype CSS names.
_allowed_button_variants = {'primary', 'secondary', 'danger'}
_allowed_badge_variants = {'ok', 'warn', 'bad', 'info', 'pro'}
_allowed_alert_variants = {'ok', 'info', 'warn', 'danger'}
_layout_utility_classes = {
    'mt-6', 'mt-8', 'mt-10', 'mt-12', 'mt-14', 'mt-16', 'mt-18',
    'mb-0', 'mb-14', 'd-block', 'd-inline', 'wrap-anywhere',
    'compact-actions', 'compact-checkbox', 'text-warn', 'pre-wrap',
}
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for match in re.finditer(r'class=["\']([^"\']+)["\']', text):
        raw = match.group(1)
        # Template-generated class strings are validated by their source logic,
        # not by this literal-token guard.
        if '{%' in raw or '{{' in raw:
            continue
        tokens = set(raw.split())
        line = text.count('\n', 0, match.start()) + 1
        if 'btn' in tokens and not (tokens & _allowed_button_variants):
            fail(
                f'{template.relative_to(ROOT)}:{line} naked/unknown button variant: {raw}'
            )
        if 'badge' in tokens:
            variants = tokens - {'badge'} - _layout_utility_classes
            if variants and not (variants & _allowed_badge_variants):
                fail(
                    f'{template.relative_to(ROOT)}:{line} unknown badge variant: {raw}'
                )
        if 'alert' in tokens:
            variants = tokens - {'alert'} - _layout_utility_classes
            if variants and not (variants & _allowed_alert_variants):
                fail(
                    f'{template.relative_to(ROOT)}:{line} unknown alert variant: {raw}'
                )

# 10d) Product templates must not depend on javascript: navigation.
# CSP/browser history can make those links unreliable; use named Django routes.
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    if re.search(r'''(?:href|action)\s*=\s*["']\s*javascript:''', text, flags=re.I):
        fail(f'{template.relative_to(ROOT)} contains javascript: navigation')


# 10e) Literal backend template classes must exist in the central stylesheet.
# Dynamic Django class expressions are validated by the narrower variant guards
# above. Literal classes are part of the shared design system and must never
# silently rely on stale prototype CSS.
_app_css = (ROOT/'backend/static/css/app.css').read_text(encoding='utf-8')
_defined_classes = set(re.findall(r'\.([A-Za-z_][A-Za-z0-9_-]*)', _app_css))
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for match in re.finditer(r'''class=["']([^"']+)["']''', text):
        raw = match.group(1)
        if '{%' in raw or '{{' in raw:
            continue
        line = text.count('\n', 0, match.start()) + 1
        for class_name in raw.split():
            if class_name not in _defined_classes:
                fail(
                    f'{template.relative_to(ROOT)}:{line} uses undefined literal '
                    f'CSS class: {class_name}'
                )


# 10f) Buttons must declare their behavior explicitly. Relying on the HTML
# default submit type makes refactors and nested-form mistakes unnecessarily risky.
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for match in re.finditer(r'<button\\b([^>]*)>', text, flags=re.I):
        if not re.search(r"""\\btype\\s*=\\s*["'](?:submit|button|reset)["']""", match.group(1), flags=re.I):
            line = text.count('\\n', 0, match.start()) + 1
            fail(f'{template.relative_to(ROOT)}:{line} button lacks explicit type')

# 10g) Layout belongs to the shared design system. Dynamic inline values used
# for charts/progress are allowed; literal one-off layout styles are not.
for template in sorted((ROOT/'backend/templates').rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for match in re.finditer(r"""\\sstyle\\s*=\\s*["']([^"']+)["']""", text, flags=re.I):
        value = match.group(1)
        if '{{' in value or '{%' in value:
            continue
        line = text.count('\\n', 0, match.start()) + 1
        fail(f'{template.relative_to(ROOT)}:{line} literal inline style must use shared CSS: {value}')

# 11) Security-critical implementation guards.
checks = {
 'backend/apps/accounts/models.py': ('security_version=models.PositiveBigIntegerField(default=1)',),
 'backend/apps/accounts/middleware.py': ("request.session.get('security_version')", 'user.totp_secret_enc'),
 'backend/apps/accounts/views.py': ("'sv': int(user.security_version)", 'bump_security_version(user)'),
 'backend/apps/devices/services.py': ('validate_device_token', 'has_current_term'),
 'backend/apps/proaccess/views.py': ('validate_device_token', 'active_product_assignment', 'HttpOnly' if False else 'httponly=True'),
 'backend/apps/payments/services.py': ('_provider_amount', 'processed_paid', 'select_for_update'),
 'backend/apps/core/datagrid.py': ('.distinct()', 'Spreadsheet programs may execute'),
}
for rel, tokens in checks.items():
    text=(ROOT/rel).read_text(encoding='utf-8')
    for token in tokens:
        if token not in text:
            fail(f'Security invariant missing {rel}: {token}')

# 12) Expected enterprise routes.
expected_admin = {'dashboard','search','more','customers','customer_detail','customer_portal_preview','private_customer_portal_preview','customer_users','customer_licenses','customer_devices','customer_orders','customer_payments','customer_emails','customer_audit','licenses','license_detail','license_refund','orders','order_detail','payments','products','product_edit','product_price_add','email','email_log','mollie','mollie_events','stats','ops','ops_services','ops_database','ops_backups','ops_restore_tests','ops_alerts','api','legal','audit','roles','settings'}
for name in sorted(expected_admin - url_names['ns_admin']): fail(f'Missing ns-admin route: {name}')
expected_portal={'dashboard','search','more','team','invitations','invite','licenses','buy','activate_my_pro','member_reactivate','renew','devices','orders','company','profile','security','help'}
for name in sorted(expected_portal-url_names['portal']): fail(f'Missing portal route: {name}')
expected_ops={'health','system','storage','database','services','backups','integrations','maintenance_snapshot'}
for name in sorted(expected_ops-url_names['ops_api']): fail(f'Missing Ops API route: {name}')

# 13) Staging and production deploy checks must stay explicit and fail closed.
bootstrap=(ROOT/'scripts/bootstrap.sh').read_text(encoding='utf-8')
if 'check --deploy || true' in bootstrap:
    fail('bootstrap ignores django check --deploy')
if 'Staging Security Check' not in bootstrap or 'check --deploy --fail-level ERROR' not in bootstrap:
    fail('bootstrap does not run the staging deploy/security check')
if 'assert_external_caddy_ports_closed' not in bootstrap or '.NetworkSettings.Ports' not in bootstrap:
    fail('bootstrap external-Caddy host-port gate is missing or not based on Docker bindings')
deploy_script=(ROOT/'scripts/deploy.sh').read_text(encoding='utf-8')
if 'check --deploy' not in deploy_script:
    fail('production deploy does not run django check --deploy')
if 'assert_external_caddy_ports_closed' not in deploy_script or '.NetworkSettings.Ports' not in deploy_script:
    fail('deploy external-Caddy host-port gate is missing or not based on Docker bindings')
if 'DEBUG=True' in (ROOT/'compose.production.yaml').read_text(encoding='utf-8'):
    fail('production compose enables DEBUG')

# 14) Pro Golden Master gate must be private. The final asset itself is checked by
# runtime_validate because it is a separately frozen product artifact.
settings_text=(ROOT/'backend/config/settings.py').read_text(encoding='utf-8')
if 'PRO_GOLDEN_MASTER_PATH' not in settings_text:
    fail('PRO_GOLDEN_MASTER_PATH setting missing')
if '/private_assets/' in (ROOT/'Caddyfile').read_text(encoding='utf-8'):
    fail('Caddy must not expose private_assets')

pro_asset = ROOT / 'backend/private_assets/promptmaster_pro.html'
approved_pro_sha = 'aa7b2da53ba3cbcf9874b9b6f7381ea4c3e86ee1f9c09db186cbec6876a3c9cf'
if pro_asset.exists() and hashlib.sha256(pro_asset.read_bytes()).hexdigest() != approved_pro_sha:
    fail('PromptMaster Pro Golden Master hash differs from approved 2026-09-12 artifact')



# 15) Every literal template reference must resolve to an existing template.
template_root = ROOT / 'backend/templates'
template_names = {
    str(path.relative_to(template_root)).replace('\\', '/')
    for path in template_root.rglob('*.html')
}
for path in sorted((ROOT / 'backend').rglob('*.py')):
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except Exception:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = getattr(node.func, 'id', '') or getattr(node.func, 'attr', '')
        if func_name == 'render' and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            name = node.args[1].value
            if name not in template_names:
                fail(f'{path.relative_to(ROOT)} renders missing template: {name}')

for template in sorted(template_root.rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for name in re.findall(r"{%\s*(?:extends|include)\s+['\"]([^'\"]+)['\"]", text):
        if name not in template_names:
            fail(f'{template.relative_to(ROOT)} references missing template: {name}')

# 16) Catch unresolved Python globals which AST syntax parsing alone misses.
_builtin_names = set(dir(builtins)) | {'__name__', '__file__', '__package__', '__doc__'}
for path in sorted((ROOT / 'backend').rglob('*.py')) + sorted((ROOT / 'scripts').glob('*.py')):
    try:
        source = path.read_text(encoding='utf-8')
        table = symtable.symtable(source, str(path), 'exec')
    except (SyntaxError, UnicodeDecodeError):
        continue
    module_bound = set(_builtin_names)
    for symbol in table.get_symbols():
        if symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace():
            module_bound.add(symbol.get_name())
    def check_table(current):
        for symbol in current.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in module_bound:
                fail(f'{path.relative_to(ROOT)} unresolved global: {symbol.get_name()}')
        for child in current.get_children():
            check_table(child)
    for child in table.get_children():
        check_table(child)

# 17) Migration field coverage: all directly declared Django model fields must
# appear in CreateModel/AddField operations. This catches hand-written initial
# migrations that forgot a later model field.
for models_path in sorted((ROOT/'backend/apps').glob('*/models.py')):
    app = models_path.parent.name
    try:
        tree = ast.parse(models_path.read_text(encoding='utf-8'))
    except SyntaxError:
        continue
    declared = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name in {'TimeStampedModel', 'AppendOnlyQuerySet'} or node.name.endswith(('QuerySet', 'Manager')):
            continue
        fields = set()
        for stmt in node.body:
            targets = []
            value = None
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
                value = stmt.value
            if not isinstance(value, ast.Call):
                continue
            fn = getattr(value.func, 'attr', '') or getattr(value.func, 'id', '')
            if fn.endswith('Field') or fn in {'ForeignKey', 'OneToOneField', 'ManyToManyField'}:
                for target in targets:
                    if isinstance(target, ast.Name):
                        fields.add(target.id)
        if fields:
            declared[node.name] = fields
    migration_files = sorted((models_path.parent/'migrations').glob('[0-9][0-9][0-9][0-9]_*.py'))
    migrated = {name: set() for name in declared}
    for migration in migration_files:
        try:
            mtree = ast.parse(migration.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(mtree):
            if not isinstance(node, ast.Call):
                continue
            opname = getattr(node.func, 'attr', '') or getattr(node.func, 'id', '')
            kw = {item.arg: item.value for item in node.keywords if item.arg}
            if opname == 'CreateModel':
                name_node = kw.get('name')
                fields_node = kw.get('fields')
                if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str) and isinstance(fields_node, (ast.List, ast.Tuple)):
                    model_name = name_node.value
                    for elt in fields_node.elts:
                        if isinstance(elt, ast.Tuple) and elt.elts and isinstance(elt.elts[0], ast.Constant):
                            migrated.setdefault(model_name, set()).add(str(elt.elts[0].value))
            elif opname == 'AddField':
                model_node, name_node = kw.get('model_name'), kw.get('name')
                if isinstance(model_node, ast.Constant) and isinstance(name_node, ast.Constant):
                    model_low = str(model_node.value).lower()
                    for model_name in declared:
                        if model_name.lower() == model_low:
                            migrated.setdefault(model_name, set()).add(str(name_node.value))
    for model_name, fields in declared.items():
        missing = fields - migrated.get(model_name, set())
        if missing:
            fail(f'{app}: migration missing fields for {model_name}: {sorted(missing)}')

# 18) Literal URL tags must reference real route names and provide the correct
# number of positional path parameters. Variable route names are intentionally
# skipped because they are validated by their view context instead.
route_files = {
    'accounts': ROOT/'backend/apps/accounts/urls.py',
    'portal': ROOT/'backend/apps/companies/portal_urls.py',
    'ns_admin': ROOT/'backend/apps/core/admin_urls.py',
    'payments': ROOT/'backend/apps/payments/webhook_urls.py',
    'proaccess': ROOT/'backend/apps/proaccess/urls.py',
    'ops_api': ROOT/'backend/apps/ops/api_urls.py',
    'prompts_api': ROOT/'backend/apps/prompts/api_urls.py',
    'content_admin': ROOT/'backend/apps/contenthub/admin_urls.py',
    'prompt_studio': ROOT/'backend/apps/prompts/studio_urls.py',
    'root': ROOT/'backend/config/urls.py',
}
route_args = {}
for namespace, path in route_files.items():
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    for route, name in re.findall(r"path\(\s*['\"]([^'\"]*)['\"][\s\S]*?name\s*=\s*['\"]([^'\"]+)['\"]\s*\)", text):
        route_args[(namespace, name)] = len(re.findall(r'<[^>]+>', route))

for template in sorted(template_root.rglob('*.html')):
    text = template.read_text(encoding='utf-8')
    for tag in re.findall(r'{%\s*url\s+([^%]+)%}', text):
        m = re.match(r"['\"]([^'\"]+)['\"](.*)", tag.strip())
        if not m:
            continue
        route_name, rest = m.group(1), m.group(2).strip()
        if ':' in route_name:
            namespace, name = route_name.split(':', 1)
        else:
            namespace, name = 'root', route_name
        key = (namespace, name)
        if key not in route_args:
            # Existing name-only validator above emits the main error for known namespaces.
            if namespace in route_files:
                fail(f'{template.relative_to(ROOT)} references unknown URL {route_name}')
            continue
        rest = re.split(r'\s+as\s+', rest, maxsplit=1)[0].strip()
        tokens = [tok for tok in re.split(r'\s+', rest) if tok and '=' not in tok]
        expected = route_args[key]
        if len(tokens) != expected:
            fail(f'{template.relative_to(ROOT)} URL {route_name} has {len(tokens)} arg(s), expected {expected}')

# 19) Design regression guards: the approved logo must never be cropped or
# stretched in responsive CSS.
if re.search(r'\.brand\s+img\s*\{[^}]*object-fit\s*:\s*cover', css, flags=re.I|re.S):
    fail('Responsive CSS crops the approved PromptMaster logo')
if re.search(r'\.brand\s+img\s*\{[^}]*height\s*:\s*47px[^}]*width\s*:\s*54px', css, flags=re.I|re.S):
    fail('Responsive CSS distorts/crops PromptMaster logo dimensions')

# 19b) Admin dashboard charts must keep CSS percentages locale-neutral.
# German localization renders floats such as 100,0 for text, which is invalid
# inside CSS percentages and previously collapsed the revenue bar/donut.
dashboard_template = (ROOT/'backend/templates/ns_admin/dashboard.html').read_text(encoding='utf-8')
dashboard_views = (ROOT/'backend/apps/core/admin_views.py').read_text(encoding='utf-8')
dashboard_css = (ROOT/'backend/static/css/app.css').read_text(encoding='utf-8')
for needle in (
    "row['percent_css']",
    "format(row['percent'], '.1f')",
    "active_licenses = License.objects.filter(valid_until__gt=now, status__in=['active', 'free'])",
    "active_licenses.values('product__name')",
    "'licenses': active_licenses.count()",
):
    if needle not in dashboard_views:
        fail(f'Dashboard rendering/data contract missing: {needle}')
for needle in ('height:{{ row.percent_css }}%', '--share:{{ product_mix.0.percent_css }}%', 'class="revenue-value"', 'class="alert-stack"'):
    if needle not in dashboard_template:
        fail(f'Dashboard rendering contract missing: {needle}')
if '.alert-stack{display:grid;gap:' not in dashboard_css:
    fail('Dashboard action alerts are missing explicit visual spacing')

# 20) Customer/account separation is a V1 invariant. A private customer may
# not silently become a company member, which would make tenant scoping
# ambiguous and destructive company deactivation possible.
company_services = (ROOT/'backend/apps/companies/services.py').read_text(encoding='utf-8')
account_views = (ROOT/'backend/apps/accounts/views.py').read_text(encoding='utf-8')
if 'PrivateCustomerProfile.objects.filter(user__email__iexact=normalized)' not in company_services:
    fail('Company invitation service does not reject existing private customers')
if "hasattr(existing, 'private_customer')" not in account_views:
    fail('Invitation acceptance does not reject private/customer type conflicts')

# 21) Central PromptDomain/Composer is a release invariant from RC11 onward.
prompt_settings = (ROOT/'backend/config/settings.py').read_text(encoding='utf-8')
prompt_urls = (ROOT/'backend/config/urls.py').read_text(encoding='utf-8')
prompt_models = (ROOT/'backend/apps/prompts/models.py').read_text(encoding='utf-8')
prompt_services = (ROOT/'backend/apps/prompts/services.py').read_text(encoding='utf-8')
prompt_api = (ROOT/'backend/apps/prompts/api.py').read_text(encoding='utf-8')
if "'apps.prompts'" not in prompt_settings:
    fail('Central PromptDomain app is not installed')
if "path('api/v1/prompts/', include('apps.prompts.api_urls'))" not in prompt_urls:
    fail('Central Prompt API is not mounted')
for model_name in (
    'PromptApplication', 'PromptDefinition', 'PromptPolicySet', 'PromptVersion',
    'PromptField', 'PromptOption', 'MicrosoftTier', 'MicrosoftCapability', 'PromptLegacyContract',
):
    if f'class {model_name}(' not in prompt_models:
        fail(f'PromptDomain model missing: {model_name}')
if 'policy_set = models.ForeignKey(PromptPolicySet' not in prompt_models:
    fail('PromptVersion does not pin its PromptPolicySet')
if "'persisted': False" not in prompt_api or "response['Cache-Control'] = 'no-store'" not in prompt_api:
    fail('Prompt compose API does not expose stateless/no-store contract')
if 'version.app_rule_snapshot or app.rule' not in prompt_services:
    fail('Published prompt version does not use app-rule snapshot')

prompt_validator = subprocess.run(
    [sys.executable, str(ROOT/'scripts/validate_prompt_domain.py')],
    cwd=ROOT, capture_output=True, text=True,
)
if prompt_validator.returncode:
    fail('PromptDomain validator failed: ' + (prompt_validator.stdout + prompt_validator.stderr).strip())


# 21b) Production backup and external acceptance must resolve the same
# restic S3 region configuration. S3_REGION is retained only as a compatibility
# alias; restic consumes AWS_DEFAULT_REGION.
backup_script = (ROOT/'backup/backup.sh').read_text(encoding='utf-8')
for needle in (
    'AWS_DEFAULT_REGION',
    'S3_REGION',
    'export AWS_DEFAULT_REGION="$S3_REGION"',
):
    if needle not in backup_script:
        fail(f'Production backup S3-region compatibility missing: {needle}')

# 22) External production-acceptance harnesses are release invariants. They are
# deliberately manual because they require real provider/infrastructure access,
# but CI must prevent later edits from weakening their fail-closed safety.
acceptance_files = {
    'mollie': ROOT/'backend/apps/core/management/commands/external_mollie_acceptance.py',
    'graph': ROOT/'backend/apps/core/management/commands/external_graph_acceptance.py',
    'backup': ROOT/'scripts/external_backup_acceptance.sh',
    'docs': ROOT/'docs/PRODUCTION_ACCEPTANCE.md',
}
for name, path in acceptance_files.items():
    if not path.exists():
        fail(f'External acceptance artifact missing: {name} ({path.relative_to(ROOT)})')

if all(path.exists() for path in acceptance_files.values()):
    mollie_acceptance = acceptance_files['mollie'].read_text(encoding='utf-8')
    graph_acceptance = acceptance_files['graph'].read_text(encoding='utf-8')
    backup_acceptance = acceptance_files['backup'].read_text(encoding='utf-8')
    production_acceptance = acceptance_files['docs'].read_text(encoding='utf-8')

    for needle in (
        "client.key.startswith('test_')",
        'CREATE-MOLLIE-TEST-PAYMENT',
        'CREATE-MOLLIE-TEST-REFUND',
        'publicly reachable HTTPS hostname',
        'processed_at__isnull=False',
        'create_refund_request',
        'submit_refund',
        "mode != 'test'",
        'metadata order_id does not match',
        'Mollie webhook URL',
    ):
        if needle not in mollie_acceptance:
            fail(f'Mollie external acceptance safety/invariant missing: {needle}')

    for needle in (
        'SEND-GRAPH-ACCEPTANCE',
        'send_email_message.run',
        'INVALID_SENDER',
        "failure.status != 'failed'",
        'retry_count',
    ):
        if needle not in graph_acceptance:
            fail(f'Graph external acceptance safety/invariant missing: {needle}')

    for needle in (
        'RUN_EXTERNAL_S3_RESTORE',
        's3:https://*)',
        's3:http://*)',
        'backup_was_running',
        'trap restore_backup_service EXIT',
        'pg_isready',
        'RESTORE_TEST_INTERVAL_SECONDS=0',
        'PRUNE_INTERVAL_SECONDS=9999999999',
        'before_snapshot',
        'after_snapshot',
        'last-restore.json',
        'EXTERNAL S3/RESTIC BACKUP + ISOLATED POSTGRES RESTORE OK',
    ):
        if needle not in backup_acceptance:
            fail(f'External backup acceptance safety/invariant missing: {needle}')

    for needle in (
        'external_graph_acceptance',
        'external_mollie_acceptance',
        'external_backup_acceptance.sh',
        'Application Mail.Send',
        'Chargeback-Reversal',
    ):
        if needle not in production_acceptance:
            fail(f'Production acceptance documentation incomplete: {needle}')

release_gates = (ROOT/'docs/RELEASE_GATES.md').read_text(encoding='utf-8')
if 'docs/PRODUCTION_ACCEPTANCE.md' not in release_gates:
    fail('Release gates do not reference the executable production acceptance procedure')


if errors:
    print('\n'.join(f'[FAIL] {e}' for e in errors))
    print(f'\nSTATIC VALIDATION FAILED: {len(errors)} issue(s)')
    sys.exit(1)
print('STATIC VALIDATION OK')
