#!/usr/bin/env python3
"""Early-release i18n gate: 9 locale catalogs, placeholders and brand terms.

No third-party packages. Catches broken interpolation/format strings before
PostgreSQL, browser tests or the Docker image is built.
"""
from __future__ import annotations

from ast import literal_eval
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl')
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

    print('I18N CONTRACTS PASS: 10 UI languages incl. DE source')


if __name__ == '__main__':
    main()
