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
    print(f'I18N PRODUCT LABELS PASS: {len(BRAND_LABELS)} brands x {len(LOCALES)} locales')
    print('I18N CONTRACTS PASS: 10 UI languages incl. DE source')


if __name__ == '__main__':
    main()
