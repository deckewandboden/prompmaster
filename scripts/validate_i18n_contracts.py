#!/usr/bin/env python3
"""Early-release i18n gate: 9 locale catalogs, placeholders and brand terms.

No third-party packages. Catches broken interpolation/format strings before
PostgreSQL, browser tests or the Docker image is built.
"""
from __future__ import annotations

from ast import literal_eval
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl')
BRAND_LABELS = (
    'Word', 'Excel', 'PowerPoint', 'Outlook', 'Teams', 'OneNote',
    'OneDrive', 'SharePoint', 'Power BI', 'Power Apps', 'Power Automate',
    'Copilot Studio', 'Clipchamp', 'Whiteboard', 'Power Pages',
    'Microsoft Security Copilot', 'Microsoft 365 Copilot Business',
    'Copilot Chat (Basic)', 'M365 Copilot (Basic)',
    'Microsoft Forms', 'Microsoft Planner', 'Microsoft Fabric',
    'Microsoft Copilot in Azure', 'Workplace Analytics', 'Copilot Analytics',
)
PLACEHOLDER = re.compile(r'%[(]([A-Za-z_][A-Za-z0-9_]*)[)][a-zA-Z]')


def parse_po(path: Path) -> dict[str, str]:
    entries = {}
    key = None
    translation = ''
    section = None

    def save():
        if key:
            if key in entries:
                raise ValueError(f'{path}: duplicated msgid {key!r}')
            entries[key] = translation

    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('msgid '):
            save()
            key = literal_eval(line[len('msgid '):])
            translation = ''
            section = 'id'
        elif line.startswith('msgstr '):
            translation = literal_eval(line[len('msgstr '):])
            section = 'translation'
        elif line.startswith('"') and section:
            piece = literal_eval(line)
            if section == 'id':
                key += piece
            else:
                translation += piece
    save()
    return entries


