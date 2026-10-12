"""Offline Free/Pro user-interface translation extension (draft, QA gated).

This only updates the additive presentation-only V2 script, never Golden
Master HTML, application codes, prompt contracts or composition services.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import argostranslate.package
import argostranslate.translate

ROOT = Path(__file__).resolve().parents[1]
PHRASES = ROOT / 'product/i18n/free_pro_visible_strings.json'
SCRIPT = ROOT / 'backend/static/js/promptfinisher_product_i18n.20261011.js'
REPORT = ROOT / 'docs/FREE_PRO_I18N_DRAFT_REPORT.md'
TARGETS = ('en', 'es', 'pt', 'tr', 'ru', 'pl', 'fr', 'it', 'nl')
# Official application names are trademarks, never UI strings for NMT.
IMMUTABLE_BRAND_LABELS = frozenset({
    'Word', 'Excel', 'PowerPoint', 'Outlook', 'Teams', 'OneNote',
    'OneDrive', 'SharePoint', 'Power BI', 'Power Apps', 'Power Automate',
    'Copilot Studio', 'Clipchamp', 'Whiteboard', 'Power Pages',
    'Microsoft Security Copilot', 'Microsoft 365 Copilot Business',
    'Copilot Chat (Basic)', 'M365 Copilot (Basic)',
    'Microsoft Forms', 'Microsoft Planner', 'Microsoft Fabric',
    'Microsoft Copilot in Azure', 'Workplace Analytics', 'Copilot Analytics',
})
PROTECTED = re.compile(
    '|'.join(
        re.escape(brand)
        for brand in sorted(IMMUTABLE_BRAND_LABELS, key=lambda name: (-len(name), name))
    ) +
    r'|PROMPTFINISHER|Microsoft 365 Copilot|Microsoft Copilot'
    r'|Copilot Chat|M365 Copilot|netstyle|Mollie'
    r'|%[(][A-Za-z_][A-Za-z_0-9]*[)][a-z]|[{][A-Za-z_][A-Za-z_0-9]*[}]',
    re.I,
)
BLOCK = re.compile('(  const TEXT=)({.*?})(;' + chr(10) + '  const language = )', re.S)


def install_model(available, src: str, dst: str) -> None:
    candidates = [package for package in available
                  if package.from_code == src and package.to_code == dst]
    if not candidates:
        raise RuntimeError(f'Offline Argos {src}->{dst} package unavailable')
    argostranslate.package.install_from_path(candidates[0].download())


def safe_translate(original: str, translator) -> str:
    # Protected product names and placeholders are not sent through the NMT
    # system; only intervening descriptive text gets translated.
    parts = PROTECTED.split(original)
    tokens = PROTECTED.findall(original)
    translated = []
    for index, piece in enumerate(parts):
        if piece.strip() and len(piece) >= 2:
            new = translator.translate(piece)
            if new.strip() and len(new) < max(2000, 5 * len(piece)):
                piece = new
        translated.append(piece)
        if index < len(tokens):
            translated.append(tokens[index])
    joined = ''.join(translated).strip()
    return joined if joined else original


def main() -> None:
    source = json.loads(PHRASES.read_text(encoding='utf-8'))
    phrases = source['terms']
    script = SCRIPT.read_text(encoding='utf-8')
    match = BLOCK.search(script)
    if not match:
        raise SystemExit('V2 localization bundle marker missing')
    existing = json.loads(match.group(2))
    available = argostranslate.package.get_available_packages()
    # Resolve translations from German source. For other languages use the
    # offline English pivot to avoid a dependency on unsupported language
    # pairs; no SaaS endpoint is used for any text.
    install_model(available, 'de', 'en')
    de_en = argostranslate.translate.get_translation_from_codes('de', 'en')
    summary = []
    for locale in TARGETS:
        translator = de_en
        if locale != 'en':
            install_model(available, 'en', locale)
            en_target = argostranslate.translate.get_translation_from_codes('en', locale)
        translated_count = 0
        source_fallbacks = 0
        for original in phrases:
            entry = existing.setdefault(original, {})
            if original in IMMUTABLE_BRAND_LABELS:
                # Override even pre-existing machine translations for brand-only labels.
                entry[locale] = original
                continue
            if entry.get(locale):
                continue  # Manually curated translations take precedence
            translation = safe_translate(original, de_en)
            if locale != 'en':
                translation = safe_translate(translation, en_target)
            if translation == original:
                source_fallbacks += 1
            else:
                translated_count += 1
            entry[locale] = translation
        coverage = sum(1 for original in phrases if existing[original].get(locale))
        if coverage != len(phrases):
            raise RuntimeError(f'Incomplete UI dictionary for {locale}')
        summary.append((locale, coverage, translated_count, source_fallbacks))
        print(f'UI {locale}: {coverage}/{len(phrases)} terms, {translated_count} generated, '
              f'{source_fallbacks} unchanged', flush=True)
    result = json.dumps(existing, ensure_ascii=False, separators=(',', ':'))
    script = script[:match.start(2)] + result + script[match.end(2):]
    SCRIPT.write_text(script, encoding='utf-8')
    REPORT.write_text(
        '# Free/Pro UI locale catalog audit (draft)\n\n'
        'Translations generated locally using offline Argos language models.\n'
        'Terminology, punctuation, meaning and layout require native QA before release.\n'
        'The original Golden Masters, prompt composition policies, task IDs and '
        'license checks are deliberately unchanged.\n\n'
        '| Language | Extracted source phrases | Generated | Unchanged source |\n'
        '|---|---:|---:|---:|\n'
        + ''.join(f'| {a} | {b} | {c} | {d} |\n' for a,b,c,d in summary),
        encoding='utf-8',
    )


if __name__ == '__main__':
    main()