def main() -> None:
    base = parse_po(ROOT / 'backend/locale/en/LC_MESSAGES/django.po')
    assert len(base) >= 370, 'Too few canonical gettext messages'
    for code in LOCALES:
        path = ROOT / 'backend/locale' / code / 'LC_MESSAGES/django.po'
        found = parse_po(path)
        if set(found) != set(base):
            missing = set(base) - set(found)
            extra = set(found) - set(base)
            raise SystemExit(f'I18N FAIL {code}: missing={len(missing)}, unexpected={len(extra)}')
        for key, target in found.items():
            if not target.strip():
                raise SystemExit(f'I18N FAIL {code}: empty translation {key!r}')
            expected_tokens = sorted(PLACEHOLDER.findall(key))
            actual_tokens = sorted(PLACEHOLDER.findall(target))
            if expected_tokens != actual_tokens:
                raise SystemExit(
                    f'I18N FAIL {code}: unsafe named placeholders {key!r}: '
                    f'{expected_tokens} != {actual_tokens}'
                )
        if code in ('pl', 'fr', 'it', 'nl'):
            for product in ('PROMPTFINISHER Free', 'PROMPTFINISHER Pro', 'Free'):
                if found.get(product) != product:
                    raise SystemExit(f'I18N FAIL {code}: product branding modified: {product}')
        print(f'I18N PASS {code}: {len(found)} strings, placeholders unchanged')

    # The dynamic Free/Pro UI catalog is separate from Django gettext.
    # Product names must never be translated as ordinary dictionary words.
    bundle = (ROOT / 'backend/static/js/promptfinisher_product_i18n.20261011.js'
              ).read_text(encoding='utf-8')
    prefix, delimiter = '  const TEXT=', ';\n  const language = '
    if prefix not in bundle or delimiter not in bundle:
        raise SystemExit('I18N FAIL: product UI dictionary markers missing')
    catalog = json.loads(bundle.split(prefix, 1)[1].split(delimiter, 1)[0])
    for brand in BRAND_LABELS:
        if brand not in catalog:
            raise SystemExit(f'I18N FAIL: missing protected product label {brand}')
        for code in LOCALES:
            if catalog[brand].get(code) != brand:
                raise SystemExit(
                    f'I18N FAIL: product label {brand!r} mutated in {code}: '
                    f'{catalog[brand].get(code)!r}'
                )
    # Official application names must also survive inside descriptions and
    # task titles, not just when they occupy the whole translation key.
    checked = 0
    for original, translations in catalog.items():
        embedded = [brand for brand in BRAND_LABELS if brand in original]
        if not embedded:
            continue
        for code in LOCALES:
            rendered = translations.get(code, '')
            for brand in embedded:
                if brand not in rendered:
                    raise SystemExit(
                        f'I18N FAIL {code}: protected product name {brand!r} '
                        f'missing from translated phrase {original!r}'
                    )
                checked += 1
    print(f'I18N EMBEDDED BRAND LABELS PASS: {checked} preserved product names')

    # Reject broken word boundaries introduced by chained offline translations.
    # These names are indivisible trademarks and must never stick to a word.
    fused_brand = re.compile(
        r'(?:Copilot Chat|M365 Copilot|PROMPTFINISHER|netstyle|SharePoint|OneDrive)'
        r'(?=[A-Za-zÀ-ÿА-Яа-я])'
    )
    repeated_machine_word = re.compile(r'\b([A-Za-z]{2,})(?:\s+\1){4,}\b', re.I)
    for phrase, variants in catalog.items():
        for code in LOCALES:
            translation = variants.get(code, '')
            if fused_brand.search(translation):
                raise SystemExit(
                    f'I18N FAIL {code}: product name concatenated to text: '
                    f'{phrase!r} => {translation[:160]!r}'
                )
            if repeated_machine_word.search(translation):
                raise SystemExit(
                    f'I18N FAIL {code}: repeated machine-translation token: '
                    f'{phrase!r} => {translation[:160]!r}'
                )
    for phrase in ('ab Copilot Chat (Basic)', 'ab M365 Copilot (Basic)'):
        for code in LOCALES:
            label = catalog[phrase][code]
            if any(label.lower().startswith(prefix) for prefix in (
                'off', 'apagado', 'desligado', 'kapalı',
                'выключать', 'wyłączone', 'départ', 'uit',
            )):
                raise SystemExit(f'I18N FAIL {code}: availability tier mistranslated as disabled')
    # The protected Free/Pro runtime uses stable option values for composer
    # semantics. Translate only the visible text of explicitly-valued options.
    tone_keys = (
        'Kompakt', 'Standard', 'Detailliert', 'Professionell', 'Sachlich',
        'Management', 'Technisch', 'Direkt', 'Freundlich',
    )
    tone_examples = {
        ('Standard', 'tr'): 'Standart',
        ('Detailliert', 'tr'): 'Ayrıntılı',
        ('Detailliert', 'fr'): 'Détaillé',
        ('Sachlich', 'tr'): 'Nesnel',
        ('Sachlich', 'nl'): 'Zakelijk',
        ('Sachlich', 'pl'): 'Rzeczowy',
        ('Management', 'tr'): 'Yönetim',
        ('Management', 'nl'): 'Management',
        ('Freundlich', 'es'): 'Amable',
        ('Freundlich', 'tr'): 'Samimi',
    }
    for key in tone_keys:
        variants = catalog.get(key)
        if not variants:
            raise SystemExit(f'I18N FAIL: missing response-style choice {key!r}')
        for code in LOCALES:
            value = variants.get(code, '')
            if not value.strip():
                raise SystemExit(f'I18N FAIL {code}: empty response-style choice {key!r}')
            if re.search(r'\\b(\\w{2,})(?:\\s+\\1)\\b', value, flags=re.I):
                raise SystemExit(
                    f'I18N FAIL {code}: repeated response-style choice {key!r}: {value!r}'
                )
    for (key, code), expected in tone_examples.items():
        if catalog[key][code] != expected:
            raise SystemExit(
                f'I18N FAIL {code}: response-style term {key!r} must be {expected!r}, '
                f'got {catalog[key][code]!r}'
            )
    if "'script,style,textarea,input,option,[contenteditable],'" in bundle:
        raise SystemExit('I18N FAIL: visible select option labels excluded from translation')
    if "if (option && !option.hasAttribute('value')) return;" not in bundle:
        raise SystemExit('I18N FAIL: select options without a stable value must be protected')
    print('I18N RESPONSE STYLE PASS: nine controls x nine locales, stable option values')

    # License warnings are action-critical: keep both the complete Microsoft
    # product name and an explicit requirement word in every translated label.
    requirement_words = {
        'en': 'REQUIRED', 'es': 'REQUIERE', 'pt': 'NECESSÁRIO',
        'tr': 'GEREKLİ', 'ru': 'ТРЕБУЕТСЯ', 'pl': 'WYMAGANY',
        'fr': 'REQUIS', 'it': 'RICHIESTO', 'nl': 'VEREIST',
    }
    for source, official in (
        ('M365 COPILOT (BASIC) ERFORDERLICH', 'M365 COPILOT (BASIC)'),
        ('MICROSOFT 365 COPILOT BUSINESS ERFORDERLICH',
         'MICROSOFT 365 COPILOT BUSINESS'),
    ):
        for code in LOCALES:
            label = catalog[source][code]
            if official not in label or requirement_words[code] not in label.upper():
                raise SystemExit(
                    f'I18N FAIL {code}: licensing requirement lost: '
                    f'{source!r} => {label!r}'
                )
    print('I18N LICENSE REQUIREMENT PASS: two license gates x nine languages')

    print('I18N PHRASE QUALITY PASS: no fused brand tokens or runaway word repetitions')

    print(f'I18N PRODUCT LABELS PASS: {len(BRAND_LABELS)} brands x {len(LOCALES)} locales')
    # The live Django Pro catalog is seeded from this frozen runtime source.
    # Verify visible app metadata and task-selection labels (not hidden prompt
    # instructions, IDs or user inputs) cannot silently fall back to German.
    logic_path = ROOT / 'backend/apps/prompts/data/pm20_golden_logic.json'
    app_definitions = json.loads(logic_path.read_text(encoding='utf-8'))['APP']
    if len(app_definitions) != 34:
        raise SystemExit(f'I18N FAIL: expected 34 application definitions, got {len(app_definitions)}')
    total_tasks = sum(len(app['tasks']) for app in app_definitions.values())
    if total_tasks != 194:
        raise SystemExit(f'I18N FAIL: expected 194 catalog tasks, got {total_tasks}')
    categories = {
        'app name': {app['name'] for app in app_definitions.values()},
        'app description': {app['copy'] for app in app_definitions.values()},
        'app licensing': {app['access'] for app in app_definitions.values()},
        'task title': {
            task['title'] for app in app_definitions.values() for task in app['tasks']
        },
        'task area': {
            task['area'] for app in app_definitions.values() for task in app['tasks']
        },
    }
    for category, values in categories.items():
        for phrase in values:
            if phrase not in catalog:
                raise SystemExit(f'I18N FAIL: missing {category} string: {phrase!r}')
            for code in LOCALES:
                if not catalog[phrase].get(code, '').strip():
                    raise SystemExit(
                        f'I18N FAIL {code}: untranslated {category} label: {phrase!r}'
                    )
    print(
        'I18N LIVE APP CATALOG PASS: 34 apps / 194 tasks; '
        + ', '.join(f'{name}={len(values)}' for name, values in categories.items())
        + ' across nine target locales'
    )

    print('I18N CONTRACTS PASS: 10 UI languages incl. DE source')


if __name__ == '__main__':
    main()
